
"""Conversation service (SQLite sync).

Contains business logic for conversation, message, and tool call operations.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import select, func, case

from app.core.exceptions import NotFoundError
from app.db.models.conversation import Conversation, Message, ToolCall
from app.db.models.user import User
from app.repositories import conversation_repo
from app.schemas.conversation import (
    ConversationCreate,
    ConversationUpdate,
    MessageCreate,
    MessageRead,
    ToolCallCreate,
    ToolCallComplete,
)

logger = logging.getLogger(__name__)


class ConversationService:
    """Service for conversation-related business logic."""

    def __init__(self, db: Session):
        self.db = db

    # Conversation Methods

    def get_conversation(
        self,
        conversation_id: str,
        *,
        include_messages: bool = False,
        user_id: str | None = None,
    ) -> Conversation:
        """Get conversation by ID.

        Raises:
            NotFoundError: If conversation does not exist or user has no access.
        """
        conversation = conversation_repo.get_conversation_by_id(
            self.db, conversation_id, include_messages=include_messages
        )
        if not conversation:
            raise NotFoundError(
                message="Conversation not found",
                details={"conversation_id": conversation_id},
            )
        if (
            user_id is not None
            and hasattr(conversation, "user_id")
            and conversation.user_id is not None
            and str(conversation.user_id) != str(user_id)
        ):
            raise NotFoundError(
                message="Conversation not found",
                details={"conversation_id": conversation_id},
            )
        return conversation

    def list_conversations(
        self,
        user_id: str | None = None,
        *,
        skip: int = 0,
        limit: int = 50,
        include_archived: bool = False,
    ) -> tuple[list[Conversation], int]:
        """List conversations with pagination."""
        items = conversation_repo.get_conversations_by_user(
            self.db,
            user_id=user_id,
            skip=skip,
            limit=limit,
            include_archived=include_archived,
        )
        total = conversation_repo.count_conversations(
            self.db,
            user_id=user_id,
            include_archived=include_archived,
        )
        return items, total

    def create_conversation(
        self,
        data: ConversationCreate,
    ) -> Conversation:
        """Create a new conversation."""
        return conversation_repo.create_conversation(
            self.db,
            user_id=data.user_id,
            title=data.title,
        )

    def update_conversation(
        self,
        conversation_id: str,
        data: ConversationUpdate,
        user_id: str | None = None,
    ) -> Conversation:
        """Update a conversation."""
        conversation = self.get_conversation(
            conversation_id,
            user_id=user_id,
        )
        update_data = data.model_dump(exclude_unset=True)
        if "active_knowledge_base_ids" in update_data:
            import json
            ids = update_data["active_knowledge_base_ids"]
            update_data["active_knowledge_base_ids"] = json.dumps([str(kb_id) for kb_id in ids]) if ids is not None else None
        return conversation_repo.update_conversation(
            self.db, db_conversation=conversation, update_data=update_data
        )

    def archive_conversation(
        self,
        conversation_id: str,
        user_id: str | None = None,
    ) -> Conversation:
        """Archive a conversation."""
        self.get_conversation(conversation_id, user_id=user_id)
        conversation = conversation_repo.archive_conversation(self.db, conversation_id)
        if not conversation:
            raise NotFoundError(
                message="Conversation not found",
                details={"conversation_id": conversation_id},
            )
        return conversation

    def delete_conversation(
        self,
        conversation_id: str,
        user_id: str | None = None,
    ) -> bool:
        """Delete a conversation."""
        self.get_conversation(conversation_id, user_id=user_id)
        deleted = conversation_repo.delete_conversation(self.db, conversation_id)
        if not deleted:
            raise NotFoundError(
                message="Conversation not found",
                details={"conversation_id": conversation_id},
            )
        return True

    # Message Methods

    def get_message(self, message_id: str) -> Message:
        """Get message by ID."""
        message = conversation_repo.get_message_by_id(self.db, message_id)
        if not message:
            raise NotFoundError(
                message="Message not found",
                details={"message_id": message_id},
            )
        return message

    def list_messages(
        self,
        conversation_id: str,
        *,
        skip: int = 0,
        limit: int = 100,
        include_tool_calls: bool = False,
        user_id: str | None = None,
    ) -> tuple[list[Message], int]:
        """List messages in a conversation."""
        self.get_conversation(conversation_id)
        items = conversation_repo.get_messages_by_conversation(
            self.db,
            conversation_id,
            skip=skip,
            limit=limit,
            include_tool_calls=include_tool_calls,
        )
        total = conversation_repo.count_messages(self.db, conversation_id)
        return list(items), total

    def add_message(
        self,
        conversation_id: str,
        data: MessageCreate,
    ) -> Message:
        """Add a message to a conversation."""
        self.get_conversation(conversation_id)
        return conversation_repo.create_message(
            self.db,
            conversation_id=conversation_id,
            role=data.role,
            content=data.content,
            model_name=data.model_name,
            tokens_used=data.tokens_used,
        )

    # Tool Call Methods

    def get_tool_call(self, tool_call_id: str) -> ToolCall:
        """Get tool call by ID."""
        tool_call = conversation_repo.get_tool_call_by_id(self.db, tool_call_id)
        if not tool_call:
            raise NotFoundError(
                message="Tool call not found",
                details={"tool_call_id": tool_call_id},
            )
        return tool_call

    def list_tool_calls(self, message_id: str) -> list[ToolCall]:
        """List tool calls for a message."""
        self.get_message(message_id)
        return conversation_repo.get_tool_calls_by_message(self.db, message_id)

    def start_tool_call(
        self,
        message_id: str,
        data: ToolCallCreate,
    ) -> ToolCall:
        """Record the start of a tool call."""
        self.get_message(message_id)
        return conversation_repo.create_tool_call(
            self.db,
            message_id=message_id,
            tool_call_id=data.tool_call_id,
            tool_name=data.tool_name,
            args=data.args,
            started_at=data.started_at or datetime.now(UTC),
        )

    def complete_tool_call(
        self,
        tool_call_id: str,
        data: ToolCallComplete,
    ) -> ToolCall:
        """Mark a tool call as completed."""
        tool_call = self.get_tool_call(tool_call_id)
        return conversation_repo.complete_tool_call(
            self.db,
            db_tool_call=tool_call,
            result=data.result,
            completed_at=data.completed_at or datetime.now(UTC),
            success=data.success,
        )

    def link_files_to_message(self, message_id: str, file_ids: list[str]) -> None:
        """Link uploaded chat files to a message."""
        from app.repositories import chat_file_repo
        chat_file_repo.link_to_message(self.db, message_id=message_id, file_ids=file_ids)

    def list_attached_files(self, file_ids: list[str]) -> list[Any]:
        """Batch-load chat files referenced as message attachments."""
        from app.repositories import chat_file_repo
        return chat_file_repo.get_many(self.db, file_ids)
