"""UsageLog model — tracks LLM API token consumption and cost."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class UsageLog(TimestampMixin, Base):
    """Records each LLM API call's token usage and estimated cost."""

    __tablename__ = "usage_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    model: Mapped[str] = mapped_column(String(100), nullable=False, default="deepseek-v4-flash")
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="deepseek")

    # Token counts
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Tool usage
    tool_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tool_names: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array of tool names

    # Cost (CNY)
    estimated_cost_cny: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Performance
    response_time_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # RAG derived field — computed at write time
    rag_triggered: Mapped[bool] = mapped_column(default=False, nullable=False)

    def __repr__(self) -> str:
        return f"<UsageLog {self.id[:8]} model={self.model} tokens={self.total_tokens}>"
