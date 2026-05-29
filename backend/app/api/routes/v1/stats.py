"""Usage statistics API routes."""

from typing import Any

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser
from app.db.session import SessionLocal
from app.services.usage import UsageService

router = APIRouter()


@router.get("/stats/summary")
async def usage_summary(
    _: CurrentUser,
    days: int = Query(30, ge=1, le=365),
) -> Any:
    """Get aggregated usage summary."""
    db = SessionLocal()
    try:
        return UsageService(db).get_summary(days=days)
    finally:
        db.close()


@router.get("/stats/daily")
async def usage_daily_trend(
    _: CurrentUser,
    days: int = Query(7, ge=1, le=90),
) -> Any:
    """Get daily token usage trend."""
    db = SessionLocal()
    try:
        return UsageService(db).get_daily_trend(days=days)
    finally:
        db.close()


@router.get("/stats/sessions")
async def usage_recent_sessions(
    _: CurrentUser,
    limit: int = Query(10, ge=1, le=100),
) -> Any:
    """Get recent conversation usage details."""
    db = SessionLocal()
    try:
        return UsageService(db).get_recent_sessions(limit=limit)
    finally:
        db.close()


@router.get("/stats/rag")
async def usage_rag_stats(
    _: CurrentUser,
    days: int = Query(30, ge=1, le=365),
) -> Any:
    """Get RAG quality metrics."""
    db = SessionLocal()
    try:
        return UsageService(db).get_rag_stats(days=days)
    finally:
        db.close()


@router.get("/stats/rag-eval")
async def rag_evaluation(_: CurrentUser) -> Any:
    """Run RAG evaluation against ground truth and return quality metrics."""
    from app.services.rag.eval import run_evaluation
    return await run_evaluation()


@router.get("/stats/kb-metadata")
async def kb_metadata(_: CurrentUser) -> Any:
    """Get knowledge base metadata: chunk counts, embedding model, storage info."""
    from app.services.rag.eval import get_kb_metadata
    return await get_kb_metadata()


@router.get("/stats/benchmark")
async def run_benchmark(_: CurrentUser) -> Any:
    """Run comprehensive RAG benchmark: precision, latency distribution, edge cases, token breakdown."""
    from app.services.rag.benchmark import run_full_benchmark
    return await run_full_benchmark()
