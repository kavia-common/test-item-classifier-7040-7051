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
from urllib.parse import urlparse

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def _build_mysql_url() -> str:
    """
    Build a MySQL SQLAlchemy URL from environment variables.

    This project runs in multiple environments. Some runtimes provide MYSQL_URL as a *host*
    (e.g. "localhost" or "localhost:5001"), while others provide a full DSN
    (e.g. "mysql://localhost:5001/mydb").

    We support both:
      - If MYSQL_URL includes a URL scheme (contains '://'), we parse it and construct a
        SQLAlchemy URL using the `mysql+pymysql` driver.
      - Otherwise we treat MYSQL_URL as host[:port] and use MYSQL_PORT + MYSQL_DB.

    Expected env vars:
      MYSQL_URL: host[:port] or full DSN (mysql://host:port/db)
      MYSQL_USER: username (optional if embedded in MYSQL_URL DSN)
      MYSQL_PASSWORD: password (optional if embedded in MYSQL_URL DSN)
      MYSQL_DB: database name (used if not embedded in MYSQL_URL DSN)
      MYSQL_PORT: port (optional if host-only and not already in MYSQL_URL)
    """
    raw = os.getenv("MYSQL_URL", "localhost")
    user = os.getenv("MYSQL_USER", "")
    password = os.getenv("MYSQL_PASSWORD", "")
    db = os.getenv("MYSQL_DB", "")
    port = os.getenv("MYSQL_PORT", "")

    # Case 1: MYSQL_URL is a full DSN like mysql://host:port/db
    if "://" in raw:
        parsed = urlparse(raw)

        # parsed.hostname strips brackets for IPv6 and excludes port.
        host = parsed.hostname or "localhost"
        resolved_port = parsed.port  # int|None

        # DB name in DSN path is like "/mydb"
        dsn_db = (parsed.path or "").lstrip("/") or db

        # Allow credentials from DSN to override env, else fall back to env.
        dsn_user = parsed.username or user
        dsn_password = parsed.password or password

        # If DSN didn't include a port, use MYSQL_PORT if present.
        if resolved_port is None and port:
            try:
                resolved_port = int(port)
            except ValueError:
                # If port is malformed, leave it unset; SQLAlchemy will error clearly later.
                resolved_port = None

        hostport = f"{host}:{resolved_port}" if resolved_port is not None else host
        return f"mysql+pymysql://{dsn_user}:{dsn_password}@{hostport}/{dsn_db}?charset=utf8mb4"

    # Case 2: MYSQL_URL is host or host:port
    host = raw
    if port and ":" not in host:
        host = f"{host}:{port}"

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
