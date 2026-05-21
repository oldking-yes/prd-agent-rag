"""API dependencies.

Dependency injection factories for services, repositories, and authentication.
"""
# ruff: noqa: I001, E402 - Imports structured for Jinja2 template conditionals

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

from app.core.config import settings
from app.db.session import get_db_session
from sqlalchemy.orm import Session

DBSession = Annotated[Session, Depends(get_db_session)]


# === Service Dependencies ===

from app.services.user import UserService
from app.services.conversation import ConversationService


def get_user_service(db: DBSession) -> UserService:
    """Create UserService instance with database session."""
    return UserService(db)


UserSvc = Annotated[UserService, Depends(get_user_service)]


def get_conversation_service(db: DBSession) -> ConversationService:
    """Create ConversationService instance with database session."""
    return ConversationService(db)


ConversationSvc = Annotated[ConversationService, Depends(get_conversation_service)]

from app.services.rag_document import RAGDocumentService


def get_rag_document_service(db: DBSession) -> RAGDocumentService:
    """Create RAGDocumentService instance with database session."""
    return RAGDocumentService(db)


RAGDocumentSvc = Annotated[RAGDocumentService, Depends(get_rag_document_service)]

from app.services.file_upload import FileUploadService


def get_file_upload_service(db: DBSession) -> FileUploadService:
    """Create FileUploadService instance with database session."""
    return FileUploadService(db)


FileUploadSvc = Annotated[FileUploadService, Depends(get_file_upload_service)]


# === Authentication Dependencies ===

from app.core.exceptions import AuthenticationError, AuthorizationError
from app.db.models.user import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    user_service: UserSvc,
) -> User:
    """Get current authenticated user from JWT token."""
    from app.core.security import verify_token

    payload = verify_token(token)
    if payload is None:
        raise AuthenticationError(message="Invalid or expired token")

    if payload.get("type") != "access":
        raise AuthenticationError(message="Invalid token type")

    user_id = payload.get("sub")
    if user_id is None:
        raise AuthenticationError(message="Invalid token payload")

    # Guest users: return a lightweight user object without DB lookup
    if payload.get("is_guest"):
        from datetime import datetime, UTC
        return User(
            id=str(user_id),
            email="guest@railway.app",
            full_name="游客",
            is_active=True,
            role="user",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    user = await user_service.get_by_id(user_id)
    if not user.is_active:
        raise AuthenticationError(message="User account is disabled")

    return user


class RoleChecker:
    """Dependency class for role-based access control."""

    def __init__(self, required_role: UserRole) -> None:
        self.required_role = required_role

    def __call__(
        self,
        user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if not user.has_role(self.required_role):
            raise AuthorizationError(
                message=f"Role '{self.required_role.value}' required for this action"
            )
        return user


def get_current_active_superuser(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not current_user.has_role(UserRole.ADMIN):
        raise AuthorizationError(message="Admin privileges required")
    return current_user


# Type aliases for dependency injection
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentSuperuser = Annotated[User, Depends(get_current_active_superuser)]
CurrentAdmin = Annotated[User, Depends(RoleChecker(UserRole.ADMIN))]


# WebSocket authentication dependency
from fastapi import WebSocket


_WS_TOKEN_PROTOCOL_PREFIX = "access_token."


def _extract_ws_auth(websocket: WebSocket) -> tuple[str | None, str | None]:
    """Parse Sec-WebSocket-Protocol header for an auth token + app subprotocol."""
    raw = websocket.headers.get("sec-websocket-protocol") or ""
    token: str | None = None
    app_subprotocol: str | None = None
    for proto in (p.strip() for p in raw.split(",") if p.strip()):
        if proto.startswith(_WS_TOKEN_PROTOCOL_PREFIX):
            token = proto[len(_WS_TOKEN_PROTOCOL_PREFIX):]
        elif app_subprotocol is None:
            app_subprotocol = proto
    return token, app_subprotocol


async def get_current_user_ws(
    websocket: WebSocket,
    access_token: str | None = None,
) -> User:
    """Authenticate a WebSocket connection."""
    from uuid import UUID

    from app.core.security import verify_token

    subprotocol_token, app_subprotocol = _extract_ws_auth(websocket)
    websocket.state.accept_subprotocol = app_subprotocol

    auth_token = subprotocol_token or access_token

    if not auth_token:
        await websocket.close(code=4001, reason="Missing authentication token")
        raise AuthenticationError(message="Missing authentication token")

    payload = verify_token(auth_token)
    if payload is None:
        await websocket.close(code=4001, reason="Invalid or expired token")
        raise AuthenticationError(message="Invalid or expired token")

    if payload.get("type") != "access":
        await websocket.close(code=4001, reason="Invalid token type")
        raise AuthenticationError(message="Invalid token type")

    user_id = payload.get("sub")
    if user_id is None:
        await websocket.close(code=4001, reason="Invalid token payload")
        raise AuthenticationError(message="Invalid token payload")

    from contextlib import contextmanager

    with contextmanager(get_db_session)() as db:
        user_service = UserService(db)
        user = await user_service.get_by_id(user_id)

        if not user.is_active:
            await websocket.close(code=4001, reason="User account is disabled")
            raise AuthenticationError(message="User account is disabled")

        db.refresh(user)
        db.expunge(user)
        return user


# === RAG Service Dependencies (lazy imports to avoid chromadb crash at module level) ===

from fastapi import Request
from app.core.config import settings
from app.services.rag.embeddings import EmbeddingService


def get_embedding_service(request: Request) -> EmbeddingService:
    """Get embedding service from lifespan state or create new if not available."""
    if request and hasattr(request.state, "embedding_service"):
        return request.state.embedding_service
    return EmbeddingService(settings=settings.rag)


EmbeddingSvc = Annotated[EmbeddingService, Depends(get_embedding_service)]


def get_vectorstore(request: Request, embedder: EmbeddingSvc) -> BaseVectorStore:
    """Get vector store client from lifespan state or create new."""
    from app.services.rag.vectorstore import BaseVectorStore, ChromaVectorStore
    if request and hasattr(request.state, "vector_store"):
        return request.state.vector_store
    return ChromaVectorStore(settings=settings.rag, embedding_service=embedder)


VectorStoreSvc = Annotated['BaseVectorStore', Depends(get_vectorstore)]


def get_retrieval_service(vector_store: VectorStoreSvc) -> 'RetrievalService':
    """Create RetrievalService instance."""
    from app.services.rag.retrieval import RetrievalService
    return RetrievalService(vector_store=vector_store, settings=settings.rag)


RetrievalSvc = Annotated['RetrievalService', Depends(get_retrieval_service)]


def get_document_processor() -> 'DocumentProcessor':
    """Create DocumentProcessor instance."""
    from app.services.rag.documents import DocumentProcessor
    return DocumentProcessor(settings=settings.rag)


DocumentProcessorSvc = Annotated['DocumentProcessor', Depends(get_document_processor)]


def get_ingestion_service(
    processor: DocumentProcessorSvc,
    vector_store: VectorStoreSvc,
) -> 'IngestionService':
    """Create IngestionService instance."""
    from app.services.rag.ingestion import IngestionService
    return IngestionService(processor=processor, vector_store=vector_store)


IngestionSvc = Annotated['IngestionService', Depends(get_ingestion_service)]
