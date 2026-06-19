"""
backend/db/database.py
======================
PostgreSQL connection pool using psycopg2.

Usage anywhere in the app:
    from backend.db.database import get_conn

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT ...")
            rows = cur.fetchall()

Connection is configured via POSTGRES_DSN env var:
    POSTGRES_DSN=postgresql://user:pass@localhost:5432/rendrai
"""

from __future__ import annotations

import os
import logging
from contextlib import contextmanager
from typing import Generator

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

log = logging.getLogger("db")

_pool: ThreadedConnectionPool | None = None


def _get_pool() -> ThreadedConnectionPool:
    """Lazily create the connection pool on first call."""
    global _pool
    if _pool is None:
        dsn = os.environ.get("POSTGRES_DSN")
        if not dsn:
            raise RuntimeError(
                "POSTGRES_DSN environment variable is not set.\n"
                "Example: postgresql://user:pass@localhost:5432/rendrai"
            )
        _pool = ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=dsn,
            cursor_factory=psycopg2.extras.RealDictCursor,  # rows as dicts
        )
        log.info("PostgreSQL connection pool created")
    return _pool


@contextmanager
def get_conn() -> Generator:
    """
    Context manager — borrows a connection from the pool,
    commits on success, rolls back on exception, always returns to pool.

    Usage:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
    """
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def check_connection() -> bool:
    """Quick connectivity check — returns True if Postgres is reachable."""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except Exception as exc:
        log.error("DB health check failed: %s", exc)
        return False