
"""User repository (SQLite sync).

Contains only database operations. Business logic (password hashing,
validation) is handled by UserService in app/services/user.py.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.user import User


def get_by_id(db: Session, user_id: str) -> User | None:
    """Get user by ID."""
    return db.get(User, user_id)


def get_by_email(db: Session, email: str) -> User | None:
    """Get user by email."""
    result = db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


def get_multi(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 100,
) -> list[User]:
    """Get multiple users with pagination."""
    result = db.execute(select(User).offset(skip).limit(limit))
    return list(result.scalars().all())


def list_query() -> Any:
    """Return the SQL Select for listing users (used by paginate)."""
    return select(User)


def create(
    db: Session,
    *,
    email: str,
    hashed_password: str | None,
    full_name: str | None = None,
    is_active: bool = True,
    role: str = "user",
    is_app_admin: bool = False,
) -> User:
    """Create a new user.

    Note: Password should already be hashed by the service layer.
    """
    user = User(
        email=email,
        hashed_password=hashed_password,
        full_name=full_name,
        is_active=is_active,
        role=role,
        is_app_admin=is_app_admin,
    )
    db.add(user)
    db.flush()
    db.refresh(user)
    return user


def update(
    db: Session,
    *,
    db_user: User,
    update_data: dict[str, Any],
) -> User:
    """Update a user.

    Note: If password needs updating, it should already be hashed.
    """
    for field, value in update_data.items():
        setattr(db_user, field, value)

    db.add(db_user)
    db.flush()
    db.refresh(db_user)
    return db_user


def delete(db: Session, user_id: str) -> User | None:
    """Delete a user."""
    user = get_by_id(db, user_id)
    if user:
        db.delete(user)
        db.flush()
    return user


def delete_non_admins(db: Session) -> int:
    """Bulk-delete users without the admin role. Returns affected row count."""
    from sqlalchemy import delete as sql_delete

    result = db.execute(sql_delete(User).where(User.role != "admin"))
    db.flush()
    return result.rowcount  # type: ignore[no-any-return, attr-defined]


def has_any(db: Session) -> bool:
    """Return True if at least one user exists."""
    result = db.execute(select(User).limit(1))
    return result.scalars().first() is not None


def admin_list_with_counts(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 50,
    search: str | None = None,
    sort_by: str = "created_at",
    sort_dir: str = "desc",
) -> tuple[list[tuple[User, int]], int]:
    """Admin: list users with their conversation counts.

    Returns list of (user, conversation_count) tuples and total count.
    """
    from sqlalchemy import func
    from app.db.models.conversation import Conversation

    conv_count_col = func.count(Conversation.id).label("conversation_count")
    query = (
        select(User, conv_count_col)
        .outerjoin(Conversation, Conversation.user_id == User.id)
        .group_by(User.id)
    )
    count_query = select(func.count()).select_from(User)

    if search:
        condition = User.email.ilike(f"%{search}%") | User.full_name.ilike(f"%{search}%")
        query = query.where(condition)
        count_query = count_query.where(condition)

    sort_columns = {
        "email": User.email,
        "full_name": User.full_name,
        "created_at": User.created_at,
        "conversations": conv_count_col,
    }
    sort_col = sort_columns.get(sort_by, User.created_at)
    sort_col = sort_col.desc() if sort_dir == "desc" else sort_col.asc()
    query = query.order_by(sort_col).offset(skip).limit(limit)

    total = db.scalar(count_query) or 0
    rows = db.execute(query).all()
    return [(user, count) for user, count in rows], total
