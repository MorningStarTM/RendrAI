"""
backend/main.py
================
RendrAI FastAPI application entrypoint.

Run locally:
    uvicorn backend.main:app --reload --port 8000

Endpoints registered:
    /users          → user management
    /history        → chat sessions + generation tree
    /health         → service health check
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.db.database import check_connection
from backend.routers.users import router as users_router
from backend.routers.history import router as history_router


# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown logic."""
    # Startup — verify DB is reachable
    if os.getenv("POSTGRES_DSN"):
        ok = check_connection()
        if ok:
            print("✅ PostgreSQL connected")
        else:
            print("⚠️  PostgreSQL connection failed — check POSTGRES_DSN")
    else:
        print("⚠️  POSTGRES_DSN not set — DB features will use JSONL fallback")
    yield
    # Shutdown (nothing to clean up yet)


# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="RendrAI API",
    description="AI-powered image generation pipeline",
    version="0.1.0",
    lifespan=lifespan,
)


# ─── CORS ─────────────────────────────────────────────────────────────────────
# Allow the Streamlit frontend (localhost:8501) to call the API

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8501",   # Streamlit dev
        "http://127.0.0.1:8501",
        "*",                       # Loosen for local dev — tighten in prod
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Routers ──────────────────────────────────────────────────────────────────

app.include_router(users_router)
app.include_router(history_router)


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/health", tags=["meta"])
def health():
    """
    Service health check.
    Returns DB connectivity status alongside the API status.
    """
    db_ok = check_connection() if os.getenv("POSTGRES_DSN") else False
    return {
        "status": "ok",
        "db":     "connected" if db_ok else "disconnected",
    }


@app.get("/", tags=["meta"])
def root():
    return {"message": "RendrAI API — visit /docs for Swagger UI"}