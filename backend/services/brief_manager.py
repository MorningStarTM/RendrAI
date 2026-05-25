"""
brief_manager.py
================
Centralized stateful context buffer for brief and prompt data.

BriefManager is NOT a pipeline runner. It is a shared memory/buffer
that LangGraph nodes call to read context and write results.

Each session is keyed by chat_id and persisted as a JSON file on disk.

Pattern every LangGraph node follows:
    context = bm.get_<node>_context(chat_id)   # read what this node needs
    result  = call_the_model(context)           # do the work
    bm.store_<result>(chat_id, result)          # write result back
"""

from __future__ import annotations

import csv
import json
import logging
import uuid
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any
from backend.logger import logger


STORE_DIR = Path(__file__).parent / "store"
STORE_DIR.mkdir(parents=True, exist_ok=True)


class BriefManager:
    """
    Stateful context buffer — one JSON file per chat_id on disk.
    All LangGraph nodes share a single BriefManager instance.
    """

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def create(self, chat_id: str | None = None) -> str:
        """
        Start a new brief session.

        Args:
            chat_id: Provide your own ID (e.g. from an API request),
                     or leave None to auto-generate a UUID4.
        Returns:
            The chat_id for this session.
        """
        chat_id = chat_id or str(uuid.uuid4())

        if self._path(chat_id).exists():
            logger.warning("create() called on existing chat_id=%s — skipping", chat_id)
            return chat_id

        self._write(chat_id, {
            "chat_id":    chat_id,
            "created_at": _now(),
            "updated_at": _now(),
            # raw input
            "raw_input":  None,
            "input_type": None,
            # pipeline stages
            "elements":   [],   # parsed from raw_input
            "tags":       [],   # written by SLM node
            "prompts":    [],   # written by Reasoning node
            "images":     [],   # written by ImageGen node
        })
        logger.info("Session created  chat_id=%s", chat_id)
        return chat_id

    def delete(self, chat_id: str) -> None:
        """Remove a session from disk."""
        p = self._path(chat_id)
        if p.exists():
            p.unlink()
            logger.info("Session deleted  chat_id=%s", chat_id)

    def exists(self, chat_id: str) -> bool:
        """Return True if a session file exists for this chat_id."""
        return self._path(chat_id).exists()

    # ------------------------------------------------------------------
    # Write operations  (called by LangGraph nodes to store their output)
    # ------------------------------------------------------------------

    def store_raw_input(
        self,
        chat_id: str,
        raw_input: str,
        input_type: str = "auto",
    ) -> None:
        """
        Save the user's raw brief (CSV string or free text) and
        automatically parse it into elements.

        Called by: parse_input node (first node in the graph).

        Args:
            chat_id:    Session identifier.
            raw_input:  Raw CSV or plain-text brief from the user.
            input_type: "csv" | "text" | "auto"  (auto = detect from content)
        """
        if input_type == "auto":
            input_type = _detect_input_type(raw_input)

        elements = _parse_csv(raw_input) if input_type == "csv" else _parse_text(raw_input)

        self._patch(chat_id, {
            "raw_input":  raw_input,
            "input_type": input_type,
            "elements":   elements,
        })
        logger.info("store_raw_input  chat_id=%s  type=%s  elements=%d",
                 chat_id, input_type, len(elements))

    def store_elements(self, chat_id: str, elements: list[dict]) -> None:
        """
        Overwrite parsed elements (use when a node refines or enriches them).

        Args:
            elements: List of dicts, each representing one brief element.
        """
        self._patch(chat_id, {"elements": elements})
        logger.info("store_elements  chat_id=%s  count=%d", chat_id, len(elements))

    def store_tags(self, chat_id: str, tags: list[dict]) -> None:
        """
        Save validated tags returned by the SLM node.

        Expected tag shape:
            {"category": str, "value": str, "confidence": float}

        Called by: slm_validate node.
        """
        self._patch(chat_id, {"tags": tags})
        logger.info("store_tags  chat_id=%s  count=%d", chat_id, len(tags))

    def store_prompts(self, chat_id: str, prompts: list[str | dict]) -> None:
        """
        Save image-generation prompts returned by the Reasoning node.

        Called by: reasoning node.

        Args:
            prompts: List of prompt strings, or dicts with keys like
                     positive / negative / full_prompt.
        """
        self._patch(chat_id, {"prompts": prompts})
        logger.info("store_prompts  chat_id=%s  count=%d", chat_id, len(prompts))

    def store_images(self, chat_id: str, images: list[dict]) -> None:
        """
        Save image results returned by the ImageGen node.

        Expected image shape:
            {"prompt_index": int, "image_url": str, "s3_key": str}

        Called by: image_gen node.
        """
        self._patch(chat_id, {"images": images})
        logger.info("store_images  chat_id=%s  count=%d", chat_id, len(images))

    def update(self, chat_id: str, fields: dict[str, Any]) -> None:
        """
        Generic patch — merge any extra fields a node needs to persist
        (e.g. storage receipts, error details, custom metadata).
        """
        self._patch(chat_id, fields)
        logger.info("update  chat_id=%s  fields=%s", chat_id, list(fields.keys()))

    # ------------------------------------------------------------------
    # Read operations  (called by any node at any time)
    # ------------------------------------------------------------------

    def get_brief(self, chat_id: str) -> dict[str, Any]:
        """Return the full brief state dict."""
        return self._read(chat_id)

    def get_elements(self, chat_id: str) -> list[dict]:
        """Return parsed brief elements."""
        return self._read(chat_id).get("elements", [])

    def get_tags(self, chat_id: str) -> list[dict]:
        """Return SLM-validated tags."""
        return self._read(chat_id).get("tags", [])

    def get_prompts(self, chat_id: str) -> list[str | dict]:
        """Return generated prompts."""
        return self._read(chat_id).get("prompts", [])

    def get_images(self, chat_id: str) -> list[dict]:
        """Return image generation results."""
        return self._read(chat_id).get("images", [])

    def get_all(self, chat_id: str) -> dict:
        return self._read(chat_id)
    # ------------------------------------------------------------------
    # Context builders  (each returns exactly what one node needs)
    # ------------------------------------------------------------------

    def get_slm_context(self, chat_id: str) -> dict[str, Any]:
        """
        Build the payload for the SLM validation node.

        The SLM receives the parsed elements and original raw input,
        and is expected to return structured tags.

        Returns:
            {
              "chat_id":   str,
              "task":      "validate_and_tag",
              "elements":  [...],
              "raw_input": str,
            }
        """
        brief = self._read(chat_id)
        return {
            "chat_id":   chat_id,
            "task":      "validate_and_tag",
            "elements":  brief.get("elements", []),
            "raw_input": brief.get("raw_input", ""),
        }

    def get_reasoning_context(self, chat_id: str) -> dict[str, Any]:
        """
        Build the payload for the Reasoning Model node.

        The Reasoning Model receives elements + the validated tags from
        the SLM, and returns image-generation prompts.

        Returns:
            {
              "chat_id":  str,
              "task":     "generate_image_prompts",
              "elements": [...],
              "tags":     [...],
            }
        """
        brief = self._read(chat_id)
        return {
            "chat_id":  chat_id,
            "task":     "generate_image_prompts",
            "elements": brief.get("elements", []),
            "tags":     brief.get("tags", []),
        }

    def get_image_gen_context(self, chat_id: str) -> dict[str, Any]:
        """
        Build the payload for the Image Generation node.

        Returns:
            {
              "chat_id": str,
              "task":    "generate_images",
              "prompts": [...],
            }
        """
        brief = self._read(chat_id)
        return {
            "chat_id": chat_id,
            "task":    "generate_images",
            "prompts": brief.get("prompts", []),
        }

    def get_storage_context(self, chat_id: str) -> dict[str, Any]:
        """
        Build the payload for the Storage node (PostgreSQL + S3).

        Returns everything needed to persist a completed run.

        Returns:
            {
              "chat_id":    str,
              "created_at": str,
              "elements":   [...],
              "tags":       [...],
              "prompts":    [...],
              "images":     [...],
            }
        """
        brief = self._read(chat_id)
        return {
            "chat_id":    chat_id,
            "created_at": brief.get("created_at"),
            "elements":   brief.get("elements", []),
            "tags":       brief.get("tags", []),
            "prompts":    brief.get("prompts", []),
            "images":     brief.get("images", []),
        }

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def summary(self, chat_id: str) -> dict[str, Any]:
        """
        Lightweight status check — used by LangGraph conditional edges
        to decide which node runs next.

        Returns:
            {
              "chat_id":       str,
              "has_elements":  bool,
              "has_tags":      bool,
              "has_prompts":   bool,
              "has_images":    bool,
              "element_count": int,
              "tag_count":     int,
              "prompt_count":  int,
              "image_count":   int,
              "updated_at":    str,
            }
        """
        brief = self._read(chat_id)
        return {
            "chat_id":       chat_id,
            "has_elements":  bool(brief.get("elements")),
            "has_tags":      bool(brief.get("tags")),
            "has_prompts":   bool(brief.get("prompts")),
            "has_images":    bool(brief.get("images")),
            "element_count": len(brief.get("elements", [])),
            "tag_count":     len(brief.get("tags", [])),
            "prompt_count":  len(brief.get("prompts", [])),
            "image_count":   len(brief.get("images", [])),
            "updated_at":    brief.get("updated_at"),
        }

    def list_sessions(self) -> list[str]:
        """Return all active chat_ids (all JSON files in the store dir)."""
        return [p.stem for p in sorted(STORE_DIR.glob("*.json"))]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _path(self, chat_id: str) -> Path:
        return STORE_DIR / f"{chat_id}.json"

    def _read(self, chat_id: str) -> dict[str, Any]:
        path = self._path(chat_id)
        if not path.exists():
            raise KeyError(
                f"No brief found for chat_id={chat_id!r}. "
                "Call BriefManager.create() first."
            )
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _write(self, chat_id: str, data: dict[str, Any]) -> None:
        with open(self._path(chat_id), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _patch(self, chat_id: str, fields: dict[str, Any]) -> None:
        """Read → merge → write back atomically."""
        data = self._read(chat_id)
        data.update(fields)
        data["updated_at"] = _now()
        self._write(chat_id, data)


# ------------------------------------------------------------------
# Pure parsing helpers (no state, importable independently)
# ------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _detect_input_type(raw: str) -> str:
    """Heuristic: first non-empty line containing a comma → CSV."""
    for line in raw.splitlines():
        line = line.strip()
        if line:
            return "csv" if "," in line else "text"
    return "text"


def _parse_csv(raw: str) -> list[dict[str, Any]]:
    """Parse a CSV string into a list of normalised dicts."""
    reader = csv.DictReader(StringIO(raw))
    rows   = list(reader)
    if not rows:
        # No header row — treat each comma-separated cell as a value
        return [
            {"value": cell.strip(), "index": i}
            for i, cell in enumerate(raw.split(","))
            if cell.strip()
        ]
    return [{k.strip().lower(): v.strip() for k, v in row.items()} for row in rows]


def _parse_text(raw: str) -> list[dict[str, Any]]:
    """
    Parse free-text brief.
    Lines with a colon → {"key": ..., "value": ...}
    Plain lines        → {"value": ...}
    """
    elements = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            elements.append({"key": key.strip().lower(), "value": value.strip()})
        else:
            elements.append({"value": line})
    return elements