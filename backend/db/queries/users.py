"""
backend/db/queries/users.py
============================
All SQL queries for the users table.
"""

from __future__ import annotations

from typing import Any
from backend.db.database import get_conn


# ─── Create ───────────────────────────────────────────────────────────────────

def create_user(name: str) -> dict[str, Any]:
    """
    Insert a new user. Returns the created user row.

    Args:
        name: Display name for the user.
    """
    sql = """
        INSERT INTO users (name)
        VALUES (%s)
        RETURNING id, name, active, created_at;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (name,))
            return dict(cur.fetchone())


# ─── Read ─────────────────────────────────────────────────────────────────────

def get_user(user_id: str) -> dict[str, Any] | None:
    """Fetch a single user by ID. Returns None if not found."""
    sql = """
        SELECT id, name, active, created_at
        FROM users
        WHERE id = %s;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id,))
            row = cur.fetchone()
            return dict(row) if row else None


def list_users() -> list[dict[str, Any]]:
    """Return all active users ordered by creation date."""
    sql = """
        SELECT id, name, active, created_at
        FROM users
        WHERE active = TRUE
        ORDER BY created_at ASC;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return [dict(r) for r in cur.fetchall()]


# ─── Update ───────────────────────────────────────────────────────────────────

def deactivate_user(user_id: str) -> bool:
    """Soft-delete a user (sets active = false). Returns True if found."""
    sql = """
        UPDATE users SET active = FALSE
        WHERE id = %s
        RETURNING id;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id,))
            return cur.fetchone() is not None