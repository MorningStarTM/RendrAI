"""
services/agent.py
=================
LangGraph pipeline — fully wired flow.

Each node:
  1. Asks BriefManager for its context
  2. Calls the relevant client class method
  3. Writes the result back to BriefManager

Client classes (to be implemented separately):
  SLMClient         → services/slm_validator.py
  ReasoningClient   → services/reasoning_model.py
  ImageClient       → services/image_api.py
  StorageClient     → services/storage.py

Graph:
  parse_input → slm_validate → reasoning → image_gen → store → END
                     ↓ invalid
                    END
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from services.brief_manager import BriefManager
from services.slm_validator import SLMClient
from services.reasoning_model import ReasoningClient
from services.image_api import ImageClient
from services.storage import StorageClient

log = logging.getLogger("Agent")


# ─────────────────────────────────────────────────────────────────────────────
# Graph state — only chat_id travels between nodes.
# ALL brief data lives in BriefManager, never in state.
# ─────────────────────────────────────────────────────────────────────────────

class BriefState(TypedDict):
    chat_id: str
    error:   str | None


# ─────────────────────────────────────────────────────────────────────────────
# Nodes
# ─────────────────────────────────────────────────────────────────────────────

def node_parse_input(
    state:      BriefState,
    bm:         BriefManager,
    raw_input:  str,
    input_type: str = "auto",
) -> BriefState:
    """
    Parse the raw CSV / text brief and store elements in BriefManager.
    No client call needed — BM handles parsing internally.

    BM writes: raw_input, input_type, elements
    """
    chat_id = state["chat_id"]
    log.info("[parse_input] chat_id=%s  type=%s", chat_id, input_type)

    try:
        bm.store_raw_input(chat_id, raw_input, input_type)
        log.info("[parse_input] elements=%d", len(bm.get_elements(chat_id)))
    except Exception as exc:
        log.error("[parse_input] failed: %s", exc)
        return {**state, "error": str(exc)}

    return state


def node_slm_validate(
    state:  BriefState,
    bm:     BriefManager,
    client: SLMClient,
) -> BriefState:
    """
    Validate the brief elements and extract structured tags.

    BM  →  client : get_slm_context()   →  SLMClient.validate()
    client  →  BM : result tags         →  store_tags()
    """
    chat_id = state["chat_id"]
    log.info("[slm_validate] chat_id=%s", chat_id)

    try:
        context = bm.get_slm_context(chat_id)       # read from BM
        result  = client.validate(context)           # call SLMClient
        bm.store_tags(chat_id, result.get("tags", []))  # write to BM

        log.info("[slm_validate] tags=%d  valid=%s",
                 len(result.get("tags", [])), result.get("is_valid"))

        if not result.get("is_valid", True):
            return {**state, "error": result.get("feedback", "SLM rejected brief")}

    except Exception as exc:
        log.error("[slm_validate] failed: %s", exc)
        return {**state, "error": str(exc)}

    return state


def node_reasoning(
    state:  BriefState,
    bm:     BriefManager,
    client: ReasoningClient,
) -> BriefState:
    """
    Generate image-generation prompts from the validated brief.

    BM  →  client : get_reasoning_context()  →  ReasoningClient.generate_prompts()
    client  →  BM : prompts list             →  store_prompts()
    """
    chat_id = state["chat_id"]
    log.info("[reasoning] chat_id=%s", chat_id)

    try:
        context = bm.get_reasoning_context(chat_id)         # read from BM
        result  = client.generate_prompts(context)          # call ReasoningClient
        bm.store_prompts(chat_id, result.get("prompts", []))  # write to BM

        log.info("[reasoning] prompts=%d", len(result.get("prompts", [])))

    except Exception as exc:
        log.error("[reasoning] failed: %s", exc)
        return {**state, "error": str(exc)}

    return state


def node_image_gen(
    state:  BriefState,
    bm:     BriefManager,
    client: ImageClient,
) -> BriefState:
    """
    Generate one image per prompt.

    BM  →  client : get_image_gen_context()  →  ImageClient.generate()  (per prompt)
    client  →  BM : image results list       →  store_images()
    """
    chat_id = state["chat_id"]
    log.info("[image_gen] chat_id=%s", chat_id)

    try:
        context = bm.get_image_gen_context(chat_id)     # read from BM
        prompts = context["prompts"]

        images = []
        for idx, prompt in enumerate(prompts):
            log.info("[image_gen] generating %d/%d", idx + 1, len(prompts))

            result = client.generate(                   # call ImageClient
                prompt=prompt,
                metadata={"chat_id": chat_id, "prompt_index": idx},
            )

            images.append({
                "prompt_index": idx,
                "prompt":       prompt,
                "image_url":    result.get("image_url", ""),
                "s3_key":       result.get("s3_key", ""),
            })

        bm.store_images(chat_id, images)                # write to BM
        log.info("[image_gen] images=%d", len(images))

    except Exception as exc:
        log.error("[image_gen] failed: %s", exc)
        return {**state, "error": str(exc)}

    return state


def node_store(
    state:  BriefState,
    bm:     BriefManager,
    client: StorageClient,
) -> BriefState:
    """
    Persist the completed run to PostgreSQL + S3.

    BM  →  client : get_storage_context()  →  StorageClient.store()
    client  →  BM : storage receipt        →  update()
    """
    chat_id = state["chat_id"]
    log.info("[store] chat_id=%s", chat_id)

    try:
        context = bm.get_storage_context(chat_id)      # read from BM
        record  = client.store(context)                # call StorageClient
        bm.update(chat_id, {"storage_record": record}) # write receipt to BM

        log.info("[store] db_id=%s", record.get("db_id"))

    except Exception as exc:
        log.error("[store] failed: %s", exc)
        return {**state, "error": str(exc)}

    return state


# ─────────────────────────────────────────────────────────────────────────────
# Conditional edge
# ─────────────────────────────────────────────────────────────────────────────

def route_after_slm(state: BriefState) -> str:
    """Route to reasoning if valid, END early if SLM rejected."""
    if state.get("error"):
        log.warning("SLM rejected brief — stopping graph")
        return END
    return "reasoning"


# ─────────────────────────────────────────────────────────────────────────────
# Graph builder
# ─────────────────────────────────────────────────────────────────────────────

def build_graph(
    bm:         BriefManager,
    raw_input:  str,
    input_type: str = "auto",
):
    """
    Compile and return the LangGraph for one brief run.

    All client instances are created here and injected into nodes
    via closures — keeps node signatures compatible with LangGraph
    while staying fully testable (swap real clients for mocks in tests).

    Args:
        bm:         Shared BriefManager instance (injected by server/caller).
        raw_input:  Raw CSV or text brief from the user.
        input_type: "csv" | "text" | "auto"

    Usage:
        bm      = BriefManager()
        chat_id = bm.create()
        graph   = build_graph(bm, raw_input, input_type)
        result  = graph.invoke({"chat_id": chat_id, "error": None})
    """

    # Instantiate clients — each will call its respective LLM API
    slm       = SLMClient()
    reasoning = ReasoningClient()
    image     = ImageClient()
    storage   = StorageClient()

    # Wrap nodes in closures to inject dependencies
    def _parse(state):  return node_parse_input(state, bm, raw_input, input_type)
    def _slm(state):    return node_slm_validate(state, bm, slm)
    def _reason(state): return node_reasoning(state, bm, reasoning)
    def _imggen(state): return node_image_gen(state, bm, image)
    def _store(state):  return node_store(state, bm, storage)

    # Build graph
    g = StateGraph(BriefState)

    g.add_node("parse_input",  _parse)
    g.add_node("slm_validate", _slm)
    g.add_node("reasoning",    _reason)
    g.add_node("image_gen",    _imggen)
    g.add_node("store",        _store)

    g.set_entry_point("parse_input")

    g.add_edge("parse_input", "slm_validate")

    g.add_conditional_edges(
        "slm_validate",
        route_after_slm,
        {"reasoning": "reasoning", END: END},
    )

    g.add_edge("reasoning", "image_gen")
    g.add_edge("image_gen", "store")
    g.add_edge("store",     END)

    return g.compile()