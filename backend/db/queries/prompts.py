"""
backend/db/queries/prompts.py
================================
All SQL queries for the prompts table.

The generation tree is built via parent_id (self-referencing FK):
  - parent_id = NULL  →  root generation (first run in a session)
  - parent_id = <id>  →  iteration/update on a specific image

Tree for a session looks like:
  job_1
    └── prompt_0  (parent_id=NULL)   image_0.png
    └── prompt_1  (parent_id=NULL)   image_1.png
  job_2  (user iterated on image_1)
    └── prompt_0  (parent_id=prompt_1_id)  image_0.png
"""

from __future__ import annotations

from typing import Any
from backend.db.database import get_conn


# ─── Create ───────────────────────────────────────────────────────────────────

def insert_prompt(
    session_id:   str,
    job_id:       str,
    prompt_index: int,
    text:         str,
    local_path:   str,
    parent_id:    str | None = None,
    image_url:    str = "",
    image_s3_key: str = "",
) -> dict[str, Any]:
    """
    Insert one generated image/prompt row.

    Args:
        session_id:   Parent session ID.
        job_id:       Parent job ID.
        prompt_index: Position within the job (0, 1, 2...).
        text:         Full prompt text sent to the image model.
        local_path:   Absolute path to image on Desktop (dev mode).
        parent_id:    ID of the prompt this was iterated from (None = root).
        image_url:    Public URL (S3/MinIO) — empty in local dev.
        image_s3_key: S3 key — empty in local dev.

    Returns:
        The created prompt row as a dict.
    """
    sql = """
        INSERT INTO prompts
            (session_id, job_id, parent_id, prompt_index,
             text, image_url, image_s3_key, local_path)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, session_id, job_id, parent_id, prompt_index,
                  text, image_url, image_s3_key, local_path, created_at;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (
                session_id, job_id, parent_id, prompt_index,
                text, image_url, image_s3_key, local_path,
            ))
            return dict(cur.fetchone())


# ─── Read ─────────────────────────────────────────────────────────────────────

def get_prompt(prompt_id: str) -> dict[str, Any] | None:
    """Fetch a single prompt row by ID."""
    sql = """
        SELECT id, session_id, job_id, parent_id, prompt_index,
               text, image_url, image_s3_key, local_path, created_at
        FROM prompts
        WHERE id = %s;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (prompt_id,))
            row = cur.fetchone()
            return dict(row) if row else None


def list_prompts_for_job(job_id: str) -> list[dict[str, Any]]:
    """
    Return all prompts for a job ordered by prompt_index.
    Used to display images for a single generation.
    """
    sql = """
        SELECT id, session_id, job_id, parent_id, prompt_index,
               text, image_url, image_s3_key, local_path, created_at
        FROM prompts
        WHERE job_id = %s
        ORDER BY prompt_index ASC;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (job_id,))
            return [dict(r) for r in cur.fetchall()]


def list_prompts_for_session(session_id: str) -> list[dict[str, Any]]:
    """
    Return ALL prompts for a session ordered by creation time.
    Used to build the full generation tree for a chat.
    """
    sql = """
        SELECT id, session_id, job_id, parent_id, prompt_index,
               text, image_url, image_s3_key, local_path, created_at
        FROM prompts
        WHERE session_id = %s
        ORDER BY created_at ASC;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (session_id,))
            return [dict(r) for r in cur.fetchall()]


def get_generation_tree(session_id: str) -> list[dict[str, Any]]:
    """
    Build the full generation tree for a session.

    Returns jobs in order, each with their prompts/images nested inside.

    Shape:
    [
        {
            "job_id":     str,
            "brief_text": str,
            "status":     str,
            "created_at": str,
            "prompts": [
                {
                    "id":           str,
                    "parent_id":    str | None,
                    "prompt_index": int,
                    "text":         str,
                    "image_url":    str,
                    "local_path":   str,
                    "created_at":   str,
                },
                ...
            ]
        },
        ...
    ]
    """
    # Fetch all jobs for this session in order
    jobs_sql = """
        SELECT id, brief_text, input_type, status, created_at
        FROM jobs
        WHERE session_id = %s
        ORDER BY created_at ASC;
    """
    # Fetch all prompts for this session in order
    prompts_sql = """
        SELECT id, job_id, parent_id, prompt_index,
               text, image_url, image_s3_key, local_path, created_at
        FROM prompts
        WHERE session_id = %s
        ORDER BY created_at ASC;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(jobs_sql, (session_id,))
            jobs = [dict(r) for r in cur.fetchall()]

            cur.execute(prompts_sql, (session_id,))
            all_prompts = [dict(r) for r in cur.fetchall()]

    # Group prompts under their job
    prompts_by_job: dict[str, list] = {j["id"]: [] for j in jobs}
    for p in all_prompts:
        jid = p["job_id"]
        if jid in prompts_by_job:
            prompts_by_job[jid].append(p)

    # Build final tree
    tree = []
    for job in jobs:
        tree.append({
            "job_id":     job["id"],
            "brief_text": job["brief_text"],
            "input_type": job["input_type"],
            "status":     job["status"],
            "created_at": job["created_at"].isoformat() if hasattr(job["created_at"], "isoformat") else str(job["created_at"]),
            "prompts":    [
                {
                    **p,
                    "created_at": p["created_at"].isoformat() if hasattr(p["created_at"], "isoformat") else str(p["created_at"]),
                }
                for p in prompts_by_job[job["id"]]
            ],
        })

    return tree