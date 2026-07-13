"""SQLAlchemy engine and session configuration."""

import os
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_DATABASE_URL = (
    "mysql+pymysql://sole_syntax:sole_syntax@127.0.0.1:3306/sole_syntax?charset=utf8mb4"
)


def get_database_url() -> str:
    return os.getenv("SOLE_SYNTAX_DATABASE_URL", DEFAULT_DATABASE_URL).strip()


@lru_cache(maxsize=8)
def get_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_database_url()
    return create_engine(url, pool_pre_ping=True)


def get_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_engine(database_url),
        expire_on_commit=False,
        autoflush=False,
    )
