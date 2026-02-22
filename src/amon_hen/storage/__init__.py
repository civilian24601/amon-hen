"""Storage layer — SQLite metadata + Qdrant vectors."""

from amon_hen.config import get_settings
from amon_hen.storage.sqlite import SQLiteStore
from amon_hen.storage.vectors import VectorStore


def get_stores(settings=None) -> tuple[SQLiteStore, VectorStore]:
    """Get both storage backends."""
    if settings is None:
        settings = get_settings()
    return SQLiteStore(settings.sqlite_path), VectorStore(settings)
