
"""File upload and download endpoints for chat attachments."""

import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.deps import CurrentUser, FileUploadSvc
from app.core.exceptions import NotFoundError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/files", tags=["files"])

# Local file storage
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


class FileInfo(BaseModel):
    id: str
    filename: str
    mime_type: str
    size: int
    file_type: str
    created_at: datetime | None = None
    user_id: str | None = None


class FileUploadResponse(BaseModel):
    id: str
    filename: str
    mime_type: str
    size: int
    file_type: str


def _save_file(user_id: str, filename: str, data: bytes) -> str:
    """Save file to local disk and return relative path."""
    user_dir = UPLOAD_DIR / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    file_id = str(uuid.uuid4())
    safe_name = f"{file_id}_{Path(filename).name}"
    file_path = user_dir / safe_name
    file_path.write_bytes(data)
    return str(file_path.relative_to(UPLOAD_DIR))


def _get_full_path(storage_path: str) -> Path | None:
    """Get full filesystem path for a stored file."""
    full = UPLOAD_DIR / storage_path
    return full if full.exists() else None


@router.post("/upload", response_model=FileUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file_upload_svc: FileUploadSvc,
    current_user: CurrentUser,
    file: UploadFile = File(...),
) -> Any:
    """Upload a file for use in chat."""
    data = await file.read()
    is_valid, error = file_upload_svc.validate_upload(file.content_type, len(data))
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    file_type = file_upload_svc.classify_file(file.content_type or "", file.filename or "unknown")
    parsed_content = file_upload_svc.parse_content(data, file_type, file.content_type or "")

    storage_path = _save_file(str(current_user.id), file.filename or "unknown", data)
    chat_file = file_upload_svc.create_chat_file(
        user_id=current_user.id,
        filename=file.filename or "unknown",
        mime_type=file.content_type or "application/octet-stream",
        size=len(data),
        storage_path=storage_path,
        file_type=file_type,
        parsed_content=parsed_content,
    )

    return FileUploadResponse(
        id=chat_file.id,
        filename=chat_file.filename,
        mime_type=chat_file.mime_type,
        size=chat_file.size,
        file_type=chat_file.file_type,
    )


@router.get("/{file_id}")
def download_file(
    file_id: str,
    file_upload_svc: FileUploadSvc,
    current_user: CurrentUser,
    disposition: str = "inline",
) -> Any:
    """Serve a file. Only the owner can access their files."""
    try:
        chat_file = file_upload_svc.get_user_file(file_id, current_user.id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found") from None

    file_path = _get_full_path(chat_file.storage_path)
    if not file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found on disk")

    mode = "attachment" if disposition == "attachment" else "inline"
    safe_name = chat_file.filename.replace('"', "")
    headers = {
        "Content-Disposition": f'{mode}; filename="{safe_name}"',
        "X-Frame-Options": "SAMEORIGIN",
        "Content-Security-Policy": "frame-ancestors 'self'",
    }
    return FileResponse(path=file_path, media_type=chat_file.mime_type, headers=headers)


@router.get("/{file_id}/info", response_model=FileInfo)
def get_file_info(
    file_id: str,
    file_upload_svc: FileUploadSvc,
    current_user: CurrentUser,
) -> Any:
    """Get file metadata. Only the owner can access."""
    try:
        chat_file = file_upload_svc.get_user_file(file_id, current_user.id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found") from None

    return FileInfo(
        id=chat_file.id,
        filename=chat_file.filename,
        mime_type=chat_file.mime_type,
        size=chat_file.size,
        file_type=chat_file.file_type,
        created_at=chat_file.created_at,
        user_id=chat_file.user_id,
    )
