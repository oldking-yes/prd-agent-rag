"""Embedding service abstraction using ChromaDB's built-in ONNX embedding."""

from typing import Any

from app.services.rag.config import RAGSettings
from app.services.rag.models import Document


class EmbeddingService:
    """Embedding service using ChromaDB's default ONNX embedding function.

    Uses all-MiniLM-L6-v2 via ONNX runtime (bundled with ChromaDB).
    No external API key needed.
    """

    def __init__(self, settings: RAGSettings) -> None:
        self.settings = settings
        self._ef = None

    def _get_ef(self):
        if self._ef is None:
            from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
            self._ef = DefaultEmbeddingFunction()
        return self._ef

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        ef = self._get_ef()
        result = ef(texts)
        if result is None:
            return [[0.0] * 384 for _ in texts]
        return result

    def embed_query(self, text: str) -> list[float]:
        """Embed a single text query."""
        results = self.embed_queries([text])
        return results[0] if results else [0.0] * 384

    def embed_document(self, document: Document) -> list[list[float]]:
        texts = []
        if document.chunked_pages:
            for chunk in document.chunked_pages:
                texts.append(chunk.content)
        else:
            for page in document.pages:
                texts.append(page.content)
        if not texts:
            return []
        ef = self._get_ef()
        result = ef(texts)
        if result is None:
            return [[0.0] * 384 for _ in texts]
        return result

    def warmup(self) -> None:
        """Load model and verify readiness."""
        ef = self._get_ef()
        result = ef(["warmup"])
        assert result is not None and len(result) == 1
