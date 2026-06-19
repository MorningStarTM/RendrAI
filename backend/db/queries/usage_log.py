"""
backend/db/queries/usage_log.py
================================
All SQL queries for the usage_log table.
Tracks token usage and estimated cost per pipeline run.
"""

from __future__ import annotations

from typing import Any
from backend.db.database import get_conn


def log_usage(
    user_id:    str,
    session_id: str,
    job_id:     str,
    token_in:   int = 0,
    token_out:  int = 0,
    cost_usd:   float = 0.0,
) -> dict[str, Any]:
    """
    Insert one usage log entry.

    Args:
        user_id:    User who triggered the run.
        session_id: Chat session the run belongs to.
        job_id:     The specific pipeline job.
        token_in:   Input tokens consumed.
        token_out:  Output tokens produced.
        cost_usd:   Estimated cost in USD.

    Returns:
        The created usage row.
    """
    sql = """
        INSERT INTO usage_log
            (user_id, session_id, job_id, token_in, token_out, cost_usd)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id, user_id, session_id, job_id,
                  token_in, token_out, cost_usd, created_at;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id, session_id, job_id, token_in, token_out, cost_usd))
            return dict(cur.fetchone())


def get_usage_for_user(user_id: str) -> list[dict[str, Any]]:
    """Return all usage records for a user, newest first."""
    sql = """
        SELECT id, user_id, session_id, job_id,
               token_in, token_out, cost_usd, created_at
        FROM usage_log
        WHERE user_id = %s
        ORDER BY created_at DESC;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id,))
            return [dict(r) for r in cur.fetchall()]


def get_usage_summary_for_user(user_id: str) -> dict[str, Any]:
    """
    Aggregate token and cost totals for a user.

    Returns:
        {
            "total_token_in":  int,
            "total_token_out": int,
            "total_cost_usd":  float,
            "total_runs":      int,
        }
    """
    sql = """
        SELECT
            COALESCE(SUM(token_in),  0) AS total_token_in,
            COALESCE(SUM(token_out), 0) AS total_token_out,
            COALESCE(SUM(cost_usd),  0) AS total_cost_usd,
            COUNT(*)                    AS total_runs
        FROM usage_log
        WHERE user_id = %s;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id,))
            return dict(cur.fetchone())