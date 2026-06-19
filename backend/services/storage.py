"""
backend/services/storage.py
============================
StorageClient — persists completed pipeline runs.

Two responsibilities:
  1. Local disk  — save raw image bytes to Desktop (dev) or S3/MinIO (prod)
  2. PostgreSQL  — insert jobs + prompts rows using the new schema

Called by node_store() in agent.py:
    context = bm.get_storage_context(chat_id)
    record  = storage_client.store(context)
    bm.update(chat_id, {"storage_record": record})

Context shape (from BriefManager.get_storage_context):
    {
      "chat_id":    str,   ← used as job identifier from BriefManager
      "session_id": str,   ← DB sessions.id  (must be set by caller)
      "user_id":    str,   ← DB users.id     (must be set by caller)
      "created_at": str,
      "brief_text": str,
      "input_type": str,
      "elements":   [...],
      "tags":       [...],
      "prompts":    [...],
      "parent_id":  str | None,  ← prompt.id being iterated on (update mode)
      "images":     [
          {
            "prompt_index": int,
            "prompt":       str | dict,
            "image_url":    str,
            "s3_key":       str,
            "local_path":   str,   ← written by node_image_gen_local
            "image_data":   str,   ← base64-encoded bytes
          },
          ...
      ],
    }

Fallbacks:
  - POSTGRES_DSN not set → writes to logs/db_fallback.jsonl
  - S3_BUCKET_NAME not set → images already saved to Desktop by node_image_gen_local
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("StorageClient")

DESKTOP = Path.home() / "Desktop" / "rendr_ai_output"


class StorageClient:
    """
    Persists a completed pipeline run to PostgreSQL + local disk / S3.

    Reads all config from environment variables.
    Both backends degrade gracefully when env vars are absent.
    """

    def __init__(self):
        self._s3 = _S3Client()
        self._db = _PostgresClient()

    # ── Called by node_store() ────────────────────────────────────────────────

    def store(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Save images and insert DB records for a completed pipeline run.

        Returns:
            {
              "job_id":     str,
              "prompt_ids": [str, ...],
              "image_urls": [str, ...],
            }
        """
        session_id  = context.get("session_id", "")
        user_id     = context.get("user_id", "")
        brief_text  = context.get("brief_text") or context.get("raw_input", "")
        input_type  = context.get("input_type", "text")
        images      = context.get("images", [])
        parent_id   = context.get("parent_id")   # prompt.id being iterated on

        log.info("StorageClient.store  session_id=%s  images=%d", session_id, len(images))

        # ── Step 1: Create job row ────────────────────────────────────────────
        job_id = self._db.create_job(
            session_id=session_id,
            brief_text=brief_text,
            input_type=input_type,
        )
        log.info("  Job created  job_id=%s", job_id)

        prompt_ids = []
        image_urls = []

        for image in images:
            idx        = image.get("prompt_index", 0)
            prompt_raw = image.get("prompt", "")
            local_path = image.get("local_path", "")
            s3_key     = image.get("s3_key", "")
            image_url  = image.get("image_url", "")

            # Normalise prompt text (could be dict from reasoning model)
            if isinstance(prompt_raw, dict):
                prompt_text = (
                    prompt_raw.get("full_prompt")
                    or prompt_raw.get("positive")
                    or json.dumps(prompt_raw)
                )
            else:
                prompt_text = str(prompt_raw)

            # ── Step 2: Upload to S3 if configured ───────────────────────────
            image_data_b64 = image.get("image_data", "")
            if image_data_b64 and not image_url:
                try:
                    raw_bytes = base64.b64decode(image_data_b64) if isinstance(image_data_b64, str) else image_data_b64
                    s3_key, image_url = self._s3.upload(
                        image_data=raw_bytes,
                        chat_id=session_id,
                        index=idx,
                    )
                    log.info("  S3 upload done  key=%s", s3_key)
                except Exception as exc:
                    log.warning("  S3 upload skipped: %s", exc)

            # ── Step 3: Insert prompt row ─────────────────────────────────────
            prompt_id = self._db.insert_prompt(
                session_id=session_id,
                job_id=job_id,
                prompt_index=idx,
                text=prompt_text,
                local_path=local_path,
                parent_id=parent_id,
                image_url=image_url,
                image_s3_key=s3_key,
            )
            log.info("  Prompt inserted  prompt_id=%s", prompt_id)

            prompt_ids.append(prompt_id)
            image_urls.append(image_url or f"file://{local_path}")

        # ── Step 4: Mark job complete ─────────────────────────────────────────
        self._db.mark_job_complete(job_id)

        # ── Step 5: Touch session updated_at ─────────────────────────────────
        if session_id:
            self._db.touch_session(session_id)

        log.info("StorageClient.store done  job_id=%s", job_id)

        return {
            "job_id":     job_id,
            "prompt_ids": prompt_ids,
            "image_urls": image_urls,
        }


# ─────────────────────────────────────────────────────────────────────────────
# S3 Client (unchanged — falls back gracefully when not configured)
# ─────────────────────────────────────────────────────────────────────────────

class _S3Client:
    def __init__(self):
        self.bucket      = os.getenv("S3_BUCKET_NAME")
        self.endpoint    = os.getenv("S3_ENDPOINT_URL")
        self.region      = os.getenv("AWS_REGION", "us-east-1")
        self.public_base = os.getenv("S3_PUBLIC_BASE_URL", "")

    def upload(self, image_data: bytes, chat_id: str, index: int) -> tuple[str, str]:
        s3_key = f"images/{chat_id}/prompt_{index}_{uuid.uuid4().hex[:8]}.png"
        if self.bucket:
            return self._upload_to_s3(s3_key, image_data)
        return self._save_locally(s3_key, image_data)

    def _upload_to_s3(self, s3_key: str, data: bytes) -> tuple[str, str]:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError

        kwargs: dict[str, Any] = {
            "region_name":           self.region,
            "aws_access_key_id":     os.environ["AWS_ACCESS_KEY_ID"],
            "aws_secret_access_key": os.environ["AWS_SECRET_ACCESS_KEY"],
        }
        if self.endpoint:
            kwargs["endpoint_url"] = self.endpoint

        try:
            s3 = boto3.client("s3", **kwargs)
            s3.upload_fileobj(
                io.BytesIO(data), self.bucket, s3_key,
                ExtraArgs={"ContentType": "image/png"},
            )
            if self.public_base:
                url = f"{self.public_base.rstrip('/')}/{s3_key}"
            elif self.endpoint:
                url = f"{self.endpoint.rstrip('/')}/{self.bucket}/{s3_key}"
            else:
                url = f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{s3_key}"
            return s3_key, url
        except (BotoCoreError, ClientError) as exc:
            log.error("S3 upload failed: %s", exc)
            raise

    def _save_locally(self, s3_key: str, data: bytes) -> tuple[str, str]:
        dest = DESKTOP / s3_key
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        log.warning("S3 not configured — image saved locally: %s", dest)
        return s3_key, f"file://{dest.resolve()}"


# ─────────────────────────────────────────────────────────────────────────────
# PostgreSQL Client — new schema
# ─────────────────────────────────────────────────────────────────────────────

class _PostgresClient:
    """
    Writes to the new schema: jobs + prompts tables.
    Falls back to JSONL when POSTGRES_DSN is not set.
    """

    def create_job(self, session_id: str, brief_text: str, input_type: str) -> str:
        """Insert a job row. Returns the new job ID."""
        from backend.db.queries.jobs import create_job
        dsn = os.getenv("POSTGRES_DSN")
        if dsn:
            row = create_job(session_id=session_id, brief_text=brief_text, input_type=input_type)
            return row["id"]
        return self._jsonl_insert("jobs", {
            "session_id": session_id,
            "brief_text": brief_text,
            "input_type": input_type,
            "status":     "running",
        })

    def insert_prompt(
        self,
        session_id:   str,
        job_id:       str,
        prompt_index: int,
        text:         str,
        local_path:   str,
        parent_id:    str | None,
        image_url:    str,
        image_s3_key: str,
    ) -> str:
        """Insert a prompt row. Returns the new prompt ID."""
        from backend.db.queries.prompts import insert_prompt
        dsn = os.getenv("POSTGRES_DSN")
        if dsn:
            row = insert_prompt(
                session_id=session_id,
                job_id=job_id,
                prompt_index=prompt_index,
                text=text,
                local_path=local_path,
                parent_id=parent_id,
                image_url=image_url,
                image_s3_key=image_s3_key,
            )
            return row["id"]
        return self._jsonl_insert("prompts", {
            "session_id":   session_id,
            "job_id":       job_id,
            "prompt_index": prompt_index,
            "text":         text,
            "local_path":   local_path,
            "parent_id":    parent_id,
            "image_url":    image_url,
            "image_s3_key": image_s3_key,
        })

    def mark_job_complete(self, job_id: str) -> None:
        from backend.db.queries.jobs import mark_job_complete
        dsn = os.getenv("POSTGRES_DSN")
        if dsn:
            mark_job_complete(job_id)

    def touch_session(self, session_id: str) -> None:
        from backend.db.queries.sessions import touch_session
        dsn = os.getenv("POSTGRES_DSN")
        if dsn:
            touch_session(session_id)

    def _jsonl_insert(self, table: str, params: dict) -> str:
        row_id   = str(uuid.uuid4())
        log_dir  = Path(__file__).parent.parent.parent / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"db_fallback_{table}.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps({"id": row_id, **params}) + "\n")
        log.warning("POSTGRES_DSN not set — record written to %s", log_file)
        return row_id


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()