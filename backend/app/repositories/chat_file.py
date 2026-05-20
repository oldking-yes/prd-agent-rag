
"""Chat file repository (SQLite sync).

Contains database operations for ChatFile entities.
"""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.chat_file import ChatFile


def get_by_id(db: Session, file_id: str) -> ChatFile | None:
    """Get a chat file by ID."""
    return db.get(ChatFile, file_id)


def get_many(db: Session, file_ids: Iterable[str]) -> list[ChatFile]:
    """Batch-load multiple chat files by IDs."""
    ids = list(file_ids)
    if not ids:
        return []
    result = db.execute(select(ChatFile).where(ChatFile.id.in_(ids)))
    return list(result.scalars().all())


def link_to_message(db: Session, *, message_id: str, file_ids: Iterable[str]) -> None:
    """Link multiple chat files to a message by setting message_id on each."""
    from sqlalchemy import update as sql_update

    ids = list(file_ids)
    if not ids:
        return
    db.execute(sql_update(ChatFile).where(ChatFile.id.in_(ids)).values(message_id=message_id))
    db.flush()


def create(
    db: Session,
    *,
    user_id: str,
    filename: str,
    mime_type: str,
    size: int,
    storage_path: str,
    file_type: str,
    parsed_content: str | None = None,
) -> ChatFile:
    """Create a new chat file record."""
    chat_file = ChatFile(
        user_id=user_id,
        filename=filename,
        mime_type=mime_type,
        size=size,
        storage_path=storage_path,
        file_type=file_type,
        parsed_content=parsed_content,
    )
    db.add(chat_file)
    db.flush()
    return chat_file
