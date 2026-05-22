
"""RAG API routes — collection management, search, document upload."""

import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Query, UploadFile, status
from fastapi.responses import FileResponse

from app.api.deps import IngestionSvc, RetrievalSvc, VectorStoreSvc
from app.api.deps import CurrentAdmin, CurrentUser
from app.api.deps import RAGDocumentSvc
from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.schemas.rag import RAGMessageResponse
from app.services.rag.config import get_supported_formats
from app.schemas.rag import (
    RAGCollectionInfo,
    RAGCollectionList,
    RAGDocumentList,
    RAGIngestResponse,
    RAGRetryResponse,
    RAGSearchRequest,
    RAGSearchResponse,
    RAGSearchResult,
    RAGTrackedDocumentList,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/supported-formats")
async def get_supported_formats_endpoint() -> Any:
    """Return file formats supported by the current PDF parser configuration."""
    parser_name = getattr(settings, "PDF_PARSER", "pymupdf")
    return {"parser": parser_name, "formats": sorted(get_supported_formats(parser_name))}


@router.get("/collections", response_model=RAGCollectionList)
async def list_collections(
    vector_store: VectorStoreSvc,
    _: CurrentUser,
) -> Any:
    """List all available collections in the vector store."""
    names = await vector_store.list_collections()
    return RAGCollectionList(items=names)


@router.post(
    "/collections/{name}",
    status_code=status.HTTP_201_CREATED,
    response_model=RAGMessageResponse,
)
async def create_collection(
    name: str,
    vector_store: VectorStoreSvc,
    _: CurrentAdmin,
) -> Any:
    """Create and initialize a new collection."""
    await vector_store.create_collection(name)
    return RAGMessageResponse(message=f"Collection '{name}' created successfully.")


@router.delete(
    "/collections/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def drop_collection(
    name: str,
    vector_store: VectorStoreSvc,
    rag_doc_svc: RAGDocumentSvc,
    _: CurrentAdmin,
) -> None:
    """Drop an entire collection."""
    await vector_store.delete_collection(name)
    await rag_doc_svc.delete_by_collection(name)


@router.get("/collections/{name}/info", response_model=RAGCollectionInfo)
async def get_collection_info(
    name: str,
    vector_store: VectorStoreSvc,
    _: CurrentAdmin,
) -> Any:
    """Retrieve stats for a specific collection."""
    return await vector_store.get_collection_info(name)


@router.get("/collections/{name}/documents", response_model=RAGDocumentList)
async def list_documents(
    name: str,
    vector_store: VectorStoreSvc,
    _: CurrentAdmin,
) -> Any:
    """List all documents in a specific collection."""
    return await vector_store.get_document_list(name)


@router.post("/search", response_model=RAGSearchResponse)
async def search_documents(
    request: RAGSearchRequest,
    retrieval_service: RetrievalSvc,
    _: CurrentUser,
    use_reranker: bool = Query(False, description="Whether to use reranking"),
) -> Any:
    """Search for relevant document chunks."""
    if request.collection_names and len(request.collection_names) > 1:
        results = await retrieval_service.retrieve_multi(
            query=request.query,
            collection_names=request.collection_names,
            limit=request.limit,
            min_score=request.min_score,
            use_reranker=use_reranker,
        )
    else:
        collection = (
            request.collection_names[0] if request.collection_names else request.collection_name
        )
        results = await retrieval_service.retrieve(
            query=request.query,
            collection_name=collection,
            limit=request.limit,
            min_score=request.min_score,
            filter=request.filter or "",
            use_reranker=use_reranker,
        )
    api_results = [RAGSearchResult(**hit.model_dump()) for hit in results]
    return RAGSearchResponse(results=api_results)


@router.delete(
    "/collections/{name}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_document(
    name: str,
    document_id: str,
    ingestion_service: IngestionSvc,
    _: CurrentAdmin,
) -> None:
    """Delete a specific document from a collection."""
    success = await ingestion_service.remove_document(name, document_id)
    if not success:
        raise NotFoundError(
            message="Document not found",
            details={"collection": name, "document_id": document_id},
        )


@router.post(
    "/collections/{name}/ingest",
    response_model=RAGIngestResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_file(
    name: str,
    rag_doc_svc: RAGDocumentSvc,
    vector_store: VectorStoreSvc,
    _: CurrentAdmin,
    file: UploadFile = File(...),
    replace: bool = Query(False),
) -> Any:
    """Upload and queue a file for ingestion into a collection."""
    data = await file.read()
    return await rag_doc_svc.dispatch_upload(
        collection_name=name,
        file_data=data,
        filename=file.filename or "unknown",
        replace=replace,
        vector_store=vector_store,
    )


@router.get("/documents", response_model=RAGTrackedDocumentList)
async def list_rag_documents(
    rag_doc_svc: RAGDocumentSvc,
    _: CurrentAdmin,
    collection_name: str | None = Query(None),
) -> Any:
    """List tracked RAG documents."""
    return await rag_doc_svc.list_documents(collection_name)


@router.get("/documents/{doc_id}/download")
async def download_rag_document(
    doc_id: str,
    rag_doc_svc: RAGDocumentSvc,
    _: CurrentAdmin,
) -> Any:
    """Download the original file."""
    file_path, filename, mime_type = await rag_doc_svc.get_download_info(doc_id)
    return FileResponse(path=file_path, filename=filename, media_type=mime_type)


@router.delete(
    "/documents/{doc_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_rag_document(
    doc_id: str,
    rag_doc_svc: RAGDocumentSvc,
    ingestion_service: IngestionSvc,
    _: CurrentAdmin,
) -> None:
    """Delete a document from SQL, vector store, and file storage."""
    await rag_doc_svc.delete_document(doc_id, ingestion_service)


@router.post("/documents/{doc_id}/retry", response_model=RAGRetryResponse)
async def retry_ingestion(
    doc_id: str,
    rag_doc_svc: RAGDocumentSvc,
    _: CurrentAdmin,
) -> Any:
    """Retry a failed document ingestion."""
    doc = await rag_doc_svc.retry_ingestion(doc_id)
    return RAGRetryResponse(id=str(doc.id), status="processing", message="Retry queued")


@router.post("/presets/load", response_model=RAGMessageResponse)
async def load_preset_documents(
    vector_store: VectorStoreSvc,
    _: CurrentUser,
) -> Any:
    """Load built-in PRD template documents into the knowledge base.

    Searches for .md files in the seed-docs/ directory and ingests them
    into the 'prd_templates' collection.
    """
    import hashlib
    from app.services.rag.documents import DocumentProcessor
    from app.services.rag.embeddings import EmbeddingService
    from app.services.rag.ingestion import IngestionService

    # Search for seed-docs: parent directories of this file, plus CWD
    seed_dir: Path | None = None
    base = Path(__file__).resolve().parent
    for candidate in [
        Path("seed-docs"),  # relative to CWD
        Path.cwd() / "seed-docs",
    ] + [base.parents[i] / "seed-docs" for i in range(min(8, len(base.parents)))]:
        if candidate and candidate.exists():
            seed_dir = candidate.resolve()
            break
    if not seed_dir:
        return RAGMessageResponse(message=f"Seed directory not found. Searched from {base}")

    md_files = sorted(seed_dir.glob("*.md"))
    if not md_files:
        return RAGMessageResponse(message="No markdown files found in seed-docs/")

    # Ensure collection exists
    collections = await vector_store.list_collections()
    if "prd_templates" not in collections:
        await vector_store.create_collection("prd_templates")

    processor = DocumentProcessor(settings=settings.rag)
    embedder = EmbeddingService(settings=settings.rag)
    ingestion = IngestionService(processor=processor, vector_store=vector_store)

    success = 0
    errors = 0
    for filepath in md_files:
        try:
            result = await ingestion.ingest_file(
                filepath=filepath,
                collection_name="prd_templates",
                replace=True,
            )
            if result.status.value == "done":
                success += 1
            else:
                errors += 1
                logger.warning(f"Failed to ingest {filepath.name}: {result.error_message}")
        except Exception as e:
            errors += 1
            logger.warning(f"Failed to ingest {filepath.name}: {e}")

    return RAGMessageResponse(
        message=f"Loaded {success} documents into 'prd_templates' ({errors} failed). "
                f"Source: {seed_dir.name}/"
    )
