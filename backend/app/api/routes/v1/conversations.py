"""Conversation API routes for AI chat persistence."""
from typing import Any

from fastapi import APIRouter, Query, status

from app.api.deps import ConversationSvc, CurrentUser
from app.schemas.conversation import (
    ConversationCreate,
    ConversationList,
    ConversationRead,
    ConversationReadWithMessages,
    ConversationUpdate,
    MessageCreate,
    MessageList,
    MessageRead,
)

router = APIRouter()


@router.get("", response_model=ConversationList)
def list_conversations(
    conversation_service: ConversationSvc,
    current_user: CurrentUser,
    skip: int = Query(0, ge=0, description="Number of conversations to skip"),
    limit: int = Query(50, ge=1, le=100, description="Maximum conversations to return"),
    include_archived: bool = Query(False, description="Include archived conversations"),
) -> Any:
    """List conversations for the current user."""
    items, total = conversation_service.list_conversations(
        user_id=str(current_user.id),
        skip=skip,
        limit=limit,
        include_archived=include_archived,
    )
    return ConversationList(items=items, total=total)


@router.post("", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
def create_conversation(
    conversation_service: ConversationSvc,
    current_user: CurrentUser,
    data: ConversationCreate | None = None,
) -> Any:
    """Create a new conversation."""
    if data is None:
        data = ConversationCreate()
    data = data.model_copy(update={"user_id": str(current_user.id)})
    return conversation_service.create_conversation(data)


@router.get("/{conversation_id}", response_model=ConversationReadWithMessages)
def get_conversation(
    conversation_id: str,
    conversation_service: ConversationSvc,
    current_user: CurrentUser,
) -> Any:
    """Get a conversation with all its messages."""
    return conversation_service.get_conversation(
        conversation_id, include_messages=True,
        user_id=str(current_user.id),
    )


@router.patch("/{conversation_id}", response_model=ConversationRead)
def update_conversation(
    conversation_id: str,
    data: ConversationUpdate,
    conversation_service: ConversationSvc,
    current_user: CurrentUser,
) -> Any:
    """Update a conversation's title or archived status."""
    return conversation_service.update_conversation(
        conversation_id, data,
        user_id=str(current_user.id),
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_conversation(
    conversation_id: str,
    conversation_service: ConversationSvc,
    current_user: CurrentUser,
) -> None:
    """Delete a conversation and all its messages."""
    conversation_service.delete_conversation(
        conversation_id,
        user_id=str(current_user.id),
    )


@router.get("/{conversation_id}/messages", response_model=MessageList)
def list_messages(
    conversation_id: str,
    conversation_service: ConversationSvc,
    current_user: CurrentUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> Any:
    """List messages in a conversation."""
    items, total = conversation_service.list_messages(
        conversation_id,
        skip=skip,
        limit=limit,
        include_tool_calls=True,
        user_id=str(current_user.id),
    )
    return MessageList(items=items, total=total)


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
)
def add_message(
    conversation_id: str,
    data: MessageCreate,
    conversation_service: ConversationSvc,
    current_user: CurrentUser,
) -> Any:
    """Add a message to a conversation."""
    return conversation_service.add_message(conversation_id, data)
