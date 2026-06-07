"""
RendrAI — ChatGPT-style frontend (Streamlit)
=============================================
Run with:
    streamlit run frontend/app.py
"""

import re
import uuid
import time
import streamlit as st


# ─── Page Config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="RendrAI",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ─── CSS ─────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

/* ── Global ─────────────────────────────────────────────── */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}
.stApp {
    background: #0a0a0a;
    color: #e5e5e5;
}

/* ── Hide default Streamlit chrome ───────────────────────── */
#MainMenu, footer, header { visibility: hidden; }
[data-testid="stToolbar"] { display: none; }
[data-testid="stDecoration"] { display: none; }
[data-testid="stHeader"] { display: none; }

/* ── Sidebar ─────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: #111111;
    border-right: 1px solid #1a1a1a;
    padding-top: 0;
}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
    color: #e5e5e5;
}
[data-testid="stSidebarContent"] {
    padding-top: 1rem;
}

/* ── Brand ────────────────────────────────────────────────── */
div.brand {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 0 16px 0;
}
div.brand-icon {
    width: 34px;
    height: 34px;
    border-radius: 8px;
    background: #f5c542;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 1.05rem;
    color: #0a0a0a;
    flex-shrink: 0;
}
div.brand-text {
    font-weight: 700;
    font-size: 1.05rem;
    color: #e5e5e5;
    letter-spacing: -0.01em;
}

/* ── Sidebar new-chat button ──────────────────────────────── */
[data-testid="stSidebar"] div[data-testid="stButton"]:first-of-type > button {
    background: #1a1a1a !important;
    color: #e5e5e5 !important;
    border: 1px dashed #333333 !important;
    border-radius: 10px !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.84rem !important;
    font-weight: 500 !important;
    padding: 10px 14px !important;
    transition: all 0.15s !important;
}
[data-testid="stSidebar"] div[data-testid="stButton"]:first-of-type > button:hover {
    background: #222222 !important;
    border-color: #f5c542 !important;
    color: #f5c542 !important;
}

/* ── Sidebar section labels ────────────────────────────────── */
div.sidebar-section {
    font-size: 0.68rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #555555;
    padding: 16px 0 8px 0;
    font-weight: 500;
}

/* ── Sidebar session buttons ──────────────────────────────── */
[data-testid="stSidebar"] .stButton > button {
    background: transparent !important;
    color: #999999 !important;
    border: none !important;
    border-radius: 8px !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.82rem !important;
    font-weight: 400 !important;
    padding: 8px 12px !important;
    text-align: left !important;
    justify-content: flex-start !important;
    transition: all 0.12s !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: #1a1a1a !important;
    color: #e5e5e5 !important;
}

/* ── Active session highlight ─────────────────────────────── */
[data-testid="stSidebar"] .active-session .stButton > button {
    background: #1e1e1e !important;
    color: #f5c542 !important;
    font-weight: 500 !important;
}

/* ── Delete button ────────────────────────────────────────── */
[data-testid="stSidebar"] .del-btn .stButton > button {
    color: #444444 !important;
    font-size: 0.75rem !important;
    padding: 6px 8px !important;
    min-width: 0 !important;
}
[data-testid="stSidebar"] .del-btn .stButton > button:hover {
    color: #ff6b6b !important;
    background: #1a0000 !important;
}

/* ── Chat messages — user ─────────────────────────────────── */
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
    background: transparent !important;
    flex-direction: row-reverse;
    max-width: 720px;
    margin: 0 auto 4px auto;
}
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="stMarkdownContainer"] {
    background: #1e1e1e;
    border-radius: 18px 18px 4px 18px;
    padding: 10px 16px;
}
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="chatAvatarIcon-user"] {
    background: #333333 !important;
}

/* ── Chat messages — assistant ────────────────────────────── */
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
    background: transparent !important;
    max-width: 720px;
    margin: 0 auto 4px auto;
}
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) [data-testid="chatAvatarIcon-assistant"] {
    background: #f5c542 !important;
    color: #0a0a0a !important;
}

/* ── Chat message text color ──────────────────────────────── */
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p {
    color: #e5e5e5 !important;
    font-size: 0.9rem;
    line-height: 1.6;
}
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] strong {
    color: #f5c542;
}

/* ── Welcome screen ───────────────────────────────────────── */
div.welcome {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 55vh;
    text-align: center;
    padding: 40px 20px;
}
div.welcome-icon {
    width: 56px;
    height: 56px;
    border-radius: 16px;
    background: #f5c542;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 1.5rem;
    color: #0a0a0a;
    margin-bottom: 20px;
}
div.welcome h1 {
    font-size: 1.5rem;
    font-weight: 600;
    color: #e5e5e5;
    margin-bottom: 8px;
    letter-spacing: -0.02em;
}
div.welcome p {
    color: #666666;
    font-size: 0.88rem;
    max-width: 400px;
    line-height: 1.5;
}

/* ── Chat input ───────────────────────────────────────────── */
[data-testid="stChatInput"] {
    background: transparent !important;
    border: none !important;
    max-width: 720px;
    margin: 0 auto;
}
[data-testid="stChatInput"] textarea {
    background: #141414 !important;
    border: 1px solid #2a2a2a !important;
    border-radius: 24px !important;
    color: #e5e5e5 !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.9rem !important;
    padding: 14px 52px 14px 20px !important;
    caret-color: #f5c542 !important;
}
[data-testid="stChatInput"] textarea:focus {
    border-color: #f5c542 !important;
    box-shadow: 0 0 0 1px #f5c54230 !important;
}
[data-testid="stChatInput"] textarea::placeholder {
    color: #555555 !important;
}
[data-testid="stChatInputSubmitButton"] button {
    background: #f5c542 !important;
    color: #0a0a0a !important;
    border-radius: 50% !important;
    border: none !important;
}
[data-testid="stChatInputSubmitButton"] button:hover {
    background: #e0b13a !important;
}

/* ── Bottom area gradient ─────────────────────────────────── */
[data-testid="stBottom"] {
    background: linear-gradient(transparent, #0a0a0a 40%) !important;
}
[data-testid="stBottomBlockContainer"] {
    max-width: 100% !important;
    padding-bottom: 16px;
}

/* ── Status pill ──────────────────────────────────────────── */
span.status-pill {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 0.72rem;
    font-weight: 500;
    margin-top: 8px;
}
span.status-generating {
    background: #f5c54215;
    color: #f5c542;
    border: 1px solid #f5c54230;
}
span.status-done {
    background: #4ade8015;
    color: #4ade80;
    border: 1px solid #4ade8030;
}

/* ── Generated images grid ────────────────────────────────── */
div.img-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
    margin-top: 12px;
    margin-bottom: 4px;
}
div.img-grid img {
    width: 100%;
    border-radius: 12px;
    border: 1px solid #1e1e1e;
    transition: transform 0.15s;
}
div.img-grid img:hover {
    transform: scale(1.02);
}

/* ── Scrollbar ────────────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #222222; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #333333; }

/* ── Streamlit image within chat ──────────────────────────── */
[data-testid="stChatMessage"] [data-testid="stImage"] {
    border-radius: 12px;
    overflow: hidden;
    border: 1px solid #1e1e1e;
}

/* ── Fix main content padding ─────────────────────────────── */
.stMainBlockContainer {
    padding-top: 2rem !important;
    max-width: 100% !important;
}

/* ── Force all backgrounds black ──────────────────────────── */
.stMain, [data-testid="stMain"],
.stAppViewBlockContainer,
[data-testid="stAppViewBlockContainer"],
section[data-testid="stMain"],
.stBottom, [data-testid="stBottom"],
[data-testid="stBottomBlockContainer"],
.block-container {
    background: #0a0a0a !important;
}

/* ── Divider ──────────────────────────────────────────────── */
[data-testid="stSidebar"] hr {
    border-color: #1a1a1a;
    margin: 8px 0;
}
</style>
""", unsafe_allow_html=True)


# ─── Session State Initialization ────────────────────────────────────────────

if "sessions" not in st.session_state:
    first_id = str(uuid.uuid4())[:8]
    st.session_state.sessions = {
        first_id: {
            "id": first_id,
            "title": "New chat",
            "messages": [],
            "created_at": time.time(),
        }
    }
    st.session_state.active_session = first_id

if "active_session" not in st.session_state:
    st.session_state.active_session = list(st.session_state.sessions.keys())[0]


# ─── Helper Functions ────────────────────────────────────────────────────────

def create_new_session():
    new_id = str(uuid.uuid4())[:8]
    st.session_state.sessions[new_id] = {
        "id": new_id,
        "title": "New chat",
        "messages": [],
        "created_at": time.time(),
    }
    st.session_state.active_session = new_id


def switch_session(session_id):
    st.session_state.active_session = session_id


def delete_session(session_id):
    if len(st.session_state.sessions) <= 1:
        return
    del st.session_state.sessions[session_id]
    if st.session_state.active_session == session_id:
        st.session_state.active_session = list(st.session_state.sessions.keys())[0]


def get_active_session():
    sid = st.session_state.active_session
    if sid not in st.session_state.sessions:
        sid = list(st.session_state.sessions.keys())[0]
        st.session_state.active_session = sid
    return st.session_state.sessions[sid]


def auto_title(text):
    text = text.strip()
    if len(text) <= 32:
        return text
    return text[:29] + "..."


def simulate_response(user_msg):
    lower = user_msg.lower()
    if any(w in lower for w in ["image", "generate", "create", "render", "photo", "picture", "design", "brand", "campaign"]):
        return {
            "text": (
                "I'd generate images based on your brief here. "
                "The pipeline would: **validate** your brief, **generate** optimized prompts, "
                "then **render** images using the AI model.\n\n"
                "**Pipeline status:** Not connected to backend yet."
            ),
            "images": [
                "https://placehold.co/512x512/1a1a1a/f5c542?text=Image+1&font=inter",
                "https://placehold.co/512x512/1a1a1a/f5c542?text=Image+2&font=inter",
            ],
        }
    return {
        "text": (
            "Thanks for your message! I'm **RendrAI** — an AI image generation pipeline. "
            "Describe a creative brief and I'll transform it into production-ready images.\n\n"
            "**Pipeline status:** Frontend-only mode (backend not connected)."
        ),
        "images": [],
    }


# ─── Sidebar ─────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("""
    <div class="brand">
        <div class="brand-icon">R</div>
        <div class="brand-text">RendrAI</div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("+ New chat", use_container_width=True, key="new_chat"):
        create_new_session()
        st.rerun()

    st.markdown('<div class="sidebar-section">Recent</div>', unsafe_allow_html=True)

    sorted_sessions = sorted(
        st.session_state.sessions.values(),
        key=lambda s: s["created_at"],
        reverse=True,
    )

    for sess in sorted_sessions:
        is_active = sess["id"] == st.session_state.active_session
        title = sess["title"]
        icon = "💬 " if not is_active else "▸ "

        col1, col2 = st.columns([6, 1])
        with col1:
            container = st.container()
            if is_active:
                container.markdown('<div class="active-session">', unsafe_allow_html=True)
            if container.button(
                f"{icon}{title}",
                key=f"s_{sess['id']}",
                use_container_width=True,
            ):
                switch_session(sess["id"])
                st.rerun()
            if is_active:
                container.markdown('</div>', unsafe_allow_html=True)

        with col2:
            if len(st.session_state.sessions) > 1:
                del_container = st.container()
                del_container.markdown('<div class="del-btn">', unsafe_allow_html=True)
                if del_container.button("✕", key=f"d_{sess['id']}"):
                    delete_session(sess["id"])
                    st.rerun()
                del_container.markdown('</div>', unsafe_allow_html=True)


# ─── Main Chat Area ─────────────────────────────────────────────────────────

session = get_active_session()
messages = session["messages"]

if not messages:
    st.markdown("""
    <div class="welcome">
        <div class="welcome-icon">R</div>
        <h1>What would you like to create?</h1>
        <p>Describe a creative brief and RendrAI will transform it into
        production-ready images using AI.</p>
    </div>
    """, unsafe_allow_html=True)

for msg in messages:
    if msg["role"] == "user":
        with st.chat_message("user"):
            st.markdown(msg["content"])
    else:
        with st.chat_message("assistant"):
            st.markdown(msg["content"])

            if msg.get("images"):
                img_tags = "".join(
                    f'<img src="{url}" alt="Generated image" />'
                    for url in msg["images"]
                )
                st.markdown(
                    f'<div class="img-grid">{img_tags}</div>'
                    f'<span class="status-pill status-done">{len(msg["images"])} images generated</span>',
                    unsafe_allow_html=True,
                )

if prompt := st.chat_input("Describe your creative brief..."):
    messages.append({
        "role": "user",
        "content": prompt,
        "timestamp": time.time(),
    })

    if session["title"] == "New chat":
        session["title"] = auto_title(prompt)

    response = simulate_response(prompt)
    messages.append({
        "role": "assistant",
        "content": response["text"],
        "images": response["images"],
        "timestamp": time.time(),
        "status": "done",
    })

    st.rerun()
