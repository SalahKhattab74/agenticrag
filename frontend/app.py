"""Gradio frontend — login, chat, and admin panel for the Epsilon platform.

The app has two screens (login and main). The main screen is a Tabs container
with one Chat tab visible to every user and three admin-only tabs (Channels,
Reports, Ingest PDF) shown when the user's JWT carries the `admin_panel`
feature. All backend calls go through helper functions at the top.

Launch modes:
  - Default: mount Gradio inside a FastAPI app that strips X-Frame-Options so
    Lightning AI's iframe wrapper (web-ui?port=7860) renders the UI.
  - GRADIO_SHARE=true: skip the wrapper and call app.launch(share=True) to get
    a public https://*.gradio.live tunnel URL instead.
"""
import base64
import os
from pathlib import Path

import requests

# gradio_client 1.3.0 (shipped with gradio==4.44.1) crashes when walking a
# JSON schema that contains boolean values (Pydantic v2 emits
# `additionalProperties: true` for `dict[str, Any]`). The two functions below
# guard the offending code paths until we can move to a newer gradio.
import gradio_client.utils as _gc_utils

_orig_get_type = _gc_utils.get_type
_orig_jstpt = _gc_utils._json_schema_to_python_type


def _patched_get_type(schema):
    if not isinstance(schema, dict):
        return None
    return _orig_get_type(schema)


def _patched_jstpt(schema, defs=None):
    if isinstance(schema, bool):
        return "Any" if schema else "Never"
    return _orig_jstpt(schema, defs)


_gc_utils.get_type = _patched_get_type
_gc_utils._json_schema_to_python_type = _patched_jstpt

import gradio as gr  # noqa: E402  — must come after the patch above


BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
LOGO_PATH = Path(__file__).resolve().parent / "assets" / "epsilon-logo.jpg"


def _logo_data_uri() -> str:
    try:
        raw = LOGO_PATH.read_bytes()
    except OSError:
        return ""
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


LOGO_DATA_URI = _logo_data_uri()


def brand_header(subtitle: str = "") -> str:
    logo = (
        f'<img class="brand-logo" src="{LOGO_DATA_URI}" alt="Epsilon AI logo">'
        if LOGO_DATA_URI
        else '<div class="brand-logo-fallback">E</div>'
    )
    subtitle_html = f'<div class="brand-subtitle">{subtitle}</div>' if subtitle else ""
    return f"""
    <div class="brand-header">
        <div class="brand-mark">{logo}</div>
        <div class="brand-copy">
            <div class="brand-kicker">Secure Intelligence Workspace</div>
            <div class="brand-title">EPSILON AI PLATFORM</div>
            {subtitle_html}
        </div>
    </div>
    """


THEME_CSS = """
:root {
    --epsilon-blue: #1919e8;
    --epsilon-blue-deep: #060b5f;
    --epsilon-blue-mid: #1020a8;
    --epsilon-orange: #ff7900;
    --epsilon-orange-soft: #ffad5c;
    --epsilon-ink: #f8fbff;
    --epsilon-muted: #cbd7ff;
    --epsilon-panel: rgba(7, 14, 88, 0.82);
    --epsilon-panel-strong: rgba(5, 10, 62, 0.92);
    --epsilon-line: rgba(255, 121, 0, 0.44);
    --epsilon-input: rgba(2, 8, 57, 0.82);
}

html,
body,
.gradio-container,
.main,
.app {
    min-height: 100%;
    background:
        linear-gradient(135deg, rgba(255, 121, 0, 0.20) 0%, rgba(255, 121, 0, 0.04) 31%, transparent 52%),
        radial-gradient(circle at 88% 11%, rgba(255, 121, 0, 0.35), transparent 30%),
        linear-gradient(150deg, var(--epsilon-blue) 0%, #1118ba 44%, var(--epsilon-blue-deep) 100%) !important;
    color: var(--epsilon-ink) !important;
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
}

.gradio-container {
    max-width: none !important;
}

.contain {
    max-width: 1220px !important;
}

#component-0,
.block,
.form,
.panel,
.tabs,
.tabitem,
.prose,
.markdown,
.wrap,
.gap,
.gr-group,
.gr-box {
    background: transparent !important;
    border-color: var(--epsilon-line) !important;
    color: var(--epsilon-ink) !important;
}

.login-panel,
.app-shell {
    width: min(1180px, calc(100vw - 32px));
    margin: 22px auto !important;
    padding: 22px !important;
    background: linear-gradient(180deg, var(--epsilon-panel), rgba(4, 10, 66, 0.72)) !important;
    border: 1px solid var(--epsilon-line) !important;
    box-shadow: 0 24px 80px rgba(0, 0, 0, 0.32), inset 0 1px 0 rgba(255, 255, 255, 0.08);
    backdrop-filter: blur(16px);
}

.brand-header {
    display: flex;
    align-items: center;
    gap: 18px;
    padding: 18px 20px;
    margin-bottom: 18px;
    background: linear-gradient(90deg, rgba(255, 121, 0, 0.96), rgba(255, 121, 0, 0.76) 34%, rgba(7, 20, 135, 0.78));
    border: 1px solid rgba(255, 255, 255, 0.18);
    box-shadow: 0 18px 42px rgba(3, 6, 46, 0.35);
}

.brand-mark {
    width: 74px;
    height: 74px;
    display: grid;
    place-items: center;
    flex: 0 0 auto;
    background: var(--epsilon-blue);
    border: 2px solid rgba(255, 255, 255, 0.82);
    box-shadow: 0 12px 30px rgba(0, 0, 0, 0.28);
    overflow: hidden;
}

.brand-logo {
    width: 100%;
    height: 100%;
    object-fit: cover;
}

.brand-logo-fallback {
    color: white;
    font-size: 38px;
    font-weight: 900;
}

.brand-copy {
    min-width: 0;
}

.brand-kicker {
    color: rgba(255, 255, 255, 0.82);
    font-size: 12px;
    font-weight: 800;
    letter-spacing: 0;
    text-transform: uppercase;
}

.brand-title {
    color: white;
    font-size: 34px;
    line-height: 1.05;
    font-weight: 900;
    letter-spacing: 0;
}

.brand-subtitle {
    margin-top: 7px;
    color: #fff4e9;
    font-size: 15px;
    font-weight: 600;
}

.session-banner {
    padding: 10px 14px;
    margin-bottom: 14px;
    color: var(--epsilon-ink) !important;
    background: rgba(255, 121, 0, 0.16) !important;
    border: 1px solid rgba(255, 121, 0, 0.38) !important;
}

h1,
h2,
h3,
label,
.prose h1,
.prose h2,
.prose h3,
.markdown h1,
.markdown h2,
.markdown h3,
.gradio-container label,
.gradio-container span,
.gradio-container p {
    color: var(--epsilon-ink) !important;
}

.prose code,
.markdown code {
    color: #fff3e6 !important;
    background: transparent !important;
    border: 0 !important;
    padding: 0 !important;
    font: inherit !important;
    font-weight: 800 !important;
}

.prose pre,
.markdown pre {
    width: 100% !important;
    max-width: 100% !important;
    overflow-x: auto !important;
    color: var(--epsilon-ink) !important;
    background: rgba(2, 8, 57, 0.92) !important;
    border: 1px solid rgba(255, 121, 0, 0.38) !important;
    padding: 14px 16px !important;
}

.prose pre code,
.markdown pre code {
    display: block !important;
    color: var(--epsilon-ink) !important;
    font-family: Consolas, "SFMono-Regular", Menlo, monospace !important;
    font-size: 15px !important;
    font-weight: 600 !important;
    white-space: pre !important;
}

input,
textarea,
select,
.input-container,
.wrap textarea,
.wrap input,
[data-testid="textbox"],
.gradio-textbox,
.gradio-dropdown,
.gradio-file,
.gradio-dataframe,
.gradio-chatbot {
    color: var(--epsilon-ink) !important;
    background: var(--epsilon-input) !important;
    border-color: rgba(255, 121, 0, 0.42) !important;
    box-shadow: none !important;
}

input::placeholder,
textarea::placeholder {
    color: rgba(203, 215, 255, 0.72) !important;
}

.epsilon-selectbox,
.epsilon-selectbox > div,
.epsilon-selectbox .wrap,
.epsilon-selectbox .input-container {
    width: 100% !important;
    max-width: 100% !important;
    min-width: 0 !important;
    min-height: clamp(52px, 7vw, 64px) !important;
}

.epsilon-selectbox input,
.epsilon-selectbox select,
.epsilon-selectbox button {
    font-size: clamp(15px, 1.5vw, 20px) !important;
    font-weight: 800 !important;
}

.epsilon-selectbox {
    border: 1px solid rgba(255, 121, 0, 0.70) !important;
    background: rgba(7, 15, 103, 0.88) !important;
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.04), 0 12px 28px rgba(0, 0, 0, 0.18) !important;
}

.epsilon-selectbox .wrap-inner {
    min-height: clamp(52px, 7vw, 64px) !important;
    display: flex !important;
    align-items: center !important;
    padding: 0 clamp(34px, 5vw, 56px) 0 clamp(12px, 2vw, 18px) !important;
    max-width: 100% !important;
    overflow: hidden !important;
}

.epsilon-selectbox .secondary-wrap {
    min-height: clamp(52px, 7vw, 64px) !important;
    min-width: 0 !important;
    max-width: 100% !important;
    overflow: hidden !important;
}

.epsilon-selectbox input {
    cursor: pointer !important;
    width: 100% !important;
    min-width: 0 !important;
    height: clamp(52px, 7vw, 64px) !important;
    min-height: clamp(52px, 7vw, 64px) !important;
    margin: 0 !important;
    padding: 0 !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    white-space: nowrap !important;
    line-height: normal !important;
}

.epsilon-selectbox label,
.epsilon-inputbox label,
.epsilon-filebox label {
    font-size: 18px !important;
    font-weight: 800 !important;
    color: white !important;
}

.epsilon-selectbox svg {
    color: white !important;
    width: clamp(16px, 2.4vw, 22px) !important;
    height: clamp(16px, 2.4vw, 22px) !important;
}

.options {
    width: min(720px, calc(100vw - 32px)) !important;
    max-width: calc(100vw - 32px) !important;
    color: var(--epsilon-ink) !important;
    background: rgba(3, 8, 57, 0.98) !important;
    border: 1px solid rgba(255, 121, 0, 0.70) !important;
    box-shadow: 0 18px 44px rgba(0, 0, 0, 0.38) !important;
    border-radius: 0 !important;
}

.options .item {
    min-height: 48px !important;
    max-width: 100% !important;
    color: var(--epsilon-ink) !important;
    background: rgba(3, 8, 57, 0.98) !important;
    border-bottom: 1px solid rgba(255, 121, 0, 0.22) !important;
    font-size: clamp(14px, 1.6vw, 18px) !important;
    font-weight: 800 !important;
    overflow-wrap: anywhere !important;
}

.options .item:hover,
.options .active {
    background: linear-gradient(90deg, rgba(255, 121, 0, 0.88), rgba(255, 121, 0, 0.52)) !important;
    color: white !important;
}

.epsilon-inputbox textarea,
.epsilon-inputbox input {
    min-height: 64px !important;
    font-size: 18px !important;
    font-weight: 700 !important;
    padding: 16px 18px !important;
}

.epsilon-filebox,
.epsilon-filebox > div,
.epsilon-filebox .upload-container,
.epsilon-filebox .file-preview,
.epsilon-filebox .file-preview-holder {
    min-height: 94px !important;
    font-size: 18px !important;
    font-weight: 700 !important;
}

.epsilon-action-button {
    min-height: 64px !important;
    font-size: 22px !important;
    font-weight: 900 !important;
}

textarea:disabled,
input:disabled,
button:disabled,
.disabled,
[aria-disabled="true"] {
    opacity: 1 !important;
    color: rgba(248, 251, 255, 0.82) !important;
    -webkit-text-fill-color: rgba(248, 251, 255, 0.82) !important;
    background:
        linear-gradient(90deg, rgba(255, 121, 0, 0.16), rgba(255, 121, 0, 0.34), rgba(255, 121, 0, 0.16)),
        rgba(2, 8, 57, 0.92) !important;
    border-color: rgba(255, 121, 0, 0.62) !important;
}

[class*="progress"],
[class*="status"],
[class*="generating"],
[class*="pending"],
[data-testid*="progress"],
[data-testid*="status"] {
    color: white !important;
    background: rgba(3, 8, 57, 0.92) !important;
    border-color: rgba(255, 121, 0, 0.58) !important;
}

[class*="progress"] *,
[class*="status"] *,
[class*="generating"] *,
[class*="pending"] *,
[data-testid*="progress"] *,
[data-testid*="status"] * {
    color: white !important;
}

.progress-text,
.eta,
.queue,
.queue-status,
.generating,
.pending {
    color: #fff4e9 !important;
    font-size: 16px !important;
    font-weight: 900 !important;
    letter-spacing: 0 !important;
    text-shadow: 0 1px 10px rgba(255, 121, 0, 0.35);
}

.progress-bar,
[class*="progress-bar"],
[class*="progress_bar"],
[role="progressbar"] {
    background: rgba(2, 8, 57, 0.95) !important;
    border: 1px solid rgba(255, 121, 0, 0.55) !important;
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.05) !important;
}

.progress-bar > *,
[class*="progress-bar"] > *,
[class*="progress_bar"] > *,
[role="progressbar"] > * {
    background: linear-gradient(90deg, var(--epsilon-orange), var(--epsilon-orange-soft), var(--epsilon-orange)) !important;
}

.spinner,
.loader,
[class*="spinner"],
[class*="loader"] {
    border-color: rgba(255, 121, 0, 0.30) !important;
    border-top-color: var(--epsilon-orange) !important;
    color: var(--epsilon-orange) !important;
}

.wrap:has(textarea:disabled),
.input-container:has(textarea:disabled),
.wrap:has(input:disabled),
.input-container:has(input:disabled) {
    background:
        linear-gradient(90deg, rgba(255, 121, 0, 0.12), rgba(255, 121, 0, 0.28), rgba(255, 121, 0, 0.12)),
        rgba(3, 8, 57, 0.92) !important;
    border-color: rgba(255, 121, 0, 0.66) !important;
    box-shadow: 0 0 28px rgba(255, 121, 0, 0.18) !important;
}

.epsilon-chatbot,
.epsilon-chatbot > div,
.epsilon-chatbot .wrap,
.epsilon-chatbot .chatbot,
.epsilon-chatbot [data-testid="bot"],
.epsilon-chatbot [data-testid="user"] {
    background:
        linear-gradient(180deg, rgba(4, 10, 68, 0.62), rgba(4, 9, 56, 0.86)) !important;
    border: 0 !important;
    box-shadow: none !important;
    color: var(--epsilon-ink) !important;
}

.epsilon-chatbot {
    padding: 0 !important;
    border: 0 !important;
    background: transparent !important;
}

.epsilon-chatbot .chatbot {
    padding: 22px 28px !important;
    border-radius: 0 !important;
}

.epsilon-chatbot .message-row,
.epsilon-chatbot .bubble-wrap,
.epsilon-chatbot .bot,
.epsilon-chatbot .user {
    width: 100% !important;
    max-width: 100% !important;
    background: transparent !important;
    border: 0 !important;
    box-shadow: none !important;
}

.epsilon-chatbot .message {
    max-width: min(86%, 980px) !important;
    border: 0 !important;
    box-shadow: none !important;
    outline: 0 !important;
    color: var(--epsilon-ink) !important;
    overflow-wrap: anywhere !important;
    word-break: normal !important;
}

.epsilon-chatbot .message.bot,
.epsilon-chatbot .bot .message,
.epsilon-chatbot .message-row.bot .message {
    margin: 14px auto 28px 0 !important;
    padding: 22px 24px !important;
    background:
        linear-gradient(180deg, rgba(10, 20, 105, 0.72), rgba(4, 10, 65, 0.62)) !important;
    border-left: 4px solid rgba(255, 121, 0, 0.82) !important;
    border-radius: 0 8px 8px 0 !important;
}

.epsilon-chatbot .message.user,
.epsilon-chatbot .user .message,
.epsilon-chatbot .message-row.user .message {
    margin: 14px 0 28px auto !important;
    padding: 12px 16px !important;
    max-width: min(62%, 620px) !important;
    color: white !important;
    background: linear-gradient(135deg, rgba(255, 121, 0, 0.98), rgba(200, 72, 0, 0.94)) !important;
    border: 0 !important;
    border-radius: 8px !important;
    box-shadow: 0 12px 26px rgba(255, 121, 0, 0.18) !important;
}

.epsilon-chatbot .message * {
    background: transparent !important;
    border: 0 !important;
    box-shadow: none !important;
}

.epsilon-chatbot .markdown,
.epsilon-chatbot .prose {
    width: 100% !important;
    max-width: 100% !important;
    color: var(--epsilon-ink) !important;
    overflow-wrap: anywhere !important;
    word-break: normal !important;
}

.epsilon-chatbot .markdown p,
.epsilon-chatbot .prose p,
.epsilon-chatbot .markdown li,
.epsilon-chatbot .prose li {
    color: var(--epsilon-ink) !important;
    font-size: 18px !important;
    line-height: 1.6 !important;
}

.epsilon-chatbot .message.user .markdown p,
.epsilon-chatbot .user .message .markdown p {
    color: white !important;
    margin: 0 !important;
    line-height: 1.35 !important;
}

.epsilon-chatbot .markdown ul,
.epsilon-chatbot .markdown ol,
.epsilon-chatbot .prose ul,
.epsilon-chatbot .prose ol {
    margin: 12px 0 12px 26px !important;
    padding: 0 !important;
}

.epsilon-chatbot .markdown li,
.epsilon-chatbot .prose li {
    margin: 10px 0 !important;
    padding-left: 6px !important;
}

.epsilon-chatbot .markdown a,
.epsilon-chatbot .prose a {
    color: #ffd5b0 !important;
    text-decoration: underline !important;
    text-decoration-color: rgba(255, 121, 0, 0.65) !important;
    text-underline-offset: 3px !important;
    border: 0 !important;
    background: transparent !important;
}

.epsilon-chatbot pre,
.epsilon-chatbot code {
    border: 0 !important;
}

.epsilon-composer {
    margin-top: 18px !important;
    padding: 12px !important;
    background: rgba(4, 9, 56, 0.72) !important;
    border: 1px solid rgba(255, 121, 0, 0.28) !important;
}

.epsilon-chat-input textarea,
.epsilon-chat-input input {
    min-height: 64px !important;
    padding: 18px !important;
    font-size: 18px !important;
    background: rgba(2, 8, 57, 0.94) !important;
    border: 0 !important;
}

.epsilon-send-button {
    min-height: 64px !important;
    font-size: 20px !important;
}

button,
.gradio-button,
button.primary {
    color: white !important;
    background: linear-gradient(135deg, var(--epsilon-orange), #e65d00) !important;
    border: 1px solid rgba(255, 220, 190, 0.44) !important;
    box-shadow: 0 10px 22px rgba(255, 121, 0, 0.22) !important;
    font-weight: 800 !important;
}

button:hover,
.gradio-button:hover {
    filter: brightness(1.08);
    transform: translateY(-1px);
}

button.secondary,
button.stop {
    background: linear-gradient(135deg, #0d1eb7, #070c65) !important;
    border-color: rgba(255, 121, 0, 0.48) !important;
}

.tabs > .tab-nav,
.tab-nav,
.tabs button,
[role="tablist"] {
    background: rgba(3, 8, 57, 0.72) !important;
    border-color: rgba(255, 121, 0, 0.34) !important;
}

[role="tab"],
.tab-nav button {
    color: var(--epsilon-muted) !important;
    background: transparent !important;
    border-color: transparent !important;
}

[role="tab"][aria-selected="true"],
.tab-nav button.selected {
    color: white !important;
    background: linear-gradient(135deg, rgba(255, 121, 0, 0.96), rgba(255, 121, 0, 0.64)) !important;
}

table,
thead,
tbody,
tr,
td,
th,
.table-wrap,
.dataframe,
.ag-theme-quartz,
.ag-root-wrapper,
.ag-root,
.ag-header,
.ag-row,
.ag-cell {
    color: var(--epsilon-ink) !important;
    background: rgba(3, 8, 57, 0.76) !important;
    border-color: rgba(255, 121, 0, 0.30) !important;
}

th,
.ag-header,
.ag-header-cell {
    background: rgba(255, 121, 0, 0.26) !important;
    color: white !important;
    font-weight: 800 !important;
}

.ag-row-even,
.ag-row-odd {
    background: rgba(6, 14, 94, 0.86) !important;
}

.ag-row-hover,
tr:hover {
    background: rgba(255, 121, 0, 0.18) !important;
}

.file-preview,
.upload-container,
.file,
.file-preview-holder {
    background: rgba(4, 10, 66, 0.84) !important;
    border-color: rgba(255, 121, 0, 0.42) !important;
    color: var(--epsilon-ink) !important;
}

.toast-wrap,
.toast {
    background: var(--epsilon-panel-strong) !important;
    color: var(--epsilon-ink) !important;
    border-color: var(--epsilon-line) !important;
}

hr {
    border-color: rgba(255, 121, 0, 0.38) !important;
}

@media (max-width: 720px) {
    .login-panel,
    .app-shell {
        width: min(100vw - 18px, 1180px);
        margin: 9px auto !important;
        padding: 13px !important;
    }

    .brand-header {
        align-items: flex-start;
        gap: 12px;
        padding: 14px;
    }

    .brand-mark {
        width: 54px;
        height: 54px;
    }

    .brand-title {
        font-size: 24px;
        line-height: 1.1;
    }

    .brand-subtitle {
        font-size: 13px;
    }

    .epsilon-selectbox,
    .epsilon-selectbox > div,
    .epsilon-selectbox .wrap,
    .epsilon-selectbox .input-container,
    .epsilon-selectbox .wrap-inner,
    .epsilon-selectbox .secondary-wrap,
    .epsilon-selectbox input {
        min-height: 52px !important;
        height: auto !important;
    }

    .epsilon-selectbox .wrap-inner {
        padding: 0 32px 0 12px !important;
    }

    .epsilon-selectbox input {
        height: 52px !important;
        font-size: 15px !important;
    }

    .options {
        width: calc(100vw - 24px) !important;
        max-width: calc(100vw - 24px) !important;
    }
}
"""

# Authorized-feature options offered when creating or editing a channel.
FEATURE_OPTIONS = [
    "chatbot",
    "document_search",
    "tables_search",
    "voice_agent",
    "admin_panel",
]


# ── API helpers ───────────────────────────────────────────────────────────────

def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def api_login(username: str, password: str) -> dict:
    r = requests.post(
        f"{BACKEND_URL}/login",
        json={"username": username, "password": password},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def api_logout(token: str) -> None:
    """Best-effort logout. Token still expires naturally if the call fails."""
    try:
        requests.post(
            f"{BACKEND_URL}/logout",
            headers=_auth_headers(token),
            timeout=10,
        )
    except Exception:
        pass


def api_orchestrate(token: str, action: str, payload: dict | None = None) -> dict:
    r = requests.post(
        f"{BACKEND_URL}/orchestrate",
        json={"action": action, "payload": payload or {}},
        headers=_auth_headers(token),
        timeout=600,
    )
    r.raise_for_status()
    return r.json()


def api_upload(token: str, file_path: str, filename: str) -> dict:
    with open(file_path, "rb") as f:
        r = requests.post(
            f"{BACKEND_URL}/upload",
            files={"file": (filename, f, "application/pdf")},
            headers=_auth_headers(token),
            timeout=120,
        )
    r.raise_for_status()
    return r.json()


def api_admin_channels(token: str) -> list[dict]:
    r = requests.get(
        f"{BACKEND_URL}/admin/channels",
        headers=_auth_headers(token),
        timeout=10,
    )
    r.raise_for_status()
    return r.json().get("channels", [])


def api_admin_create_channel(token: str, name: str, description: str, features: list[str]) -> dict:
    r = requests.post(
        f"{BACKEND_URL}/admin/channels",
        json={
            "name": name,
            "description": description,
            "authorized_features": features,
        },
        headers=_auth_headers(token),
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def api_admin_create_rag_channel(token: str, channelid: int, name: str, description: str) -> dict:
    r = requests.post(
        f"{BACKEND_URL}/admin/channels/{channelid}/rag-channel",
        json={"name": name, "description": description},
        headers=_auth_headers(token),
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def api_admin_list_reports(token: str, channelid: int) -> list[dict]:
    r = requests.get(
        f"{BACKEND_URL}/admin/channels/{channelid}/reports",
        headers=_auth_headers(token),
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("reports", [])


def api_admin_delete_report(token: str, report_id: str) -> dict:
    r = requests.delete(
        f"{BACKEND_URL}/admin/reports/{report_id}",
        headers=_auth_headers(token),
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_admin(session: dict | None) -> bool:
    return (
        session is not None
        and "admin_panel" in session.get("authorized_features", [])
    )


def _err_msg(exc: Exception) -> str:
    """Render a user-facing error string from any exception."""
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        if exc.response.status_code == 401:
            return "Your session has expired. Please log out and log in again."
        try:
            detail = exc.response.json().get("detail")
        except Exception:
            detail = exc.response.text
        return f"Backend error ({exc.response.status_code}): {detail}"
    return f"Error: {exc}"


def _as_blockquote(text: str) -> str:
    """Wrap multi-line text as a Markdown blockquote so chunk content
    renders as a distinct block inside the chat bubble. Empty lines are
    kept as `>` so the quote doesn't break visually mid-chunk."""
    text = (text or "").strip()
    if not text:
        return ""
    return "\n".join(f"> {line}" if line else ">" for line in text.split("\n"))


def format_query_response(result: dict) -> str:
    """Render a /orchestrate?action=query response as Markdown for the chat.

    Returns the LLM's grounded answer only. The source chunks are still
    retrieved server-side (so the LLM can cite page numbers) but are no
    longer shown in the chat bubble. If the LLM is unavailable
    (`answer` empty), we fall back to a short retrieval-only summary so
    the user still sees something useful.
    """
    if not result.get("success"):
        return f"Query failed: {result.get('message', 'Unknown error.')}"

    answer = (result.get("answer") or "").strip()
    if answer:
        return answer

    # Fallback: LLM disabled or failed. Show a compact list of the top
    # source pages instead of going completely silent.
    count = result.get("result_count", 0)
    rows = result.get("results_metadata", []) or []
    if count == 0 or not rows:
        return "No relevant results found for your question."

    lines: list[str] = [f"Found **{count}** relevant result(s):"]
    primary_idx = 0
    for r in rows:
        if r.get("is_neighbour"):
            continue
        primary_idx += 1
        score = r.get("rerank_score") if r.get("rerank_score") is not None else r.get("rrf_score")
        score_str = f"{score:.3f}" if score is not None else "N/A"
        section = (r.get("section_title") or "").strip()
        section_part = f" | Section: *{section}*" if section else ""
        lines.append(
            f"**{primary_idx}.** Page {r['page_number']}{section_part} | Score: {score_str}"
        )
    return "\n".join(lines)


def format_ingest_response(result: dict) -> str:
    """Render a /orchestrate?action=ingest response as a Markdown summary."""
    if not result.get("success"):
        return f"Ingestion failed: {result.get('message', 'Unknown error.')}"

    return (
        f"Ingestion complete.\n\n"
        f"- **Report ID:** {result.get('report_id', 'N/A')}\n"
        f"- **Pages processed:** {result.get('pages_processed', '?')} / {result.get('pages_total', '?')}\n"
        f"- **Chunks inserted:** {result.get('chunks_inserted', '?')}\n"
        f"- **Latency:** {result.get('total_latency_ms', '?')} ms"
    )


def _channels_table(channels: list[dict]) -> list[list]:
    return [
        [
            c["channelid"],
            c["name"],
            c.get("rag_channel_id") or "— not linked —",
            ", ".join(c.get("authorized_features") or []),
        ]
        for c in channels
    ]


def _unlinked_choices(channels: list[dict]) -> list[tuple[str, int]]:
    return [(c["name"], c["channelid"]) for c in channels if not c.get("rag_channel_id")]


def _linked_choices(channels: list[dict]) -> list[tuple[str, int]]:
    return [(c["name"], c["channelid"]) for c in channels if c.get("rag_channel_id")]


def _ingest_choices(channels: list[dict]) -> list[tuple[str, str]]:
    return [
        (c["name"], c["rag_channel_id"])
        for c in channels
        if c.get("rag_channel_id")
    ]


def _reports_table(reports: list[dict]) -> list[list]:
    return [
        [
            r["report_id"],
            r["filename"],
            r.get("title") or "",
            r.get("page_count", 0),
            r.get("chunk_count", 0),
            (r.get("created_at") or "")[:19].replace("T", " "),
        ]
        for r in reports
    ]


def _report_delete_choices(reports: list[dict]) -> list[tuple[str, str]]:
    return [
        (f"{r['filename']} ({r['report_id'][:8]}…)", r["report_id"])
        for r in reports
    ]


# ── Gradio app ────────────────────────────────────────────────────────────────

def _first_choice_value(choices: list[tuple[str, object]]):
    """Return the value part of the first Dropdown choice, if one exists."""
    return choices[0][1] if choices else None


with gr.Blocks(
    title="Epsilon AI Platform",
    css=THEME_CSS,
    theme=gr.themes.Base(
        primary_hue="orange",
        secondary_hue="blue",
        neutral_hue="slate",
    ),
) as app:

    # session holds the bearer token and the user profile after login.
    # channels_state caches the channel list for admin tab refreshes.
    session_state  = gr.State(value=None)
    channels_state = gr.State(value=[])

    # ── Login screen ──────────────────────────────────────────────────────────
    with gr.Column(visible=True, elem_classes=["login-panel"]) as login_screen:
        gr.HTML(brand_header("Sign in to your tenant workspace."))
        username_input = gr.Textbox(label="Username", placeholder="Enter username")
        password_input = gr.Textbox(label="Password", placeholder="Enter password", type="password")
        login_btn      = gr.Button("Login", variant="primary")
        login_msg      = gr.Markdown("")

    # ── Main screen ───────────────────────────────────────────────────────────
    with gr.Column(visible=False, elem_classes=["app-shell"]) as main_screen:
        gr.HTML(brand_header("Chat, manage channels, review reports, and ingest documents."))
        session_label = gr.Markdown("", elem_classes=["session-banner"])

        with gr.Tabs():

            # Chat tab — visible to every authenticated user.
            with gr.Tab("Chat"):
                chatbot = gr.Chatbot(
                    label="Epsilon AI",
                    type="messages",
                    height=560,
                    show_label=False,
                    elem_classes=["epsilon-chatbot"],
                )
                with gr.Row(elem_classes=["epsilon-composer"]):
                    chat_input = gr.Textbox(
                        placeholder="Ask anything...",
                        show_label=False,
                        scale=8,
                        elem_classes=["epsilon-chat-input"],
                    )
                    send_btn = gr.Button(
                        "Send",
                        variant="primary",
                        scale=1,
                        elem_classes=["epsilon-send-button"],
                    )

            # Channels tab — admin only. Three sections:
            #   1. Read-only overview table of every control channel.
            #   2. Form to add a brand-new control channel.
            #   3. Form to create a RAG channel and link it to a control channel.
            with gr.Tab("Channels", visible=False) as channels_tab:
                gr.Markdown("## Channels overview")
                channels_table = gr.Dataframe(
                    headers=["channelid", "name", "rag_channel_id", "authorized_features"],
                    datatype=["number", "str", "str", "str"],
                    interactive=False,
                    wrap=True,
                )
                refresh_channels_btn = gr.Button("Refresh channels")

                gr.Markdown("---")
                gr.Markdown("## Add a new channel")
                gr.Markdown(
                    "Creates a tenant row in `control.channel`. RAG linking is a "
                    "separate step below — fill that in next to enable ingestion."
                )
                add_channel_name = gr.Textbox(
                    label="Channel name (required, unique)",
                    placeholder="e.g. Acme Industries",
                )
                add_channel_description = gr.Textbox(
                    label="Description (optional)",
                    placeholder="Stored in metadata.description",
                )
                add_channel_features = gr.CheckboxGroup(
                    label="Authorized features",
                    choices=FEATURE_OPTIONS,
                    value=["chatbot", "document_search"],
                )
                add_channel_btn = gr.Button("Add channel", variant="primary")
                add_channel_status = gr.Markdown("")

                gr.Markdown("---")
                gr.Markdown("## Create & link a RAG channel")
                gr.Markdown(
                    "Pick a control channel that is **not yet linked**, then click "
                    "**Create & link**. A new RAG channel will be created in the RAG "
                    "schema and its UUID will be saved to `control.channel.rag_channel_id`."
                )
                link_channel_dropdown = gr.Dropdown(
                    label="Unlinked control channel",
                    choices=[],
                    allow_custom_value=False,
                    filterable=False,
                    interactive=True,
                    min_width=0,
                    elem_classes=["epsilon-selectbox"],
                )
                link_name_input = gr.Textbox(
                    label="RAG channel name (optional — defaults to control channel name)",
                    placeholder="Leave empty to reuse the control channel name",
                )
                link_description_input = gr.Textbox(
                    label="Description (optional)",
                    placeholder="Free-form description for the RAG channel",
                )
                link_btn = gr.Button("Create & link", variant="primary")
                link_status = gr.Markdown("")

            # Reports tab — admin only. Lists reports for a chosen channel and
            # provides a per-report delete control.
            with gr.Tab("Reports", visible=False) as reports_tab:
                gr.Markdown("## Uploaded reports")
                reports_channel_dropdown = gr.Dropdown(
                    label="Channel (linked channels only)",
                    choices=[],
                    allow_custom_value=False,
                    filterable=False,
                    interactive=True,
                    min_width=0,
                    elem_classes=["epsilon-selectbox"],
                )
                refresh_reports_btn = gr.Button("Load reports")
                reports_table = gr.Dataframe(
                    headers=["report_id", "filename", "title", "pages", "chunks", "created_at"],
                    datatype=["str", "str", "str", "number", "number", "str"],
                    interactive=False,
                    wrap=True,
                )

                gr.Markdown("---")
                gr.Markdown("### Delete a report")
                delete_report_dropdown = gr.Dropdown(
                    label="Report to delete",
                    choices=[],
                    allow_custom_value=False,
                    filterable=False,
                    interactive=True,
                    min_width=0,
                    elem_classes=["epsilon-selectbox"],
                )
                delete_report_btn = gr.Button("Delete report", variant="stop")
                delete_report_status = gr.Markdown("")

            # Ingest tab — admin only. Upload a PDF and run the full pipeline
            # against the chosen channel (must already be RAG-linked).
            with gr.Tab("Ingest PDF", visible=False) as ingest_tab:
                gr.Markdown("## Ingest a PDF into a channel")
                ingest_channel_dropdown = gr.Dropdown(
                    label="Channel (linked channels only)",
                    choices=[],
                    allow_custom_value=False,
                    filterable=False,
                    interactive=True,
                    min_width=0,
                    elem_classes=["epsilon-selectbox"],
                )
                pdf_upload = gr.File(
                    label="Upload PDF",
                    file_types=[".pdf"],
                    elem_classes=["epsilon-filebox"],
                )
                title_input = gr.Textbox(
                    label="Document title (optional)",
                    elem_classes=["epsilon-inputbox"],
                )
                ingest_btn = gr.Button(
                    "Ingest document",
                    variant="primary",
                    elem_classes=["epsilon-action-button"],
                )
                ingest_status = gr.Markdown("")

        logout_btn = gr.Button("Logout", variant="secondary")

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _refresh_dropdowns(channels: list[dict]):
        """Compute fresh values for the channels table and the three dropdowns
        that depend on it. Returned in the order the callers wire to outputs."""
        unlinked = _unlinked_choices(channels)
        linked = _linked_choices(channels)
        ingest = _ingest_choices(channels)
        return (
            _channels_table(channels),
            gr.update(choices=unlinked, value=_first_choice_value(unlinked)),
            gr.update(choices=linked, value=_first_choice_value(linked)),
            gr.update(choices=ingest, value=_first_choice_value(ingest)),
        )

    def handle_send(message: str, history: list, session: dict | None):
        if not message.strip():
            return history, ""
        if not session:
            history = history + [
                {"role": "user",      "content": message},
                {"role": "assistant", "content": "You are not logged in."},
            ]
            return history, ""

        history = history + [{"role": "user", "content": message}]

        try:
            result   = api_orchestrate(session["token"], "query", {"question": message})
            response = format_query_response(result)
        except Exception as e:
            response = _err_msg(e)

        history = history + [{"role": "assistant", "content": response}]
        return history, ""

    send_btn.click(
        fn=handle_send,
        inputs=[chat_input, chatbot, session_state],
        outputs=[chatbot, chat_input],
    )
    chat_input.submit(
        fn=handle_send,
        inputs=[chat_input, chatbot, session_state],
        outputs=[chatbot, chat_input],
    )

    def handle_login(username: str, password: str):
        """Authenticate and toggle visibility of the login/main screens and
        the admin tabs. Also preloads the channel list for admin sessions."""
        try:
            result = api_login(username, password)
        except Exception as e:
            return (
                None, [],
                gr.update(visible=True), gr.update(visible=False),
                gr.update(visible=False), gr.update(visible=False), gr.update(visible=False),
                "", _err_msg(e),
                [], gr.update(choices=[], value=None),
                gr.update(choices=[], value=None), gr.update(choices=[], value=None),
            )

        if not result["success"]:
            return (
                None, [],
                gr.update(visible=True), gr.update(visible=False),
                gr.update(visible=False), gr.update(visible=False), gr.update(visible=False),
                "", result["message"],
                [], gr.update(choices=[], value=None),
                gr.update(choices=[], value=None), gr.update(choices=[], value=None),
            )

        session = {
            "token":               result["token"],
            "name":                result["name"],
            "channel_name":        result["channel_name"],
            "authorized_features": result["authorized_features"],
        }
        admin = _is_admin(session)

        channels: list[dict] = []
        if admin:
            try:
                channels = api_admin_channels(session["token"])
            except Exception:
                channels = []

        table_rows, link_update, reports_update, ingest_update = _refresh_dropdowns(channels)

        return (
            session, channels,
            gr.update(visible=False), gr.update(visible=True),
            gr.update(visible=admin), gr.update(visible=admin), gr.update(visible=admin),
            f"Logged in as **{result['name']}** | Channel: **{result['channel_name']}**",
            result["message"],
            table_rows, link_update, reports_update, ingest_update,
        )

    login_btn.click(
        fn=handle_login,
        inputs=[username_input, password_input],
        outputs=[
            session_state, channels_state,
            login_screen, main_screen,
            channels_tab, reports_tab, ingest_tab,
            session_label, login_msg,
            channels_table, link_channel_dropdown,
            reports_channel_dropdown, ingest_channel_dropdown,
        ],
    )

    # ── Channels handlers ─────────────────────────────────────────────────────

    def handle_refresh_channels(session: dict | None):
        if not session:
            return [], [], gr.update(), gr.update(), gr.update()
        try:
            channels = api_admin_channels(session["token"])
        except Exception:
            return [], [], gr.update(), gr.update(), gr.update()

        table_rows, link_update, reports_update, ingest_update = _refresh_dropdowns(channels)
        return channels, table_rows, link_update, reports_update, ingest_update

    refresh_channels_btn.click(
        fn=handle_refresh_channels,
        inputs=[session_state],
        outputs=[
            channels_state, channels_table,
            link_channel_dropdown, reports_channel_dropdown, ingest_channel_dropdown,
        ],
    )

    def handle_add_channel(
        session: dict | None,
        name: str,
        description: str,
        features: list[str] | None,
    ):
        """Create a new control.channel and refresh the dropdowns so the new
        row is immediately available for RAG linking."""
        if not session:
            return (gr.update(), gr.update(), gr.update(), gr.update(), gr.update(),
                    "Not logged in.")
        if not name.strip():
            return (gr.update(), gr.update(), gr.update(), gr.update(), gr.update(),
                    "Please enter a channel name.")

        try:
            result = api_admin_create_channel(
                session["token"],
                name.strip(),
                description.strip(),
                features or [],
            )
        except Exception as e:
            return (gr.update(), gr.update(), gr.update(), gr.update(), gr.update(),
                    _err_msg(e))

        try:
            channels = api_admin_channels(session["token"])
        except Exception:
            channels = []

        table_rows, link_update, reports_update, ingest_update = _refresh_dropdowns(channels)
        msg = f"Created channel **{result['name']}** (channelid `{result['channelid']}`)."
        return channels, table_rows, link_update, reports_update, ingest_update, msg

    add_channel_btn.click(
        fn=handle_add_channel,
        inputs=[session_state, add_channel_name, add_channel_description, add_channel_features],
        outputs=[
            channels_state, channels_table,
            link_channel_dropdown, reports_channel_dropdown, ingest_channel_dropdown,
            add_channel_status,
        ],
    )

    def handle_create_link(
        session: dict | None,
        channelid,
        name: str,
        description: str,
    ):
        """Create a RAG channel and link it to the chosen control channel."""
        if not session:
            return ([], [], gr.update(), gr.update(), gr.update(), "Not logged in.")
        if channelid is None:
            return (
                gr.update(), gr.update(), gr.update(), gr.update(), gr.update(),
                "Please select an unlinked channel.",
            )

        try:
            result = api_admin_create_rag_channel(
                session["token"], int(channelid), name.strip(), description.strip(),
            )
        except Exception as e:
            return (
                gr.update(), gr.update(), gr.update(), gr.update(), gr.update(),
                _err_msg(e),
            )

        try:
            channels = api_admin_channels(session["token"])
        except Exception:
            channels = []

        table_rows, link_update, reports_update, ingest_update = _refresh_dropdowns(channels)
        msg = (
            f"Created and linked RAG channel **{result['name']}** "
            f"(`{result['rag_channel_id']}`) to control channel `{result['channelid']}`."
        )
        return channels, table_rows, link_update, reports_update, ingest_update, msg

    link_btn.click(
        fn=handle_create_link,
        inputs=[session_state, link_channel_dropdown, link_name_input, link_description_input],
        outputs=[
            channels_state, channels_table,
            link_channel_dropdown, reports_channel_dropdown, ingest_channel_dropdown,
            link_status,
        ],
    )

    # ── Reports handlers ──────────────────────────────────────────────────────

    def handle_refresh_reports(session: dict | None, channelid):
        if not session:
            return [], gr.update(choices=[], value=None), "Not logged in."
        if channelid is None:
            return [], gr.update(choices=[], value=None), "Please select a channel."
        try:
            reports = api_admin_list_reports(session["token"], int(channelid))
        except Exception as e:
            return [], gr.update(choices=[], value=None), _err_msg(e)
        delete_choices = _report_delete_choices(reports)
        return (
            _reports_table(reports),
            gr.update(choices=delete_choices, value=_first_choice_value(delete_choices)),
            f"Loaded {len(reports)} report(s).",
        )

    refresh_reports_btn.click(
        fn=handle_refresh_reports,
        inputs=[session_state, reports_channel_dropdown],
        outputs=[reports_table, delete_report_dropdown, delete_report_status],
    )

    def handle_delete_report(session: dict | None, channelid, report_id: str):
        """Delete a report and refresh the list for the same channel."""
        if not session:
            return [], gr.update(), "Not logged in."
        if not report_id:
            return gr.update(), gr.update(), "Please select a report to delete."
        try:
            result = api_admin_delete_report(session["token"], report_id)
        except Exception as e:
            return gr.update(), gr.update(), _err_msg(e)

        if channelid is None:
            return gr.update(), gr.update(choices=[], value=None), (
                f"Deleted report (removed {result.get('deleted_chunks', 0)} chunks)."
            )

        try:
            reports = api_admin_list_reports(session["token"], int(channelid))
        except Exception:
            reports = []

        delete_choices = _report_delete_choices(reports)
        return (
            _reports_table(reports),
            gr.update(choices=delete_choices, value=_first_choice_value(delete_choices)),
            f"Deleted report (removed {result.get('deleted_chunks', 0)} chunks).",
        )

    delete_report_btn.click(
        fn=handle_delete_report,
        inputs=[session_state, reports_channel_dropdown, delete_report_dropdown],
        outputs=[reports_table, delete_report_dropdown, delete_report_status],
    )

    # ── Ingest handler ────────────────────────────────────────────────────────

    def handle_ingest(file, rag_channel_id: str, title: str, session: dict | None):
        """Upload the PDF to the backend, then trigger the orchestrator's
        ingest action against the chosen RAG channel."""
        if not session:
            return "Not logged in."
        if not rag_channel_id:
            return "Please select a channel."
        if file is None:
            return "Please upload a PDF file."

        file_path = file.name if hasattr(file, "name") else str(file)
        filename  = os.path.basename(file_path)

        try:
            upload_result = api_upload(session["token"], file_path, filename)
        except Exception as e:
            return _err_msg(e)

        try:
            result = api_orchestrate(
                session["token"],
                "ingest",
                {
                    "rag_channel_id": rag_channel_id,
                    "file_path":      upload_result["file_path"],
                    "filename":       upload_result["filename"],
                    "title":          (title or "").strip(),
                },
            )
        except Exception as e:
            return _err_msg(e)

        return format_ingest_response(result)

    ingest_btn.click(
        fn=handle_ingest,
        inputs=[pdf_upload, ingest_channel_dropdown, title_input, session_state],
        outputs=[ingest_status],
    )

    # ── Logout handler ────────────────────────────────────────────────────────

    def handle_logout(session: dict | None):
        """Clear the session and return the UI to the login screen."""
        if session and session.get("token"):
            api_logout(session["token"])
        return (
            None, [],
            gr.update(visible=True), gr.update(visible=False),
            gr.update(visible=False), gr.update(visible=False), gr.update(visible=False),
            "", "",
            "", "",
            [],
            [],
            gr.update(choices=[], value=None),
            gr.update(choices=[], value=None),
            gr.update(choices=[], value=None),
            gr.update(choices=[], value=None),
            "",
            "",
        )

    logout_btn.click(
        fn=handle_logout,
        inputs=[session_state],
        outputs=[
            session_state, channels_state,
            login_screen, main_screen,
            channels_tab, reports_tab, ingest_tab,
            session_label, login_msg,
            username_input, password_input,
            chatbot,
            channels_table,
            link_channel_dropdown, reports_channel_dropdown,
            ingest_channel_dropdown, delete_report_dropdown,
            link_status, delete_report_status,
        ],
    )


# ── Launch ────────────────────────────────────────────────────────────────────
# Two access modes for Lightning AI users:
#   * GRADIO_SHARE=true → app.launch(share=True) opens an https://*.gradio.live
#     public tunnel and prints the URL in the logs.
#   * Otherwise → mount Gradio inside a small FastAPI app that strips the
#     X-Frame-Options header so Lightning AI's iframe wrapper for port 7860
#     can display the UI directly.

if os.getenv("GRADIO_SHARE", "false").lower() == "true":
    app.launch(server_name="0.0.0.0", server_port=7860, share=True)
else:
    from fastapi import FastAPI
    from starlette.middleware.base import BaseHTTPMiddleware
    import uvicorn

    class _AllowIframe(BaseHTTPMiddleware):
        """Remove anti-iframe response headers so Lightning AI's wrapper page
        can embed the UI in its own iframe view."""
        async def dispatch(self, request, call_next):
            response = await call_next(request)
            if "X-Frame-Options" in response.headers:
                del response.headers["X-Frame-Options"]
            if "x-frame-options" in response.headers:
                del response.headers["x-frame-options"]
            response.headers["Content-Security-Policy"] = "frame-ancestors *"
            return response

    app.queue()
    _main = FastAPI()
    _main.add_middleware(_AllowIframe)
    gr.mount_gradio_app(_main, app, path="/")

    uvicorn.run(_main, host="0.0.0.0", port=7860, log_level="info")
