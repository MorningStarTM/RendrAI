"""
backend/db/queries/sessions.py
================================
All SQL queries for the sessions table.
"""

from __future__ import annotations

from typing import Any
from backend.db.database import get_conn


# ─── Create ───────────────────────────────────────────────────────────────────

def create_session(user_id: str, title: str = "New chat") -> dict[str, Any]:
    """
    Create a new chat session for a user.

    Args:
        user_id: The owning user's ID.
        title:   Initial session title (auto-updated on first generation).

    Returns:
        The created session row.
    """
    sql = """
        INSERT INTO sessions (user_id, title)
        VALUES (%s, %s)
        RETURNING id, user_id, title, status, created_at, updated_at;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id, title))
            return dict(cur.fetchone())


# ─── Read ─────────────────────────────────────────────────────────────────────

def get_session(session_id: str) -> dict[str, Any] | None:
    """Fetch a single session by ID. Returns None if not found."""
    sql = """
        SELECT id, user_id, title, status, created_at, updated_at
        FROM sessions
        WHERE id = %s;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (session_id,))
            row = cur.fetchone()
            return dict(row) if row else None


def list_sessions_for_user(user_id: str) -> list[dict[str, Any]]:
    """
    Return all sessions for a user, most recent first.
    Includes a count of jobs per session for the sidebar display.
    """
    sql = """
        SELECT
            s.id,
            s.user_id,
            s.title,
            s.status,
            s.created_at,
            s.updated_at,
            COUNT(j.id) AS job_count
        FROM sessions s
        LEFT JOIN jobs j ON j.session_id = s.id
        WHERE s.user_id = %s
        GROUP BY s.id
        ORDER BY s.updated_at DESC;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id,))
            return [dict(r) for r in cur.fetchall()]


# ─── Update ───────────────────────────────────────────────────────────────────

def update_session_title(session_id: str, title: str) -> bool:
    """Update the session title. Returns True if the session was found."""
    sql = """
        UPDATE sessions
        SET title = %s, updated_at = NOW()
        WHERE id = %s
        RETURNING id;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (title, session_id))
            return cur.fetchone() is not None


def update_session_status(session_id: str, status: str) -> bool:
    """Update session status (active | archived)."""
    sql = """
        UPDATE sessions
        SET status = %s, updated_at = NOW()
        WHERE id = %s
        RETURNING id;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (status, session_id))
            return cur.fetchone() is not None


def touch_session(session_id: str) -> None:
    """Update updated_at timestamp — called whenever a new job runs."""
    sql = "UPDATE sessions SET updated_at = NOW() WHERE id = %s;"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (session_id,))


# ─── Delete ───────────────────────────────────────────────────────────────────

def delete_session(session_id: str) -> bool:
    """Hard delete a session and all its jobs/prompts (CASCADE)."""
    sql = "DELETE FROM sessions WHERE id = %s RETURNING id;"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (session_id,))
            return cur.fetchone() is not None