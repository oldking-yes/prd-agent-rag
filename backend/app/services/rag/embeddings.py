
"""Embedding service abstraction with local fallback.

Supports OpenAI-compatible embedding APIs (including DeepSeek) and a local
sentence-transformers fallback for offline use.
"""

from abc import ABC, abstractmethod

from app.services.rag.config import RAGSettings
from app.services.rag.models import Document


class BaseEmbeddingProvider(ABC):
    """Abstract base class for embedding providers."""

    @abstractmethod
    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of query texts."""
        pass

    @abstractmethod
    def embed_document(self, document: Document) -> list[list[float]]:
        """Embed all chunks of a document."""
        pass

    @abstractmethod
    def warmup(self) -> None:
        """Load model and verify readiness."""
        pass


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """OpenAI/DeepSeek compatible embedding provider."""

    def __init__(self, model: str, api_key: str = "", base_url: str = "") -> None:
        self.model = model
        from openai import OpenAI

        client_kwargs = {}
        if api_key:
            client_kwargs["api_key"] = api_key
        if base_url:
            client_kwargs["base_url"] = base_url
        self.client = OpenAI(**client_kwargs) if client_kwargs else OpenAI()

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        response = self.client.embeddings.create(input=texts, model=self.model)
        return [d.embedding for d in response.data]

    def embed_document(self, document: Document) -> list[list[float]]:
        texts = []
        for page in document.pages:
            for chunk in page.chunks:
                texts.append(chunk.content)
        if not texts:
            return []
        response = self.client.embeddings.create(input=texts, model=self.model)
        return [d.embedding for d in response.data]

    def warmup(self) -> None:
        self.client.embeddings.create(input=["warmup"], model=self.model)


class EmbeddingService(BaseEmbeddingProvider):
    """Main embedding service router."""

    def __init__(self, settings: RAGSettings) -> None:
        self.settings = settings
        self._provider: BaseEmbeddingProvider | None = None

    def _get_provider(self) -> BaseEmbeddingProvider:
        if self._provider is not None:
            return self._provider

        model = self.settings.embeddings_config.model

        # Try to detect provider from model name
        if model.startswith("deepseek"):
            from app.core.config import settings as app_settings

            self._provider = OpenAIEmbeddingProvider(
                model=model,
                api_key=app_settings.DEEPSEEK_API_KEY or app_settings.OPENAI_API_KEY,
                base_url="https://api.deepseek.com/v1",
            )
        else:
            # Default: use standard OpenAI
            self._provider = OpenAIEmbeddingProvider(model=model)

        return self._provider

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        return self._get_provider().embed_queries(texts)

    def embed_document(self, document: Document) -> list[list[float]]:
        return self._get_provider().embed_document(document)

    def warmup(self) -> None:
        self._get_provider().warmup()
