
"""Conversation repository (SQLite sync).

Contains database operations for Conversation, Message, and ToolCall entities.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update as sql_update
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import String

from app.db.models.conversation import Conversation, Message, ToolCall


# Conversation Operations


def get_conversation_by_id(
    db: Session,
    conversation_id: str,
    *,
    include_messages: bool = False,
) -> Conversation | None:
    """Get conversation by ID, optionally with messages."""
    if include_messages:
        query = (
            select(Conversation)
            .options(selectinload(Conversation.messages).selectinload(Message.tool_calls))
            .where(Conversation.id == conversation_id)
        )
        result = db.execute(query)
        return result.scalar_one_or_none()
    return db.get(Conversation, conversation_id)


def get_conversations_by_user(
    db: Session,
    user_id: str | None = None,
    *,
    skip: int = 0,
    limit: int = 50,
    include_archived: bool = False,
) -> list[Conversation]:
    """Get conversations for a user with pagination."""
    query = select(Conversation)
    if user_id:
        query = query.where(Conversation.user_id == user_id)
    if not include_archived:
        query = query.where(Conversation.is_archived == False)  # noqa: E712
    query = query.order_by(func.coalesce(Conversation.updated_at, Conversation.created_at).desc()).offset(skip).limit(limit)
    result = db.execute(query)
    return list(result.scalars().all())
def get_all_conversations_with_count(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 50,
    include_archived: bool = False,
    search: str | None = None,
) -> tuple[list[tuple[Conversation, int]], int]:
    """Get all conversations with message counts for admin (paginated).

    Returns list of (conversation, message_count) tuples and total count.
    """
    message_count_subq = (
        select(func.count(Message.id))
        .where(Message.conversation_id == Conversation.id)
        .correlate(Conversation)
        .scalar_subquery()
    )

    query = select(Conversation, message_count_subq.label("message_count"))

    if not include_archived:
        query = query.where(Conversation.is_archived == False)  # noqa: E712
    if search:
        safe_search = search.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        query = query.where(
            (Conversation.title.ilike(f"%{safe_search}%", escape="\\"))
            | Conversation.id.cast(String).ilike(f"{safe_search}%", escape="\\")
        )

    query = query.order_by(
        func.coalesce(Conversation.updated_at, Conversation.created_at).desc()
    ).offset(skip).limit(limit)
    result = db.execute(query)
    rows = result.all()

    # Total count (same filters, no pagination)
    count_query = select(func.count(Conversation.id))
    if not include_archived:
        count_query = count_query.where(Conversation.is_archived == False)  # noqa: E712
    if search:
        safe_search = search.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        count_query = count_query.where(
            (Conversation.title.ilike(f"%{safe_search}%", escape="\\"))
            | Conversation.id.cast(String).ilike(f"{safe_search}%", escape="\\")
        )
    total: int = db.execute(count_query).scalar() or 0

    return [tuple(row) for row in rows], total


def export_chunk(
    db: Session,
    *,
    last_created_at: datetime | None,
    last_id: str | None,
    limit: int,
) -> list[Conversation]:
    """Keyset-paginated chunk for admin export of all conversations."""
    from sqlalchemy import tuple_

    query = (
        select(Conversation)
        .order_by(Conversation.created_at.desc(), Conversation.id.desc())
        .limit(limit)
    )
    if last_created_at is not None and last_id is not None:
        query = query.where(
            tuple_(Conversation.created_at, Conversation.id) < (last_created_at, last_id)
        )
    result = db.execute(query)
    return list(result.scalars().all())


def admin_list_with_users(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 50,
    search: str | None = None,
    user_id: str | None = None,
    include_archived: bool = False,
    archived_only: bool = False,
    sort_by: str = "updated_at",
    sort_dir: str = "desc",
) -> tuple[list[tuple[Conversation, int, str | None]], int]:
    """Admin: list conversations across all users with message counts and owner email.

    Returns list of (conversation, message_count, user_email) tuples and total count.
    """
    from app.db.models.user import User

    msg_count_col = func.count(Message.id).label("message_count")
    query = (
        select(Conversation, msg_count_col, User.email.label("user_email"))
        .outerjoin(Message, Message.conversation_id == Conversation.id)
        .outerjoin(User, User.id == Conversation.user_id)
        .group_by(Conversation.id, User.email)
    )
    count_query = select(func.count()).select_from(Conversation)

    if search:
        query = query.where(Conversation.title.ilike(f"%{search}%"))
        count_query = count_query.where(Conversation.title.ilike(f"%{search}%"))
    if user_id is not None:
        query = query.where(Conversation.user_id == user_id)
        count_query = count_query.where(Conversation.user_id == user_id)
    if archived_only:
        query = query.where(Conversation.is_archived.is_(True))
        count_query = count_query.where(Conversation.is_archived.is_(True))
    elif not include_archived:
        query = query.where(Conversation.is_archived.is_(False))
        count_query = count_query.where(Conversation.is_archived.is_(False))

    sort_columns: dict[str, Any] = {
        "title": Conversation.title,
        "created_at": Conversation.created_at,
        "updated_at": Conversation.updated_at,
        "owner": User.email,
        "messages": msg_count_col,
    }
    sort_col = sort_columns.get(sort_by, Conversation.updated_at)
    sort_col = sort_col.desc() if sort_dir == "desc" else sort_col.asc()
    query = query.order_by(sort_col).offset(skip).limit(limit)

    total = db.scalar(count_query) or 0
    rows = db.execute(query).all()
    return [(conv, msg_count, email) for conv, msg_count, email in rows], total


def count_conversations(
    db: Session,
    user_id: str | None = None,
    *,
    include_archived: bool = False,
) -> int:
    """Count conversations for a user."""
    query = select(func.count(Conversation.id))
    if user_id:
        query = query.where(Conversation.user_id == user_id)
    if not include_archived:
        query = query.where(Conversation.is_archived == False)  # noqa: E712
    result = db.execute(query)
    return result.scalar() or 0


def create_conversation(
    db: Session,
    *,
    user_id: str | None = None,
    title: str | None = None,
) -> Conversation:
    """Create a new conversation."""
    conversation = Conversation(
        user_id=user_id,
        title=title,
    )
    db.add(conversation)
    db.flush()
    db.refresh(conversation)
    return conversation


def update_conversation(
    db: Session,
    *,
    db_conversation: Conversation,
    update_data: dict[str, Any],
) -> Conversation:
    """Update a conversation."""
    for field, value in update_data.items():
        setattr(db_conversation, field, value)

    db.add(db_conversation)
    db.flush()
    db.refresh(db_conversation)
    return db_conversation


def archive_conversation(
    db: Session,
    conversation_id: str,
) -> Conversation | None:
    """Archive a conversation."""
    conversation = get_conversation_by_id(db, conversation_id)
    if conversation:
        conversation.is_archived = True
        db.add(conversation)
        db.flush()
        db.refresh(conversation)
    return conversation


def delete_conversation(db: Session, conversation_id: str) -> bool:
    """Delete a conversation and all related messages/tool_calls (cascades)."""
    conversation = get_conversation_by_id(db, conversation_id)
    if conversation:
        db.delete(conversation)
        db.flush()
        return True
    return False


# Message Operations


def get_message_by_id(db: Session, message_id: str) -> Message | None:
    """Get message by ID."""
    return db.get(Message, message_id)


def get_messages_by_conversation(
    db: Session,
    conversation_id: str,
    *,
    skip: int = 0,
    limit: int = 100,
    include_tool_calls: bool = False,
) -> list[Message]:
    """Get messages for a conversation with pagination."""
    query = select(Message).where(Message.conversation_id == conversation_id)
    if include_tool_calls:
        query = query.options(selectinload(Message.tool_calls))
    from app.db.models.chat_file import ChatFile
    query = query.options(selectinload(Message.files))
    query = query.order_by(Message.created_at.asc()).offset(skip).limit(limit)
    result = db.execute(query)
    return list(result.scalars().all())


def count_messages(db: Session, conversation_id: str) -> int:
    """Count messages in a conversation."""
    query = select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
    result = db.execute(query)
    return result.scalar() or 0


def create_message(
    db: Session,
    *,
    conversation_id: str,
    role: str,
    content: str,
    model_name: str | None = None,
    tokens_used: int | None = None,
) -> Message:
    """Create a new message."""
    message = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        model_name=model_name,
        tokens_used=tokens_used,
    )
    db.add(message)
    db.flush()
    db.refresh(message)

    # Update conversation's updated_at timestamp
    db.execute(
        sql_update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(updated_at=message.created_at)
    )

    return message


def delete_message(db: Session, message_id: str) -> bool:
    """Delete a message."""
    message = get_message_by_id(db, message_id)
    if message:
        db.delete(message)
        db.flush()
        return True


def count_user_messages(db: Session, conversation_id: str) -> int:
    """Count user messages in a conversation."""
    from sqlalchemy import func, select
    from app.db.models.conversation import Message
    stmt = select(func.count()).select_from(Message).where(
        Message.conversation_id == conversation_id,
        Message.role == "user",
    )
    return db.scalar(stmt) or 0
    return False


# ToolCall Operations


def get_tool_call_by_id(db: Session, tool_call_id: str) -> ToolCall | None:
    """Get tool call by ID."""
    return db.get(ToolCall, tool_call_id)


def get_tool_calls_by_message(
    db: Session,
    message_id: str,
) -> list[ToolCall]:
    """Get tool calls for a message."""
    query = (
        select(ToolCall)
        .where(ToolCall.message_id == message_id)
        .order_by(ToolCall.started_at.asc())
    )
    result = db.execute(query)
    return list(result.scalars().all())


def create_tool_call(
    db: Session,
    *,
    message_id: str,
    tool_call_id: str,
    tool_name: str,
    args: dict[str, Any],
    started_at: datetime,
) -> ToolCall:
    """Create a new tool call record."""
    import json

    tool_call = ToolCall(
        message_id=message_id,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        args=json.dumps(args),  # SQLite stores as JSON string
        started_at=started_at,
        status="running",
    )
    db.add(tool_call)
    db.flush()
    db.refresh(tool_call)
    return tool_call


def deserialize_tool_call_args(tool_call: ToolCall) -> dict[str, Any]:
    """Deserialize tool call args from JSON string (SQLite stores as TEXT)."""
    import json

    if isinstance(tool_call.args, str):
        try:
            result: dict[str, Any] = json.loads(tool_call.args)
            return result
        except (json.JSONDecodeError, TypeError):
            return {}
    return dict(tool_call.args) if isinstance(tool_call.args, dict) else {}


def complete_tool_call(
    db: Session,
    *,
    db_tool_call: ToolCall,
    result: str,
    completed_at: datetime,
    success: bool = True,
) -> ToolCall:
    """Mark a tool call as completed."""
    db_tool_call.result = result
    db_tool_call.completed_at = completed_at
    db_tool_call.status = "completed" if success else "failed"

    # Calculate duration
    if db_tool_call.started_at:
        delta = completed_at - db_tool_call.started_at
        db_tool_call.duration_ms = int(delta.total_seconds() * 1000)

    db.add(db_tool_call)
    db.flush()
    db.refresh(db_tool_call)
    return db_tool_call
