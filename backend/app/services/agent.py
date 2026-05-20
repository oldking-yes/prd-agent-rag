"""Shared agent service utilities.

Houses framework-agnostic helpers used by every WebSocket agent route:
  - ``AgentConnectionManager`` + ``send_event`` — WebSocket fan-out
  - ``build_message_history`` — convert dicts to provider-native messages
  - ``persist_user_turn`` / ``persist_assistant_turn`` — DB persistence
  - ``resolve_kb_collections`` — Teams+RAG collection lookup
  - ``normalize_tool_args`` / ``truncate_title`` — small utilities

Framework-specific concerns (multimodal input, streaming events) stay in the route.
"""

import logging
from typing import Any
import json
from datetime import UTC, datetime
from contextlib import contextmanager

from fastapi import WebSocket, WebSocketDisconnect
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    UserPromptPart,
)
from app.api.deps import get_conversation_service
from app.schemas.conversation import (
    ConversationCreate,
    ConversationUpdate,
    MessageCreate,
    ToolCallComplete,
    ToolCallCreate,
)
from app.db.session import get_db_context, get_db_session

logger = logging.getLogger(__name__)


async def send_event(websocket: WebSocket, event_type: str, data: Any) -> bool:
    """Send a JSON event to a WebSocket client.

    Returns True if sent successfully, False if the connection is already closed.
    """
    try:
        await websocket.send_json({"type": event_type, "data": data})
        return True
    except (WebSocketDisconnect, RuntimeError):
        return False


class AgentConnectionManager:
    """WebSocket connection manager for AI agent."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and store a new WebSocket connection."""
        # Echo back the client's Sec-WebSocket-Protocol so the browser
        # handshake completes. The auth dependency already validated the token.
        echo = None
        raw = websocket.headers.get("sec-websocket-protocol", "")
        if raw:
            for proto in (p.strip() for p in raw.split(",") if p.strip()):
                echo = proto
                break
        await websocket.accept(subprotocol=echo)
        self.active_connections.append(websocket)
        logger.info(f"Agent WebSocket connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"Agent WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def send_event(self, websocket: WebSocket, event_type: str, data: Any) -> bool:
        """Forward to the module-level :func:`send_event`."""
        return await send_event(websocket, event_type, data)


def build_message_history(history: list[dict[str, str]]) -> list[ModelRequest | ModelResponse]:
    """Convert conversation history to PydanticAI message format."""
    model_history: list[ModelRequest | ModelResponse] = []

    for msg in history:
        if msg["role"] == "user":
            model_history.append(ModelRequest(parts=[UserPromptPart(content=msg["content"])]))
        elif msg["role"] == "assistant":
            model_history.append(ModelResponse(parts=[TextPart(content=msg["content"])]))
        elif msg["role"] == "system":
            model_history.append(ModelRequest(parts=[SystemPromptPart(content=msg["content"])]))

    return model_history


def truncate_title(text: str, limit: int = 50) -> str:
    """Return text truncated to ``limit`` characters."""
    return text[:limit] if len(text) > limit else text


async def persist_user_turn(
    user: Any,
    user_message: str,
    file_ids: list[Any],
    requested_conversation_id: str | None,
    current_conversation_id: str | None,
) -> tuple[str | None, bool, str | None]:
    """Resolve the conversation, persist the user message, and link any uploaded files.

    Returns ``(conversation_id, was_newly_created, organization_id)``. When
    ``was_newly_created`` is True the caller should emit a ``conversation_created``
    WebSocket event. ``organization_id`` is the conversation's owning org (the user's
    Personal org for new conversations) so usage events can be billed correctly;
    None when teams are disabled or no org context is available.
    """
    newly_created = False
    organization_id: str | None = None
    try:
        with contextmanager(get_db_session)() as db:
            conv_service = get_conversation_service(db)

            if requested_conversation_id:
                current_conversation_id = requested_conversation_id
                conv = conv_service.get_conversation(requested_conversation_id, user_id=str(user.id))
                if not conv.title and user_message:
                    conv_service.update_conversation(
                        requested_conversation_id,
                        ConversationUpdate(title=truncate_title(user_message)),
                        user_id=str(user.id),
                    )
            elif not current_conversation_id:
                conversation = conv_service.create_conversation(
                    ConversationCreate(
                        user_id=str(user.id),
                        title=truncate_title(user_message),
                    )
                )
                current_conversation_id = str(conversation.id)
                newly_created = True

            user_msg = conv_service.add_message(
                current_conversation_id,
                MessageCreate(role="user", content=user_message),
            )
            if file_ids:
                try:
                    conv_service.link_files_to_message(user_msg.id, file_ids)
                except Exception as e:
                    logger.warning(f"Failed to link files: {e}")
    except Exception as e:
        logger.warning(f"Failed to persist conversation: {e}")

    return current_conversation_id, newly_created, organization_id


def normalize_tool_args(args: Any) -> dict[str, Any]:
    """Coerce a tool-call ``args`` payload to a dict (handles JSON strings + None)."""
    if isinstance(args, str):
        return json.loads(args) if args.strip() else {}
    if args is None:
        return {}
    return args


async def persist_assistant_turn(
    conversation_id: str,
    output: str,
    model_name: str | None,
    collected_tool_calls: list[dict[str, Any]],
) -> str | None:
    """Persist the assistant message and any tool calls. Returns the saved message id."""
    try:
        with contextmanager(get_db_session)() as db:
            conv_service = get_conversation_service(db)
            assistant_msg = conv_service.add_message(
                conversation_id,
                MessageCreate(role="assistant", content=output, model_name=model_name),
            )
            for tc in collected_tool_calls:
                try:
                    tc_obj = conv_service.start_tool_call(
                        assistant_msg.id,
                        ToolCallCreate(
                            tool_call_id=tc["tool_call_id"],
                            tool_name=tc["tool_name"],
                            args=normalize_tool_args(tc.get("args")),
                            started_at=datetime.now(UTC),
                        ),
                    )
                    if tc.get("result"):
                        conv_service.complete_tool_call(
                            tc_obj.id,
                            ToolCallComplete(
                                result=tc["result"],
                                completed_at=datetime.now(UTC),
                                success=True,
                            ),
                        )
                except Exception as e:
                    logger.warning(f"Failed to persist tool call: {e}")
            return str(assistant_msg.id)
    except Exception as e:
        logger.warning(f"Failed to persist assistant response: {e}")
        return None
