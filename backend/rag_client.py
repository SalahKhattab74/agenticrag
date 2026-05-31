"""Small HTTP client for calls from backend to rag_service."""
import logging
import os
import time
from typing import Any

import requests

RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://rag_service:8001").rstrip("/")
DEFAULT_TIMEOUT = 30
DEFAULT_RETRIES = 3
RETRY_SLEEP_SECONDS = 2

logger = logging.getLogger(__name__)


def call_rag_service(
    method: str,
    path: str,
    *,
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    **kwargs: Any,
) -> requests.Response:
    """Call rag_service with a short retry window for startup/warmup races."""
    url = f"{RAG_SERVICE_URL}/{path.lstrip('/')}"
    last_exc: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            resp = requests.request(method, url, timeout=timeout, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.HTTPError:
            raise
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            logger.warning(
                "rag_service call failed (%s %s), attempt %s/%s: %s",
                method.upper(),
                path,
                attempt,
                retries,
                exc,
            )
            if attempt < retries:
                time.sleep(RETRY_SLEEP_SECONDS)

    raise RuntimeError(
        f"RAG service is not reachable at {RAG_SERVICE_URL}. "
        "Start/restart the rag_service container and wait until /health is OK. "
        f"Last error: {last_exc}"
    )
