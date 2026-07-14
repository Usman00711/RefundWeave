"""FastAPI dependencies kept replaceable for tests and future database adapters."""

from agent.graph import build_graph
from application.support_service import SupportService
from infrastructure.database import get_database_url


def get_support_service() -> SupportService:
    return SupportService(get_database_url())


def get_chat_graph():
    """Return the process-wide graph so thread checkpoints survive API requests."""
    return build_graph()
