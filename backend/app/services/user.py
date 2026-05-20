"""User service.

Contains business logic for user operations.
"""

import logging
from typing import Any
from uuid import UUID
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AlreadyExistsError, AuthenticationError, NotFoundError
from app.core.security import (
    create_magic_link_token,
    create_password_reset_token,
    get_password_hash,
    verify_password,
    verify_special_token,
)
from app.db.models.user import User, UserRole
from app.repositories import user_repo
from app.schemas.user import UserCreate, UserUpdate

logger = logging.getLogger(__name__)


class UserService:
    """Service for user-related business logic."""

    def __init__(self, db: Session):
        self.db = db

    async def _repo(self, func, /, *args, **kwargs):
        """Invoke a sync SQLite repo function from async context."""
        return func(self.db, *args, **kwargs)

    async def get_by_id(self, user_id: UUID) -> User:
        """Get user by ID."""
        user = await self._repo(user_repo.get_by_id, user_id)
        if not user:
            raise NotFoundError(
                message="User not found",
                details={"user_id": user_id},
            )
        return user

    async def get_by_email(self, email: str) -> User | None:
        """Get user by email. Returns None if not found."""
        return await self._repo(user_repo.get_by_email, email)

    async def get_multi(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[User]:
        """Get multiple users with pagination."""
        return await self._repo(user_repo.get_multi, skip=skip, limit=limit)

    async def list_paginated(self) -> Any:
        """Return paginated user list (fastapi-pagination Page)."""
        from fastapi_pagination.ext.sqlalchemy import paginate
        return await paginate(self.db, user_repo.list_query())

    async def has_any(self) -> bool:
        """Return True if at least one user exists."""
        return await self._repo(user_repo.has_any)

    async def register(self, user_in: UserCreate) -> User:
        """Register a new user.

        The very first user to register is auto-promoted to app-admin.

        Raises:
            AlreadyExistsError: If email is already registered.
        """
        existing = await self._repo(user_repo.get_by_email, user_in.email)
        if existing:
            raise AlreadyExistsError(
                message="Email already registered",
                details={"email": user_in.email},
            )
        existing_count = self.db.execute(select(func.count()).select_from(User)).scalar_one()
        is_first_user = existing_count == 0

        hashed_password = get_password_hash(user_in.password)
        user = await self._repo(
            user_repo.create,
            email=user_in.email,
            hashed_password=hashed_password,
            full_name=user_in.full_name,
            role=UserRole.ADMIN.value if is_first_user else user_in.role.value,
            is_app_admin=is_first_user,
        )
        return user

    async def authenticate(self, email: str, password: str) -> User:
        """Authenticate user by email and password."""
        user = await self._repo(user_repo.get_by_email, email)
        if (
            not user
            or not user.hashed_password
            or not verify_password(password, user.hashed_password)
        ):
            raise AuthenticationError(message="Invalid email or password")
        if not user.is_active:
            raise AuthenticationError(message="User account is disabled")
        return user

    async def update(self, user_id: UUID, user_in: UserUpdate) -> User:
        """Update user."""
        user = await self.get_by_id(user_id)
        update_data = user_in.model_dump(exclude_unset=True)
        if "password" in update_data:
            update_data["hashed_password"] = get_password_hash(update_data.pop("password"))
        return await self._repo(user_repo.update, db_user=user, update_data=update_data)

    async def delete(self, user_id: UUID) -> User:
        """Delete user."""
        user = await self._repo(user_repo.delete, user_id)
        if not user:
            raise NotFoundError(
                message="User not found",
                details={"user_id": str(user_id)},
            )
        return user

    async def issue_password_reset_token(self, email: str) -> tuple[User, str] | None:
        """Issue a short-lived JWT for password reset."""
        user = await self._repo(user_repo.get_by_email, email)
        if user is None or not user.is_active:
            return None
        token = create_password_reset_token(subject=str(user.id))
        return user, token

    async def confirm_password_reset(self, token: str, new_password: str) -> User:
        """Verify the reset token and set a new password."""
        payload = verify_special_token(token, expected_type="password_reset")
        if payload is None or "sub" not in payload:
            raise AuthenticationError(message="Reset link is invalid or has expired")
        try:
            user_id = UUID(str(payload["sub"]))
        except (TypeError, ValueError) as exc:
            raise AuthenticationError(
                message="Reset link is invalid or has expired"
            ) from exc

        user = await self.get_by_id(user_id)
        if not user.is_active:
            raise AuthenticationError(message="Account is disabled")

        await self._repo(
            user_repo.update,
            db_user=user,
            update_data={"hashed_password": get_password_hash(new_password)},
        )
        return user

    async def issue_magic_link_token(self, email: str) -> tuple[User, str] | None:
        """Issue a magic link token for passwordless sign-in."""
        user = await self._repo(user_repo.get_by_email, email)
        if user is None or not user.is_active:
            return None
        token = create_magic_link_token(subject=str(user.id))
        return user, token

    async def consume_magic_link_token(self, token: str) -> User:
        """Verify the magic-link token and return the user."""
        payload = verify_special_token(token, expected_type="magic_link")
        if payload is None or "sub" not in payload:
            raise AuthenticationError(message="Magic link is invalid or has expired")
        try:
            user_id = UUID(str(payload["sub"]))
        except (TypeError, ValueError) as exc:
            raise AuthenticationError(
                message="Magic link is invalid or has expired"
            ) from exc

        user = await self.get_by_id(user_id)
        if not user.is_active:
            raise AuthenticationError(message="Account is disabled")
        return user
