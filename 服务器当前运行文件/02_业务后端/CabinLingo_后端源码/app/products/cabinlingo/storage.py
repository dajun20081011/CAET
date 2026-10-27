from ...core.config import settings
from .domain import TrainingStore


def build_store():
    if settings.database_url:
        from .postgres_store import PostgresStore
        return PostgresStore(settings.database_url)
    if settings.is_production:
        raise RuntimeError("Production cannot use the in-memory repository")
    return TrainingStore()
