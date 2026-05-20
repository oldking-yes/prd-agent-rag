
"""Agent session management for WebSocket-based PRD analysis.

Handles the lifecycle of a single agent conversation session:
- Message processing and streaming
- Conversation persistence
- RAG-enhanced PRD generation
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket

from app.agents.assistant import PRDAgent, Deps
from app.agents.tools.rag_tool import search_knowledge_base
from app.core.config import settings
from app.db.models.user import User
from app.services.agent import AgentConnectionManager, send_event
from app.schemas.conversation import (
    ConversationCreate,
    ConversationUpdate,
    MessageCreate,
)

logger = logging.getLogger(__name__)


class AgentSession:
    """Manages a single PRD analysis conversation session."""

    def __init__(
        self,
        websocket: WebSocket,
        user: User,
    ):
        self.websocket = websocket
        self.user = user
        self.conversation_id: str | None = None
        self.db = None
        self.message_history: list[dict[str, str]] = []

    async def process_message(self, data: dict[str, Any]) -> None:
        """Process an incoming message from the WebSocket.

        Expected format:
        {
            "message": "user's product idea or answer",
            "conversation_id": "optional-uuid",
            "file_ids": [...]
        }
        """
        user_message = data.get("message", "")
        self.conversation_id = data.get("conversation_id")
        file_ids = data.get("file_ids", [])

        if not user_message.strip():
            return

        # Persist user message
        await self._persist_user_message(user_message, file_ids)

        # Send typing indicator
        await send_event(self.websocket, "status", {"status": "thinking"})

        # Run the PRD agent
        try:
            agent = PRDAgent()
            deps = Deps(
                user_id=str(self.user.id) if self.user else None,
                user_name=self.user.full_name if self.user else None,
            )

            # Stream agent response
            full_response = ""
            await send_event(self.websocket, "status", {"status": "generating"})

            async with agent.agent.iter(
                user_message,
                deps=deps,
                message_history=agent._build_model_history(self.message_history),
            ) as run:
                async for event in run:
                    # Handle text streaming
                    if hasattr(event, "parts"):
                        for part in event.parts:
                            if hasattr(part, "content") and part.content:
                                full_response += part.content
                                await send_event(
                                    self.websocket,
                                    "text",
                                    {"content": part.content},
                                )
                            # Handle tool calls
                            if hasattr(part, "tool_name"):
                                await send_event(
                                    self.websocket,
                                    "tool_call",
                                    {
                                        "tool_name": part.tool_name,
                                        "args": getattr(part, "args", {}),
                                    },
                                )

            # Persist assistant response
            if full_response:
                await self._persist_assistant_message(full_response)

                # If this is a new conversation, update the title
                title = self._extract_title(full_response, user_message)
                if self.conversation_id:
                    await self._update_conversation_title(title)

            await send_event(self.websocket, "done", {})

        except Exception as e:
            logger.error(f"Agent error: {e}", exc_info=True)
            await send_event(
                self.websocket,
                "error",
                {"message": f"Analysis failed: {str(e)}"},
            )

    async def _persist_user_message(
        self, content: str, file_ids: list[str] | None = None
    ) -> None:
        """Save user message to conversation history."""
        self.message_history.append({"role": "user", "content": content})

        if not self.db:
            return

        try:
            from app.repositories import conversation_repo
            from app.repositories import chat_file_repo

            # Create conversation if needed
            if not self.conversation_id:
                conv = conversation_repo.create_conversation(
                    self.db,
                    user_id=str(self.user.id) if self.user else None,
                    title="PRD Analysis",
                )
                self.conversation_id = conv.id

            # Create message
            msg = conversation_repo.create_message(
                self.db,
                conversation_id=self.conversation_id,
                role="user",
                content=content,
            )

            # Link files
            if file_ids:
                chat_file_repo.link_to_message(
                    self.db, message_id=msg.id, file_ids=file_ids
                )

            self.db.commit()
        except Exception as e:
            logger.warning(f"Failed to persist user message: {e}")
            self.db.rollback()

    async def _persist_assistant_message(self, content: str) -> None:
        """Save assistant message to conversation history."""
        self.message_history.append({"role": "assistant", "content": content})

        if not self.db or not self.conversation_id:
            return

        try:
            from app.repositories import conversation_repo

            conversation_repo.create_message(
                self.db,
                conversation_id=self.conversation_id,
                role="assistant",
                content=content,
                model_name=settings.AI_MODEL,
            )
            self.db.commit()
        except Exception as e:
            logger.warning(f"Failed to persist assistant message: {e}")
            self.db.rollback()

    async def _update_conversation_title(self, title: str | None) -> None:
        """Update conversation title based on content."""
        if not title or not self.db or not self.conversation_id:
            return

        try:
            from app.repositories import conversation_repo

            conversation = conversation_repo.get_conversation_by_id(
                self.db, self.conversation_id
            )
            if conversation:
                conversation_repo.update_conversation(
                    self.db,
                    db_conversation=conversation,
                    update_data={"title": title},
                )
                self.db.commit()
        except Exception as e:
            logger.warning(f"Failed to update title: {e}")
            self.db.rollback()

    @staticmethod
    def _extract_title(full_response: str, user_message: str) -> str:
        """Extract a short title from the conversation."""
        # Try to find the product name from the PRD
        import re

        name_match = re.search(
            r"(?:Product Name|product name)\s*[:：]\s*(.+?)[\n\r]",
            full_response,
            re.IGNORECASE,
        )
        if name_match:
            title = name_match.group(1).strip()
            if len(title) > 100:
                title = title[:100]
            return title

        # Fall back to first line of user message
        first_line = user_message.strip().split("\n")[0]
        return first_line[:100] if len(first_line) > 100 else first_line
