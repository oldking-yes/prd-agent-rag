"""UsageService — records and queries LLM token consumption."""

import json
import logging
from datetime import datetime, timedelta, UTC

from sqlalchemy import Integer, func
from sqlalchemy.orm import Session

from app.db.models.usage_log import UsageLog

logger = logging.getLogger(__name__)

# DeepSeek v4-flash pricing (CNY per million tokens)
PRICING = {
    "input": 1.0,
    "output": 2.0,
    "cached": 0.1,
}


def estimate_cost(input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> float:
    """Estimate cost in CNY based on token counts."""
    return (
        input_tokens * PRICING["input"] / 1_000_000
        + output_tokens * PRICING["output"] / 1_000_000
        + cached_tokens * PRICING["cached"] / 1_000_000
    )


class UsageService:
    """Records and queries LLM usage data."""

    def __init__(self, db: Session):
        self.db = db

    def record(
        self,
        *,
        session_id: str | None = None,
        model: str = "deepseek-v4-flash",
        provider: str = "deepseek",
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_tokens: int = 0,
        tool_calls: int = 0,
        tool_names: list[str] | None = None,
        response_time_ms: int = 0,
    ) -> UsageLog:
        """Record a single LLM API call."""
        total = input_tokens + output_tokens
        cost = estimate_cost(input_tokens, output_tokens, cached_tokens)
        rag_triggered = any(
            t in ("search_documents", "search_knowledge_base")
            for t in (tool_names or [])
        )

        log = UsageLog(
            session_id=session_id,
            model=model,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            total_tokens=total,
            tool_calls=tool_calls,
            tool_names=json.dumps(tool_names or []),
            estimated_cost_cny=cost,
            response_time_ms=response_time_ms,
            rag_triggered=rag_triggered,
        )
        self.db.add(log)
        self.db.commit()
        logger.info("Usage recorded: %d tokens, ¥%.4f, rag=%s", total, cost, rag_triggered)
        return log

    def get_summary(self, days: int = 30) -> dict:
        """Get aggregated usage summary."""
        since = datetime.now(UTC) - timedelta(days=days)
        row = self.db.query(
            func.sum(UsageLog.input_tokens).label("input"),
            func.sum(UsageLog.output_tokens).label("output"),
            func.sum(UsageLog.total_tokens).label("total"),
            func.sum(UsageLog.estimated_cost_cny).label("cost"),
            func.count(UsageLog.id).label("requests"),
            func.sum(UsageLog.tool_calls).label("tools"),
            func.sum(func.cast(UsageLog.rag_triggered, Integer)).label("rag_count"),
        ).filter(UsageLog.created_at >= since).first()

        return {
            "input_tokens": int(row.input or 0),
            "output_tokens": int(row.output or 0),
            "total_tokens": int(row.total or 0),
            "estimated_cost_cny": round(float(row.cost or 0), 4),
            "total_requests": int(row.requests or 0),
            "total_tool_calls": int(row.tools or 0),
            "rag_triggered_count": int(row.rag_count or 0),
            "days": days,
        }

    def get_daily_trend(self, days: int = 7) -> list[dict]:
        """Get daily token usage trend."""
        since = datetime.now(UTC) - timedelta(days=days)
        rows = (
            self.db.query(
                func.date(UsageLog.created_at).label("date"),
                func.sum(UsageLog.input_tokens).label("input"),
                func.sum(UsageLog.output_tokens).label("output"),
                func.sum(UsageLog.estimated_cost_cny).label("cost"),
                func.count(UsageLog.id).label("requests"),
                func.sum(func.cast(UsageLog.rag_triggered, Integer)).label("rag_count"),
            )
            .filter(UsageLog.created_at >= since)
            .group_by(func.date(UsageLog.created_at))
            .order_by(func.date(UsageLog.created_at))
            .all()
        )
        return [
            {
                "date": str(r.date),
                "input_tokens": int(r.input or 0),
                "output_tokens": int(r.output or 0),
                "estimated_cost_cny": round(float(r.cost or 0), 4),
                "requests": int(r.requests or 0),
                "rag_triggered": int(r.rag_count or 0),
            }
            for r in rows
        ]

    def get_recent_sessions(self, limit: int = 10) -> list[dict]:
        """Get recent conversation usage details."""
        rows = (
            self.db.query(UsageLog)
            .order_by(UsageLog.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": r.id[:8],
                "timestamp": r.created_at.isoformat() if r.created_at else None,
                "model": r.model,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "total_tokens": r.total_tokens,
                "tool_calls": r.tool_calls,
                "tool_names": json.loads(r.tool_names) if r.tool_names else [],
                "estimated_cost_cny": r.estimated_cost_cny,
                "response_time_ms": r.response_time_ms,
                "rag_triggered": r.rag_triggered,
            }
            for r in rows
        ]

    def get_rag_stats(self, days: int = 30) -> dict:
        """Get RAG quality metrics."""
        since = datetime.now(UTC) - timedelta(days=days)
        total = self.db.query(func.count(UsageLog.id)).filter(UsageLog.created_at >= since).scalar() or 0
        rag_count = (
            self.db.query(func.count(UsageLog.id))
            .filter(UsageLog.created_at >= since, UsageLog.rag_triggered == True)
            .scalar()
            or 0
        )
        return {
            "total_requests": total,
            "rag_triggered": rag_count,
            "rag_trigger_rate": round(rag_count / total * 100, 1) if total > 0 else 0,
            "days": days,
        }
