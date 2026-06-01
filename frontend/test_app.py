"""
dev_tester.py
=============
Place this file at:  RendrAI/frontend/dev_tester.py

Run with:
    cd RendrAI
    streamlit run frontend/dev_tester.py

It imports build_dev_graph directly — no HTTP, no FastAPI needed.
"""

import sys
import uuid
import time
import logging
import traceback
from pathlib import Path
from dotenv import load_dotenv
import streamlit as st

# ── Make sure the backend package is importable ──────────────────────────────
# File lives at:  RendrAI/frontend/dev_tester.py
# __file__  →     .../RendrAI/frontend/dev_tester.py
# parent    →     .../RendrAI/frontend/
# parent.parent → .../RendrAI/              (ROOT)
# ROOT/backend  → .../RendrAI/backend/      (added to sys.path)
#
# This lets us do:  from services.agent import ...
#                   from services.brief_manager import ...

ROOT    = Path(__file__).resolve().parent.parent       # RendrAI/
BACKEND = ROOT / "backend"                             # RendrAI/backend/
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

for p in (str(BACKEND), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from services.agent         import build_dev_graph     # noqa: E402
from services.brief_manager import BriefManager        # noqa: E402

# ── Logging → visible in terminal running streamlit ──────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s — %(message)s",
)
log = logging.getLogger("dev_tester")


# ─── Page Config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="RendrAI · Graph Tester",
    page_icon="🧪",
    layout="wide",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Syne:wght@700;800&display=swap');

html, body, [class*="css"] { font-family: 'IBM Plex Mono', monospace; }
.stApp { background: #0d0d0f; color: #e8e4dc; }
[data-testid="stSidebar"] { background: #111116; border-right: 1px solid #222230; }

h1 { font-family: 'Syne', sans-serif; font-weight: 800; font-size: 1.8rem;
     letter-spacing: -0.03em; color: #f0ebe0; }

.tag { display:inline-block; background:#1e1e2a; border:1px solid #3a3a55;
       border-radius:4px; padding:2px 8px; font-size:0.7rem; color:#8080aa;
       margin:2px; }

.node-row { display:flex; align-items:center; gap:10px;
            padding:10px 14px; border-radius:6px; margin-bottom:6px;
            border:1px solid #2a2a35; background:#16161e;
            font-size:0.8rem; }
.node-row.running { border-color:#c8a96e; background:#1a1810; }
.node-row.done    { border-color:#4a9e6e; background:#0f1a12; }
.node-row.error   { border-color:#c85050; background:#1a0f0f; }
.node-row.skipped { border-color:#555570; background:#141420; color:#666688; }

.dot { width:10px; height:10px; border-radius:50%; flex-shrink:0;
       background:#2a2a35; }
.dot.running { background:#c8a96e; }
.dot.done    { background:#4a9e6e; }
.dot.error   { background:#c85050; }
.dot.skipped { background:#44445a; }

.prompt-box { background:#1a1a26; border:1px solid #33334a; border-radius:6px;
              padding:10px 14px; margin:6px 0; font-size:0.78rem; color:#a0a0c0;
              line-height:1.5; }

.section { font-size:0.6rem; letter-spacing:.15em; text-transform:uppercase;
           color:#44445a; border-bottom:1px solid #1a1a26;
           padding-bottom:4px; margin:20px 0 10px; }

.stButton > button { background:#c8a96e !important; color:#0d0d0f !important;
    border:none !important; border-radius:6px !important;
    font-family:'IBM Plex Mono',monospace !important; font-weight:600 !important;
    font-size:0.78rem !important; letter-spacing:.08em !important; }
.stButton > button:hover { opacity:.82 !important; }

.stTextArea textarea { background:#16161e !important; border:1px solid #2a2a35 !important;
    color:#e8e4dc !important; font-family:'IBM Plex Mono',monospace !important;
    font-size:0.82rem !important; }
.stTextArea textarea:focus { border-color:#c8a96e !important; }

#MainMenu, footer, header { visibility:hidden; }
</style>
""", unsafe_allow_html=True)


# ─── Graph nodes in order (for display) ──────────────────────────────────────
GRAPH_NODES = [
    ("parse_input",  "Parse Input",    "Stores raw brief into BriefManager"),
    ("slm_validate", "SLM Validate",   "Validates brief, extracts tags"),
    ("reasoning",    "Reasoning",      "Generates image prompts"),
    ("image_gen",    "Image Gen",      "Renders images → saves to Desktop"),
]


# ─── Session state ────────────────────────────────────────────────────────────
for k, v in {
    "result":     None,
    "node_log":   {},    # node_id → "done" | "error" | "skipped"
    "chat_id":    None,
    "bm":         None,
    "error_tb":   None,
    "elapsed":    None,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ─── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🧪 RendrAI\nGraph Dev Tester")
    st.markdown('<div class="section">Input type</div>', unsafe_allow_html=True)
    input_type = st.selectbox("Input type", ["auto", "text", "csv"], index=0)

    st.markdown('<div class="section">Graph nodes</div>', unsafe_allow_html=True)
    for node_id, label, desc in GRAPH_NODES:
        status = st.session_state.node_log.get(node_id, "idle")
        st.markdown(f"""
        <div class="node-row {status}">
          <div class="dot {status}"></div>
          <div>
            <b>{label}</b><br>
            <span style="color:#55556a;font-size:0.68rem">{desc}</span>
          </div>
        </div>""", unsafe_allow_html=True)

    if st.session_state.chat_id:
        st.markdown('<div class="section">Session</div>', unsafe_allow_html=True)
        st.code(st.session_state.chat_id, language=None)

    if st.session_state.result is not None:
        if st.button("🔄 Reset", use_container_width=True):
            for k in ["result", "node_log", "chat_id", "bm", "error_tb", "elapsed"]:
                st.session_state[k] = {} if k == "node_log" else None
            st.rerun()


# ─── Main ─────────────────────────────────────────────────────────────────────
st.markdown("# RendrAI · Graph Dev Tester")
st.markdown(
    '<p style="color:#55556a;font-size:0.75rem;margin-top:-12px">'
    'Calls <code>build_dev_graph()</code> directly — no API, no S3.</p>',
    unsafe_allow_html=True,
)

st.markdown('<div class="section">Brief</div>', unsafe_allow_html=True)
brief_text = st.text_area(
    "brief",
    height=160,
    placeholder=(
        "A modern coffee brand targeting young urban professionals aged 22–35. "
        "Minimalist aesthetic with warm earthy tones. Key message: slow down and "
        "savour the moment. Generate 2 product lifestyle images for Instagram."
    ),
    label_visibility="collapsed",
)

run_col, _ = st.columns([1, 4])
with run_col:
    run = st.button("▶  RUN GRAPH", use_container_width=True)


# ─── Execute ──────────────────────────────────────────────────────────────────
if run:
    if not brief_text.strip():
        st.error("Brief is empty.")
    else:
        # Reset state
        st.session_state.result   = None
        st.session_state.node_log = {}
        st.session_state.error_tb = None

        chat_id = f"dev-{uuid.uuid4().hex[:8]}"
        st.session_state.chat_id = chat_id

        bm = BriefManager()
        bm.create(chat_id)          # creates store/{chat_id}.json on disk first
        st.session_state.bm = bm

        log.info("Starting dev graph  chat_id=%s", chat_id)

        with st.spinner("Running graph…"):
            t0 = time.time()
            try:
                graph  = build_dev_graph(bm, brief_text, input_type)
                result = graph.invoke({"chat_id": chat_id, "error": None})
                st.session_state.elapsed = round(time.time() - t0, 2)

                # ── Work out which nodes ran ──────────────────────────────
                # LangGraph doesn't emit per-node events in .invoke() by default.
                # We infer status from BriefManager state + result error field.
                error_msg = result.get("error")

                # parse_input always runs
                st.session_state.node_log["parse_input"] = "done"

                # slm_validate always runs (it's next)
                slm_ok = bm.get_tags(chat_id) is not None   # tags were stored
                st.session_state.node_log["slm_validate"] = "done" if not error_msg else "error"

                if not error_msg:
                    prompts = bm.get_prompts(chat_id) or []
                    st.session_state.node_log["reasoning"] = "done" if prompts else "error"
                    st.session_state.node_log["image_gen"] = "done" if prompts else "skipped"
                else:
                    st.session_state.node_log["reasoning"] = "skipped"
                    st.session_state.node_log["image_gen"] = "skipped"

                st.session_state.result = result

            except Exception:
                st.session_state.elapsed = round(time.time() - t0, 2)
                st.session_state.error_tb = traceback.format_exc()
                log.error("Graph crashed:\n%s", st.session_state.error_tb)
                # mark all as error
                for node_id, *_ in GRAPH_NODES:
                    st.session_state.node_log[node_id] = "error"

        st.rerun()


# ─── Results ─────────────────────────────────────────────────────────────────
if st.session_state.error_tb:
    st.markdown('<div class="section">Graph Error</div>', unsafe_allow_html=True)
    st.error("Graph raised an exception — see full traceback below.")
    st.code(st.session_state.error_tb, language="python")

elif st.session_state.result is not None:
    result  = st.session_state.result
    bm      = st.session_state.bm
    chat_id = st.session_state.chat_id

    # ── Metrics ──────────────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Status",   "✅ OK" if not result.get("error") else "❌ Error")
    col2.metric("Elapsed",  f"{st.session_state.elapsed}s")

    prompts = bm.get_prompts(chat_id) or []
    col3.metric("Prompts",  len(prompts))

    images  = bm.get_images(chat_id) or []
    col4.metric("Images",   len(images))

    # ── SLM error (brief rejected) ───────────────────────────────────────────
    if result.get("error"):
        st.markdown('<div class="section">Pipeline Error</div>', unsafe_allow_html=True)
        st.error(result["error"])

    # ── Tags from SLM ────────────────────────────────────────────────────────
    tags = bm.get_tags(chat_id) or []
    if tags:
        st.markdown('<div class="section">SLM Tags</div>', unsafe_allow_html=True)
        st.markdown(
            " ".join(f'<span class="tag">{t}</span>' for t in tags),
            unsafe_allow_html=True,
        )

    # ── Prompts from Reasoning ───────────────────────────────────────────────
    if prompts:
        st.markdown('<div class="section">Generated Prompts</div>', unsafe_allow_html=True)
        for i, p in enumerate(prompts, 1):
            st.markdown(
                f'<div class="prompt-box"><b style="color:#c8a96e">#{i}</b>  {p}</div>',
                unsafe_allow_html=True,
            )

    # ── Images saved locally ─────────────────────────────────────────────────
    if images:
        st.markdown('<div class="section">Generated Images (saved to Desktop)</div>',
                    unsafe_allow_html=True)
        cols = st.columns(min(len(images), 4))
        for i, img in enumerate(images):
            with cols[i % 4]:
                local_path = img.get("local_path", "")
                if local_path and Path(local_path).exists():
                    st.image(local_path, caption=f"prompt_{i}", use_column_width=True)
                    st.caption(f"`{local_path}`")
                else:
                    st.markdown(
                        f'<div class="prompt-box" style="color:#555570">'
                        f'prompt_{i}<br>{local_path or "no path"}</div>',
                        unsafe_allow_html=True,
                    )

    # ── Full BriefManager state ───────────────────────────────────────────────
    with st.expander("📋 Full BriefManager state"):
        try:
            st.json(bm.get_all(chat_id))
        except Exception:
            st.json({"note": "bm.get_all() not implemented — add it or use bm.__dict__"})

    with st.expander("📦 Raw graph result (BriefState)"):
        st.json(dict(result))