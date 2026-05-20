
"""
RAG CLI commands for document management and retrieval.

Commands:
    rag-collections   - List collections with stats
    rag-ingest        - Ingest file/directory
    rag-search        - Search knowledge base
    rag-drop          - Drop collection
    rag-stats         - Overall RAG system statistics
"""
import asyncio
import os
from pathlib import Path

import click

from app.commands import command, info, success, error, warning
from app.services.rag.config import DocumentExtensions, RAGSettings
from app.services.rag.documents import DocumentProcessor
from app.services.rag.embeddings import EmbeddingService
from app.services.rag.ingestion import IngestionService
from app.services.rag.retrieval import RetrievalService
from app.services.rag.vectorstore import BaseVectorStore
from app.services.rag.vectorstore import ChromaVectorStore


def get_rag_services() -> tuple[RAGSettings, BaseVectorStore, DocumentProcessor, RetrievalService, IngestionService]:
    """Initialize RAG services for CLI usage."""
    settings = RAGSettings()
    embedder = EmbeddingService(settings=settings)
    vector_store = ChromaVectorStore(settings=settings, embedding_service=embedder)
    processor = DocumentProcessor(settings=settings)
    retrieval = RetrievalService(vector_store=vector_store, settings=settings)
    ingestion = IngestionService(processor=processor, vector_store=vector_store)
    return settings, vector_store, processor, retrieval, ingestion


async def list_collections_async(vector_store: BaseVectorStore) -> None:
    """List all collections with their stats."""
    collection_names = await vector_store.list_collections()

    if not collection_names:
        info("No collections found.")
        return

    click.echo(f"\nFound {len(collection_names)} collection(s):\n")

    for name in collection_names:
        try:
            info_obj = await vector_store.get_collection_info(name)
            click.echo(f"  {name}")
            click.echo(f"    Vectors: {info_obj.total_vectors:,}")
            click.echo(f"    Dimension: {info_obj.dim}")
            click.echo(f"    Status: {info_obj.indexing_status}")
            click.echo()
        except Exception as e:
            warning(f"Could not get info for '{name}': {e}")


@command("rag-collections", help="List collections with stats")
def rag_collections() -> None:
    """List all available collections in the vector store with their statistics."""
    _, vector_store, _, _, _ = get_rag_services()
    asyncio.run(list_collections_async(vector_store))


async def ingest_path_async(
    path: str,
    collection: str,
    recursive: bool,
    vector_store: BaseVectorStore,
    processor: DocumentProcessor,
    ingestion: IngestionService,
    replace: bool = True,
    sync_mode: str = "full",
) -> None:
    """Ingest files from a path (file or directory)."""
    target_path = Path(path).resolve()

    if not target_path.exists():
        error(f"Path does not exist: {target_path}")
        return

    if target_path.is_file():
        files = [target_path]
    elif target_path.is_dir():
        if recursive:
            files = list(target_path.rglob("*"))
            files = [f for f in files if f.is_file() and not f.name.startswith(".")]
        else:
            files = list(target_path.iterdir())
            files = [f for f in files if f.is_file() and not f.name.startswith(".")]
    else:
        error(f"Invalid path: {target_path}")
        return

    if not files:
        warning("No files found to ingest.")
        return

    allowed_extensions = {ext.value for ext in DocumentExtensions}
    files = [f for f in files if f.suffix.lower() in allowed_extensions]

    if not files:
        warning(f"No supported files found. Allowed: {', '.join(allowed_extensions)}")
        return

    import hashlib
    from tqdm import tqdm

    info(f"Syncing {len(files)} file(s) into '{collection}' (mode={sync_mode})...")

    success_count = 0
    error_count = 0
    replaced_count = 0
    skipped_count = 0

    with tqdm(files, unit="file", desc="Syncing", ncols=80) as pbar:
        for filepath in pbar:
            pbar.set_postfix_str(filepath.name[:30], refresh=True)

            source_path = str(filepath.resolve())
            if sync_mode in ("new_only", "update_only"):
                existing_id: str | None = await ingestion.find_existing(collection, source_path)

                if sync_mode == "new_only":
                    if existing_id:
                        file_hash: str = hashlib.sha256(filepath.read_bytes()).hexdigest()
                        existing_hash: str | None = await ingestion.get_existing_hash(collection, source_path)
                        if existing_hash and file_hash == existing_hash:
                            skipped_count += 1
                            continue

                elif sync_mode == "update_only":
                    if not existing_id:
                        skipped_count += 1
                        continue
                    file_hash = hashlib.sha256(filepath.read_bytes()).hexdigest()
                    existing_hash = await ingestion.get_existing_hash(collection, source_path)
                    if existing_hash and file_hash == existing_hash:
                        skipped_count += 1
                        continue

            try:
                result = await ingestion.ingest_file(filepath=filepath, collection_name=collection, replace=replace)
                if result.status.value == "done":
                    success_count += 1
                    if result.message and "replaced" in result.message:
                        replaced_count += 1
                else:
                    error_count += 1
                    tqdm.write(f"  X {filepath.name}: {result.error_message}")
            except Exception as e:
                error_count += 1
                tqdm.write(f"  X {filepath.name}: {str(e)}")

    click.echo()
    msg = f"Done: {success_count} ingested"
    if replaced_count > 0:
        msg += f" ({replaced_count} updated)"
    if skipped_count > 0:
        msg += f", {skipped_count} skipped"
    success(msg)
    if error_count > 0:
        error(f"Failed: {error_count} files")


@command("rag-ingest", help="Ingest file/directory into knowledge base")
@click.argument("path", type=click.Path(exists=True))
@click.option("--collection", "-c", default="documents", help="Collection name (default: documents)")
@click.option("--recursive/--no-recursive", "-r", default=False, help="Recursively process directories")
@click.option("--replace/--no-replace", default=True, help="Replace existing documents")
@click.option("--sync-mode", type=click.Choice(["full", "new_only", "update_only"]), default="full")
def rag_ingest(path: str, collection: str, recursive: bool, replace: bool, sync_mode: str) -> None:
    """Ingest a file or directory into the knowledge base."""
    _, vector_store, processor, _, ingestion = get_rag_services()
    asyncio.run(ingest_path_async(path, collection, recursive, vector_store, processor, ingestion, replace, sync_mode))


async def search_async(query: str, collection: str, top_k: int, retrieval: RetrievalService) -> None:
    """Search the knowledge base."""
    info(f"Searching collection '{collection}' for: \"{query}\"")
    click.echo()

    results = await retrieval.retrieve(query=query, collection_name=collection, limit=top_k)

    if not results:
        warning("No results found.")
        return

    for i, result in enumerate(results, 1):
        click.echo(f"--- Result {i} (score: {result.score:.4f}) ---")
        if result.metadata:
            filename = result.metadata.get("filename", "Unknown")
            page_num = result.metadata.get("page_num", "?")
            click.echo(f"Source: {filename} (page {page_num})")
        content = result.content[:500]
        if len(result.content) > 500:
            content += "..."
        click.echo(content)
        click.echo()


@command("rag-search", help="Search knowledge base")
@click.argument("query")
@click.option("--collection", "-c", default="documents", help="Collection name")
@click.option("--top-k", "-k", default=4, type=int, help="Number of results to return")
def rag_search(query: str, collection: str, top_k: int) -> None:
    """Search the knowledge base for relevant content."""
    _, _, _, retrieval, _ = get_rag_services()
    asyncio.run(search_async(query, collection, top_k, retrieval))


async def drop_collection_async(collection: str, yes: bool, vector_store: BaseVectorStore) -> None:
    """Drop a collection."""
    if not yes:
        click.confirm(f"Are you sure you want to drop collection '{collection}'? This cannot be undone.", abort=True)
    try:
        await vector_store.delete_collection(collection)
        success(f"Collection '{collection}' dropped successfully.")
    except Exception as e:
        error(f"Failed to drop collection: {e}")


@command("rag-drop", help="Drop a collection")
@click.argument("collection")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def rag_drop(collection: str, yes: bool) -> None:
    """Drop a collection and all its data."""
    _, vector_store, _, _, _ = get_rag_services()
    asyncio.run(drop_collection_async(collection, yes, vector_store))


@command("rag-stats", help="Show overall RAG system statistics")
def rag_stats() -> None:
    """Display overall RAG system statistics."""
    settings, vector_store, _, _, _ = get_rag_services()
    asyncio.run(stats_async(settings, vector_store))


async def stats_async(settings: RAGSettings, vector_store: BaseVectorStore) -> None:
    """Show RAG system statistics."""
    click.echo("RAG System Statistics")
    click.echo("=" * 40)

    try:
        collection_names = await vector_store.list_collections()
        click.echo(f"\nCollections: {len(collection_names)}")
    except Exception as e:
        warning(f"Could not list collections: {e}")
        collection_names = []

    click.echo("\nConfiguration:")
    click.echo(f"  Embedding model: {settings.embeddings_config.model}")
    click.echo(f"  Embedding dimension: {settings.embeddings_config.dim}")
    click.echo(f"  Chunk size: {settings.chunk_size}")
    click.echo(f"  Chunk overlap: {settings.chunk_overlap}")
    click.echo(f"  Parser method: {settings.pdf_parser.method}")

    if collection_names:
        click.echo("\nCollection Details:")
        total_vectors = 0
        for name in collection_names:
            try:
                info_obj = await vector_store.get_collection_info(name)
                click.echo(f"  {name}:")
                click.echo(f"    Vectors: {info_obj.total_vectors:,}")
                total_vectors += info_obj.total_vectors
            except Exception:
                click.echo(f"  {name}: Error getting info")
        click.echo(f"\nTotal vectors: {total_vectors:,}")
    click.echo()
