"""
Database utilities (SQLAlchemy engine/session) for the FastAPI backend.

Uses environment variables provided by the MySQL container:
- MYSQL_URL
- MYSQL_USER
- MYSQL_PASSWORD
- MYSQL_DB
- MYSQL_PORT

Important: Do not hardcode credentials in code. Configure these via .env in the runtime environment.
"""

from __future__ import annotations

import os
from typing import Generator, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def _build_mysql_url() -> str:
    """
    Build a MySQL SQLAlchemy URL from environment variables.

    Expected env vars:
      MYSQL_URL: host (or host:port), e.g. "localhost" (preferred) or "127.0.0.1"
      MYSQL_USER: username
      MYSQL_PASSWORD: password
      MYSQL_DB: database name
      MYSQL_PORT: port (optional if MYSQL_URL already includes a port)
    """
    host = os.getenv("MYSQL_URL", "localhost")
    user = os.getenv("MYSQL_USER", "")
    password = os.getenv("MYSQL_PASSWORD", "")
    db = os.getenv("MYSQL_DB", "")
    port = os.getenv("MYSQL_PORT", "")

    # If host already contains "host:port", do not append port again.
    if port and ":" not in host:
        host = f"{host}:{port}"

    # Use pymysql driver (pure python).
    # Example: mysql+pymysql://user:pass@localhost:5001/mydb?charset=utf8mb4
    return f"mysql+pymysql://{user}:{password}@{host}/{db}?charset=utf8mb4"


# Lazily-created single engine per process.
_ENGINE: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None


# PUBLIC_INTERFACE
def get_engine() -> Engine:
    """Return a singleton SQLAlchemy Engine configured from environment variables."""
    global _ENGINE, _SessionLocal
    if _ENGINE is None:
        database_url = _build_mysql_url()
        _ENGINE = create_engine(
            database_url,
            pool_pre_ping=True,
            future=True,
        )
        _SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=_ENGINE,
            future=True,
        )
    return _ENGINE


# PUBLIC_INTERFACE
def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a SQLAlchemy session and closes it afterward."""
    if _SessionLocal is None:
        get_engine()
    assert _SessionLocal is not None
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()
