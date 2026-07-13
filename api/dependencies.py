"""FastAPI dependencies kept replaceable for tests and future database adapters."""

from application.support_service import SupportService
from infrastructure.database import get_database_url


def get_support_service() -> SupportService:
    return SupportService(get_database_url())
