"""Azure Document Intelligence OCR — Arabic + English text recognition via cloud API.

OCR runs only on regions where Docling's text-layer extraction came
back empty (or suspiciously short). Two reasons:
    1. Network I/O adds latency (~500-2000 ms per region).
    2. Native PDF text is always more accurate than OCR'd text — never
       overwrite real text with an OCR guess.

Uses the Azure AI Document Intelligence SDK (azure-ai-documentintelligence ≥ 1.0.0)
with the prebuilt-read model, which supports Arabic + Latin scripts natively.
Credentials are read from settings.azure_ocr_endpoint / settings.azure_ocr_key
(env vars AZURE_OCR_ENDPOINT / AZURE_OCR_KEY).

Public API
==========
`init()`, `is_ready()`, `ocr_image()`, `ocr_crop()` keep their
signatures so the orchestrator and warmup loop don't need to know
which engine is wired in.
"""
from __future__ import annotations

import io
import logging
import struct
import threading
import time

import numpy as np
from PIL import Image

from core.config import settings

logger = logging.getLogger(__name__)


# ── Module state ─────────────────────────────────────────────────────────────

_client = None          # type: ignore[var-annotated]
_init_attempted: bool = False
_lock = threading.Lock()


def init() -> None:
    """Build Azure DocumentIntelligenceClient from settings. Idempotent."""
    global _client, _init_attempted
    with _lock:
        if _init_attempted:
            return
        _init_attempted = True

        try:
            from azure.ai.documentintelligence import DocumentIntelligenceClient
            from azure.core.credentials import AzureKeyCredential
        except ImportError as exc:
            logger.exception("azure-ocr: azure-ai-documentintelligence not installed: %s", exc)
            return

        endpoint = settings.azure_ocr_endpoint.rstrip("/")
        key = settings.azure_ocr_key
        if not endpoint or not key:
            logger.error(
                "azure-ocr: AZURE_OCR_ENDPOINT and AZURE_OCR_KEY must be set — OCR disabled"
            )
            return

        try:
            _client = DocumentIntelligenceClient(
                endpoint=endpoint,
                credential=AzureKeyCredential(key),
            )
            logger.info("azure-ocr: Document Intelligence client ready (endpoint=%s)", endpoint)
        except Exception as exc:
            logger.exception("azure-ocr: failed to build client: %s", exc)


def is_ready() -> bool:
    return _client is not None


# ── Public API ───────────────────────────────────────────────────────────────

def ocr_image(img: bytes | np.ndarray | Image.Image) -> str:
    """Run OCR on an image and return concatenated text in reading order.

    Accepts bytes (any PIL-supported format), a numpy array (H×W×C),
    or a PIL Image. Returns "" on any failure — never raises, so the
    orchestrator's fallback path stays predictable.

    Confidence filter: lines whose average word confidence is below
    `settings.ocr_min_confidence` are dropped.
    """
    if not is_ready():
        return ""

    png_bytes = _to_png_bytes(img)
    if png_bytes is None:
        return ""

    img_w, img_h = _png_dims(png_bytes)
    logger.info("azure-ocr: recognizing image=%dx%d", img_w, img_h)

    started = time.perf_counter()
    try:
        from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
        poller = _client.begin_analyze_document(
            "prebuilt-read",
            AnalyzeDocumentRequest(bytes_source=png_bytes),
        )
        result = poller.result()
    except Exception as exc:
        logger.warning("azure-ocr: recognition failed (image=%dx%d): %s", img_w, img_h, exc)
        return ""

    elapsed_ms = int((time.perf_counter() - started) * 1000)

    if not result.pages:
        logger.info(
            "azure-ocr: no text detected (image=%dx%d, elapsed=%dms)",
            img_w, img_h, elapsed_ms,
        )
        return ""

    min_conf = settings.ocr_min_confidence
    kept: list[str] = []
    dropped_low_conf = 0

    for page in result.pages:
        # In SDK 1.0.x words are at page level, not line level.
        # Compute page-level average confidence once and apply to all lines.
        page_words = page.words or []
        avg_page_conf = (
            sum(w.confidence for w in page_words if w.confidence is not None) / len(page_words)
            if page_words else 1.0
        )
        if avg_page_conf < min_conf:
            dropped_low_conf += len(page.lines or [])
            continue
        for line in (page.lines or []):
            text = (line.content or "").strip()
            if text:
                kept.append(text)

    if not kept:
        logger.info(
            "azure-ocr: lines detected, all below conf=%.2f (image=%dx%d, elapsed=%dms)",
            min_conf, img_w, img_h, elapsed_ms,
        )
        return ""

    out = "\n".join(kept)
    preview = out.replace("\n", " ⏎ ")[:80]
    logger.info(
        "azure-ocr: ok — %d line(s) kept (%d dropped <%.2f conf), "
        "%d chars, %d ms — preview: %s",
        len(kept), dropped_low_conf, min_conf, len(out), elapsed_ms, preview,
    )
    return out


def ocr_crop(
    page_img: np.ndarray,
    bbox: tuple[float, float, float, float],
) -> str:
    """OCR a sub-region of a page image. Used to fill in text for layout
    regions where Docling didn't return any (scanned PDFs, image-only pages).
    """
    if page_img is None or page_img.size == 0:
        return ""

    page_h, page_w = page_img.shape[:2]
    raw = tuple(float(v) for v in bbox)
    x0, y0, x1, y1 = (int(round(v)) for v in raw)
    x0, x1 = max(0, x0), min(page_w, x1)
    y0, y1 = max(0, y0), min(page_h, y1)
    crop_w, crop_h = x1 - x0, y1 - y0
    logger.info(
        "azure-ocr: ocr_crop bbox=%s page=%dx%d → crop=%dx%d",
        raw, page_w, page_h, max(0, crop_w), max(0, crop_h),
    )

    if x1 <= x0 or y1 <= y0:
        logger.warning(
            "azure-ocr: ocr_crop bbox clamped to empty "
            "(raw=%s page=%dx%d) — upstream bbox / origin / unit mismatch?",
            raw, page_w, page_h,
        )
        return ""

    # Azure Document Intelligence requires a minimum of 50×50 px.
    # Smaller crops are decorations / thin rules — skip to save quota.
    if crop_w < 50 or crop_h < 50:
        logger.info(
            "azure-ocr: ocr_crop skipped — crop too small (%dx%d)", crop_w, crop_h
        )
        return ""

    crop = page_img[y0:y1, x0:x1]
    return ocr_image(crop)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _to_png_bytes(img: bytes | np.ndarray | Image.Image) -> bytes | None:
    """Convert accepted input types to PNG bytes for the Azure API."""
    try:
        if isinstance(img, (bytes, bytearray)):
            pil = Image.open(io.BytesIO(img)).convert("RGB")
        elif isinstance(img, np.ndarray):
            if img.ndim not in (2, 3):
                return None
            pil = Image.fromarray(img if img.ndim == 2 else img[..., :3])
        elif isinstance(img, Image.Image):
            pil = img.convert("RGB")
        else:
            return None
        buf = io.BytesIO()
        pil.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as exc:
        logger.warning("azure-ocr: image conversion failed: %s", exc)
        return None


def _png_dims(png_bytes: bytes) -> tuple[int, int]:
    """Read width and height from PNG IHDR without full decode."""
    try:
        w = struct.unpack(">I", png_bytes[16:20])[0]
        h = struct.unpack(">I", png_bytes[20:24])[0]
        return w, h
    except Exception:
        return 0, 0
