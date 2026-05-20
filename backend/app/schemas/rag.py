
"""RAG API schemas."""

from typing import Any

from pydantic import BaseModel, Field


class RAGSearchRequest(BaseModel):
    """Parameters for a vector search query."""
    collection_name: str = Field("documents", description="Target collection for search")
    collection_names: list[str] | None = Field(None, description="Search across multiple collections")
    query: str = Field(..., description="Natural language search query")
    limit: int = Field(default=4, ge=1, le=20)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)
    filter: str | None = Field(None, description="Scalar filter expression")


class RAGSearchResult(BaseModel):
    """A single retrieved chunk with its associated metadata."""
    content: str
    score: float
    metadata: dict[str, Any]
    parent_doc_id: str


class RAGSearchResponse(BaseModel):
    """List of results found in the vector store."""
    results: list[RAGSearchResult]


class RAGCollectionInfo(BaseModel):
    """Statistical information about a specific collection."""
    name: str
    total_vectors: int
    dim: int
    indexing_status: str = "complete"


class RAGCollectionList(BaseModel):
    """List of all available collection names."""
    items: list[str]


class RAGDocumentItem(BaseModel):
    """Information about a single document in a collection."""
    document_id: str = Field(..., description="Unique identifier of the document")
    filename: str | None = None
    filesize: int | None = None
    filetype: str | None = None
    chunk_count: int = 0
    additional_info: dict[str, Any] | None = None


class RAGDocumentList(BaseModel):
    """List of all documents in a collection."""
    items: list[RAGDocumentItem]
    total: int


class RAGMessageResponse(BaseModel):
    """Simple message response."""
    message: str


class RAGTrackedDocumentItem(BaseModel):
    """A document tracked in the RAG document database."""
    id: str
    collection_name: str
    filename: str
    filesize: int | None = None
    filetype: str | None = None
    status: str = "pending"
    error_message: str | None = None
    vector_document_id: str | None = None
    chunk_count: int | None = None
    has_file: bool = False
    created_at: str | None = None
    completed_at: str | None = None


class RAGTrackedDocumentList(BaseModel):
    """List of tracked RAG documents."""
    items: list[RAGTrackedDocumentItem]
    total: int


class RAGIngestResponse(BaseModel):
    """Response from a document ingestion request."""
    id: str
    filename: str
    status: str
    message: str


class RAGRetryResponse(BaseModel):
    """Response from a retry ingestion request."""
    id: str
    status: str
    message: str
