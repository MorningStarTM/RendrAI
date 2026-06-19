-- ─────────────────────────────────────────────────────────────────────────────
-- RendrAI — PostgreSQL Schema
-- Run with: psql -U <user> -d rendrai -f schema.sql
-- ─────────────────────────────────────────────────────────────────────────────

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";


-- ─── users ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id          TEXT        PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name        TEXT        NOT NULL,
    token_hash  TEXT        UNIQUE,                  -- optional API token (future auth)
    active      BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ─── sessions ────────────────────────────────────────────────────────────────
-- One session = one chat window opened by a user
CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT        PRIMARY KEY DEFAULT gen_random_uuid()::text,
    user_id     TEXT        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title       TEXT        NOT NULL DEFAULT 'New chat',
    status      TEXT        NOT NULL DEFAULT 'active',   -- active | archived
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ─── jobs ────────────────────────────────────────────────────────────────────
-- One job = one pipeline run (brief submission) inside a session
CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT        PRIMARY KEY DEFAULT gen_random_uuid()::text,
    session_id  TEXT        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    brief_text  TEXT        NOT NULL DEFAULT '',         -- raw user brief
    input_type  TEXT        NOT NULL DEFAULT 'text',     -- text | csv | auto
    status      TEXT        NOT NULL DEFAULT 'pending',  -- pending | running | complete | failed
    retry_count INT         NOT NULL DEFAULT 0,
    error_msg   TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ─── prompts ─────────────────────────────────────────────────────────────────
-- One prompt = one generated image inside a job
-- parent_id enables the generation tree (iteration / branching)
CREATE TABLE IF NOT EXISTS prompts (
    id           TEXT        PRIMARY KEY DEFAULT gen_random_uuid()::text,
    session_id   TEXT        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    job_id       TEXT        NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    parent_id    TEXT        REFERENCES prompts(id) ON DELETE SET NULL,  -- NULL = root generation
    prompt_index INT         NOT NULL DEFAULT 0,
    text         TEXT        NOT NULL DEFAULT '',        -- full prompt text sent to image model
    image_url    TEXT        NOT NULL DEFAULT '',        -- local file:// path or S3 URL
    image_s3_key TEXT        NOT NULL DEFAULT '',        -- S3/MinIO key (empty in local dev)
    local_path   TEXT        NOT NULL DEFAULT '',        -- absolute Desktop path (dev)
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ─── usage_log ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS usage_log (
    id          TEXT        PRIMARY KEY DEFAULT gen_random_uuid()::text,
    user_id     TEXT        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id  TEXT        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    job_id      TEXT        REFERENCES jobs(id) ON DELETE SET NULL,
    token_in    INT         NOT NULL DEFAULT 0,
    token_out   INT         NOT NULL DEFAULT 0,
    cost_usd    REAL        NOT NULL DEFAULT 0.0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ─── Indexes ──────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_sessions_user_id   ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_session_id    ON jobs(session_id);
CREATE INDEX IF NOT EXISTS idx_prompts_session_id ON prompts(session_id);
CREATE INDEX IF NOT EXISTS idx_prompts_job_id     ON prompts(job_id);
CREATE INDEX IF NOT EXISTS idx_prompts_parent_id  ON prompts(parent_id);
CREATE INDEX IF NOT EXISTS idx_usage_user_id      ON usage_log(user_id);
CREATE INDEX IF NOT EXISTS idx_usage_session_id   ON usage_log(session_id);