"""
backend/routers/history.py
===========================
Chat history and generation tree endpoints.

Routes:
    POST /history/sessions                          → create a new session
    GET  /history/{user_id}/sessions                → all sessions for a user
    GET  /history/sessions/{session_id}             → single session detail
    DELETE /history/sessions/{session_id}           → delete a session
    PATCH  /history/sessions/{session_id}/title     → rename a session
    GET  /history/sessions/{session_id}/tree        → full generation tree
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any

from backend.db.queries.sessions import (
    create_session,
    get_session,
    list_sessions_for_user,
    update_session_title,
    delete_session,
)
from backend.db.queries.prompts import get_generation_tree

router = APIRouter(prefix="/history", tags=["history"])


# ─── Request / Response models ────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    user_id: str
    title:   str = "New chat"


class SessionResponse(BaseModel):
    id:         str
    user_id:    str
    title:      str
    status:     str
    created_at: str
    updated_at: str
    job_count:  int = 0


class RenameTitleRequest(BaseModel):
    title: str


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/sessions", response_model=SessionResponse, status_code=201)
def create_session_endpoint(body: CreateSessionRequest):
    """
    Create a new chat session for a user.

    Body: { "user_id": "abc123", "title": "New chat" }
    """
    row = create_session(user_id=body.user_id, title=body.title)
    row["created_at"] = str(row["created_at"])
    row["updated_at"] = str(row["updated_at"])
    row["job_count"]  = 0
    return row


@router.get("/{user_id}/sessions", response_model=list[SessionResponse])
def list_sessions_endpoint(user_id: str):
    """
    Return all chat sessions for a user, most recent first.
    Used to populate the sidebar chat list.
    """
    rows = list_sessions_for_user(user_id)
    for r in rows:
        r["created_at"] = str(r["created_at"])
        r["updated_at"] = str(r["updated_at"])
        r["job_count"]  = r.get("job_count", 0)
    return rows


@router.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session_endpoint(session_id: str):
    """Fetch a single session by ID."""
    row = get_session(session_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")
    row["created_at"] = str(row["created_at"])
    row["updated_at"] = str(row["updated_at"])
    row["job_count"]  = 0
    return row


@router.patch("/sessions/{session_id}/title", status_code=200)
def rename_session_endpoint(session_id: str, body: RenameTitleRequest):
    """
    Rename a chat session.
    Called automatically after first generation to set a meaningful title.

    Body: { "title": "Coffee Brand Campaign" }
    """
    if not body.title.strip():
        raise HTTPException(status_code=400, detail="title cannot be empty")
    found = update_session_title(session_id, body.title.strip())
    if not found:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")
    return {"session_id": session_id, "title": body.title.strip()}


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session_endpoint(session_id: str):
    """
    Delete a session and all its jobs/prompts (CASCADE).
    """
    found = delete_session(session_id)
    if not found:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")


@router.get("/sessions/{session_id}/tree")
def get_tree_endpoint(session_id: str) -> list[dict[str, Any]]:
    """
    Return the full generation tree for a chat session.

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
                    "parent_id":    str | None,   ← links iterations
                    "prompt_index": int,
                    "text":         str,
                    "image_url":    str,
                    "local_path":   str,           ← Desktop path
                    "created_at":   str,
                },
                ...
            ]
        },
        ...
    ]

    Returns [] if session has no generations yet.
    """
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

    return get_generation_tree(session_id)