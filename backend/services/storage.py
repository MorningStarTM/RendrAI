"""
services/storage.py
====================
StorageClient — persists completed pipeline runs.

Two responsibilities:
  1. S3 / MinIO  — upload raw image bytes, get back a public URL + s3_key
  2. PostgreSQL  — insert one record per image + upsert the brief_sessions row

Called by node_store() in agent.py:
    context = bm.get_storage_context(chat_id)
    record  = storage_client.store(context)
    bm.update(chat_id, {"storage_record": record})

Context shape (from BriefManager.get_storage_context):
    {
      "chat_id":    str,
      "created_at": str,
      "elements":   [...],
      "tags":       [...],
      "prompts":    [...],
      "images":     [
          {
            "prompt_index": int,
            "prompt":       str,
            "image_url":    str,   # empty if saved locally in dev
            "s3_key":       str,   # empty if saved locally in dev
            "image_data":   bytes, # raw bytes — uploaded to S3 here
          },
          ...
      ],
    }

Fallbacks (no config needed for local dev):
  - POSTGRES_DSN not set → writes to logs/db_fallback.jsonl
  - S3_BUCKET_NAME not set → saves images to local output_images/ folder
"""

from __future__ import annotations

import io
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("StorageClient")


class StorageClient:
    """
    Persists a completed pipeline run to PostgreSQL + S3/MinIO.

    All config is read from environment variables — no constructor args needed.
    Both backends degrade gracefully to local fallbacks when env vars are absent.

    Required env vars (production):
        POSTGRES_DSN        postgresql://user:pass@host:5432/dbname
        S3_BUCKET_NAME      pipeline-images
        AWS_ACCESS_KEY_ID   ...
        AWS_SECRET_ACCESS_KEY ...
        AWS_REGION          us-east-1
        S3_ENDPOINT_URL     http://minio:9000  (MinIO) or omit for real AWS S3

    Optional:
        S3_PUBLIC_BASE_URL  Override the public URL prefix for images
    """

    def __init__(self):
        self._s3  = _S3Client()
        self._db  = _PostgresClient()

    # ── Called by node_store() ────────────────────────────────────────────────

    def store(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Upload images to S3 and insert records to PostgreSQL.

        Args:
            context: From BriefManager.get_storage_context()

        Returns:
            {
              "db_ids":   [str, ...],   # inserted PostgreSQL row IDs
              "s3_keys":  [str, ...],   # S3 keys for each uploaded image
              "image_urls": [str, ...], # public URLs for each image
            }
        """
        chat_id    = context["chat_id"]
        created_at = context.get("created_at", _now())
        tags       = context.get("tags",    [])
        images     = context.get("images",  [])

        log.info("StorageClient.store  chat_id=%s  images=%d", chat_id, len(images))

        db_ids     = []
        s3_keys    = []
        image_urls = []

        for image in images:
            idx         = image.get("prompt_index", 0)
            prompt      = image.get("prompt", "")
            image_data  = image.get("image_data", b"")
            s3_key      = image.get("s3_key", "")    # already set if prod image_gen ran
            image_url   = image.get("image_url", "")

            # ── Step 1: Upload to S3 if we have bytes and no URL yet ──────────
            if image_data and not image_url:
                s3_key, image_url = self._s3.upload(
                    image_data = image_data,
                    chat_id    = chat_id,
                    index      = idx,
                )
                log.info("  S3 upload done  key=%s", s3_key)

            # ── Step 2: Insert PostgreSQL record ──────────────────────────────
            db_id = self._db.insert_image_record(
                chat_id    = chat_id,
                created_at = created_at,
                prompt     = prompt,
                s3_key     = s3_key,
                image_url  = image_url,
                tags       = tags,
                metadata   = {
                    "prompt_index": idx,
                    "local_path":   image.get("local_path", ""),
                },
            )
            log.info("  DB record inserted  id=%s", db_id)

            db_ids.append(db_id)
            s3_keys.append(s3_key)
            image_urls.append(image_url)

        # ── Step 3: Upsert brief_sessions row ─────────────────────────────────
        self._db.upsert_session(
            chat_id       = chat_id,
            created_at    = created_at,
            input_type    = context.get("input_type", ""),
            element_count = len(context.get("elements", [])),
            tag_count     = len(tags),
            prompt_count  = len(context.get("prompts", [])),
            image_count   = len(images),
            status        = "complete",
        )
        log.info("StorageClient.store done  chat_id=%s", chat_id)

        return {
            "db_ids":     db_ids,
            "s3_keys":    s3_keys,
            "image_urls": image_urls,
        }


# ─────────────────────────────────────────────────────────────────────────────
# S3 Client
# ─────────────────────────────────────────────────────────────────────────────

class _S3Client:
    """
    Uploads image bytes to S3 or MinIO.
    Falls back to local file storage when S3_BUCKET_NAME is not set.
    """

    def __init__(self):
        self.bucket   = os.getenv("S3_BUCKET_NAME")
        self.endpoint = os.getenv("S3_ENDPOINT_URL")          # None = real AWS S3
        self.region   = os.getenv("AWS_REGION", "us-east-1")
        self.public_base = os.getenv("S3_PUBLIC_BASE_URL", "")

    def upload(
        self,
        image_data: bytes,
        chat_id:    str,
        index:      int,
    ) -> tuple[str, str]:
        """
        Upload image bytes. Returns (s3_key, public_url).
        """
        s3_key = f"images/{chat_id}/prompt_{index}_{uuid.uuid4().hex[:8]}.png"

        if self.bucket:
            return self._upload_to_s3(s3_key, image_data)
        return self._save_locally(s3_key, image_data)

    def _upload_to_s3(self, s3_key: str, data: bytes) -> tuple[str, str]:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError

        kwargs: dict[str, Any] = {
            "region_name":          self.region,
            "aws_access_key_id":    os.environ["AWS_ACCESS_KEY_ID"],
            "aws_secret_access_key": os.environ["AWS_SECRET_ACCESS_KEY"],
        }
        if self.endpoint:
            kwargs["endpoint_url"] = self.endpoint   # MinIO or R2

        try:
            s3 = boto3.client("s3", **kwargs)
            s3.upload_fileobj(
                io.BytesIO(data),
                self.bucket,
                s3_key,
                ExtraArgs={"ContentType": "image/png"},
            )

            # Build public URL
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
        """Fallback: save to local output_images/ when S3 is not configured."""
        dest = Path(__file__).parent.parent.parent / "output_images" / s3_key
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        log.warning("S3 not configured — image saved locally: %s", dest)
        return s3_key, f"file://{dest.resolve()}"


# ─────────────────────────────────────────────────────────────────────────────
# PostgreSQL Client
# ─────────────────────────────────────────────────────────────────────────────

class _PostgresClient:
    """
    Writes records to PostgreSQL.
    Falls back to a local JSONL file when POSTGRES_DSN is not set.

    Tables (defined in postgresql/init.sql):
        image_generation_records  — one row per generated image
        brief_sessions            — one row per pipeline run
    """

    # ── SQL ───────────────────────────────────────────────────────────────────

    _INSERT_IMAGE = """
        INSERT INTO image_generation_records
            (chat_id, created_at, prompt, s3_key, image_url, tags, metadata)
        VALUES
            (%(chat_id)s, %(created_at)s, %(prompt)s, %(s3_key)s,
             %(image_url)s, %(tags)s::jsonb, %(metadata)s::jsonb)
        RETURNING id;
    """

    _UPSERT_SESSION = """
        INSERT INTO brief_sessions
            (chat_id, created_at, input_type, element_count,
             tag_count, prompt_count, image_count, status)
        VALUES
            (%(chat_id)s, %(created_at)s, %(input_type)s, %(element_count)s,
             %(tag_count)s, %(prompt_count)s, %(image_count)s, %(status)s)
        ON CONFLICT (chat_id) DO UPDATE SET
            status        = EXCLUDED.status,
            image_count   = EXCLUDED.image_count,
            prompt_count  = EXCLUDED.prompt_count,
            tag_count     = EXCLUDED.tag_count,
            updated_at    = NOW();
    """

    # ── Public methods ────────────────────────────────────────────────────────

    def insert_image_record(
        self,
        chat_id:    str,
        created_at: str,
        prompt:     str,
        s3_key:     str,
        image_url:  str,
        tags:       list,
        metadata:   dict,
    ) -> str:
        """Insert one image record. Returns the new row UUID."""
        params = {
            "chat_id":    chat_id,
            "created_at": created_at,
            "prompt":     prompt,
            "s3_key":     s3_key,
            "image_url":  image_url,
            "tags":       json.dumps(tags),
            "metadata":   json.dumps(metadata),
        }
        dsn = os.getenv("POSTGRES_DSN")
        if dsn:
            return self._pg_insert(dsn, self._INSERT_IMAGE, params)
        return self._jsonl_insert("image_records", params)

    def upsert_session(
        self,
        chat_id:       str,
        created_at:    str,
        input_type:    str,
        element_count: int,
        tag_count:     int,
        prompt_count:  int,
        image_count:   int,
        status:        str,
    ) -> None:
        """Upsert the brief_sessions row for this chat_id."""
        params = {
            "chat_id":       chat_id,
            "created_at":    created_at,
            "input_type":    input_type,
            "element_count": element_count,
            "tag_count":     tag_count,
            "prompt_count":  prompt_count,
            "image_count":   image_count,
            "status":        status,
        }
        dsn = os.getenv("POSTGRES_DSN")
        if dsn:
            self._pg_execute(dsn, self._UPSERT_SESSION, params)
        else:
            self._jsonl_insert("sessions", params)

    # ── PostgreSQL helpers ────────────────────────────────────────────────────

    def _pg_insert(self, dsn: str, sql: str, params: dict) -> str:
        import psycopg2
        import psycopg2.extras

        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                row_id = str(cur.fetchone()[0])
            conn.commit()
        return row_id

    def _pg_execute(self, dsn: str, sql: str, params: dict) -> None:
        import psycopg2

        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
            conn.commit()

    # ── Local JSONL fallback ──────────────────────────────────────────────────

    def _jsonl_insert(self, table: str, params: dict) -> str:
        """
        Fallback when POSTGRES_DSN is not set.
        Appends a JSON line to logs/db_fallback_{table}.jsonl
        """
        row_id   = str(uuid.uuid4())
        log_dir  = Path(__file__).parent.parent.parent / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"db_fallback_{table}.jsonl"

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps({"id": row_id, **params}) + "\n")

        log.warning(
            "POSTGRES_DSN not set — record written to %s", log_file
        )
        return row_id


# ── Helper ────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()