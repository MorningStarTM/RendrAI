"""
backend/db/queries/jobs.py
============================
All SQL queries for the jobs table.
One job = one full pipeline run (brief submission) inside a session.
"""

from __future__ import annotations

from typing import Any
from backend.db.database import get_conn


# ─── Create ───────────────────────────────────────────────────────────────────

def create_job(
    session_id: str,
    brief_text: str,
    input_type: str = "text",
) -> dict[str, Any]:
    """
    Insert a new job row when a pipeline run starts.

    Args:
        session_id: The parent session ID.
        brief_text: Raw user brief text.
        input_type: 'text' | 'csv' | 'auto'

    Returns:
        The created job row.
    """
    sql = """
        INSERT INTO jobs (session_id, brief_text, input_type, status)
        VALUES (%s, %s, %s, 'running')
        RETURNING id, session_id, brief_text, input_type,
                  status, retry_count, error_msg, created_at, updated_at;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (session_id, brief_text, input_type))
            return dict(cur.fetchone())


# ─── Read ─────────────────────────────────────────────────────────────────────

def get_job(job_id: str) -> dict[str, Any] | None:
    """Fetch a single job by ID."""
    sql = """
        SELECT id, session_id, brief_text, input_type,
               status, retry_count, error_msg, created_at, updated_at
        FROM jobs
        WHERE id = %s;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (job_id,))
            row = cur.fetchone()
            return dict(row) if row else None


def list_jobs_for_session(session_id: str) -> list[dict[str, Any]]:
    """
    Return all jobs for a session ordered oldest → newest.
    Used to build the ordered generation list for a chat.
    """
    sql = """
        SELECT id, session_id, brief_text, input_type,
               status, retry_count, error_msg, created_at, updated_at
        FROM jobs
        WHERE session_id = %s
        ORDER BY created_at ASC;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (session_id,))
            return [dict(r) for r in cur.fetchall()]


# ─── Update ───────────────────────────────────────────────────────────────────

def mark_job_complete(job_id: str) -> None:
    """Mark a job as complete after successful pipeline run."""
    sql = """
        UPDATE jobs
        SET status = 'complete', updated_at = NOW()
        WHERE id = %s;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (job_id,))


def mark_job_failed(job_id: str, error_msg: str) -> None:
    """Mark a job as failed with an error message."""
    sql = """
        UPDATE jobs
        SET status     = 'failed',
            error_msg  = %s,
            retry_count = retry_count + 1,
            updated_at  = NOW()
        WHERE id = %s;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (error_msg, job_id))