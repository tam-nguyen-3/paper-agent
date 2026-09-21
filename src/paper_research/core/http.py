"""Shared process-wide pacing and bounded retries."""

import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx


class ProviderError(RuntimeError):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


class Limiter:
    def __init__(self, interval):
        self.interval = interval
        self.lock = threading.Lock()
        self.last = None

    def wait(self):
        if self.last is not None:
            time.sleep(max(0, self.interval - (time.monotonic() - self.last)))
        self.last = time.monotonic()


LIMITERS = {
    name: Limiter(interval)
    for name, interval in (("arxiv", 3), ("semantic_scholar", 1), ("tavily", 0))
}


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def retry_delay(value, attempt):
    try:
        return max(0, float(value))
    except (ValueError, TypeError):
        try:
            return max(0, parsedate_to_datetime(value).timestamp() - time.time())
        except (ValueError, TypeError, OverflowError):
            return 2**attempt


def request(provider, method, url, *, timeout=30, max_bytes=50_000_000, **kwargs):
    limiter = LIMITERS[provider]
    headers = {"User-Agent": "local-arxiv-research/0.1", **kwargs.pop("headers", {})}
    if provider == "arxiv":
        # Some arXiv responses reject httpx's negotiated encodings with HTTP 406.
        headers["Accept-Encoding"] = "identity"
    for attempt in range(3):
        try:
            # Hold the provider lock through the request: concurrent tools share pacing.
            with limiter.lock:
                limiter.wait()
                with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                    with client.stream(
                        method, url, headers=headers, **kwargs
                    ) as response:
                        chunks, size = [], 0
                        for chunk in response.iter_bytes():
                            size += len(chunk)
                            if size > max_bytes:
                                raise ProviderError(
                                    f"{provider}: response exceeds {max_bytes} bytes"
                                )
                            chunks.append(chunk)
                        result = httpx.Response(
                            response.status_code,
                            headers=response.headers,
                            content=b"".join(chunks),
                        )
        except httpx.TransportError as exc:
            if attempt == 2:
                raise ProviderError(
                    f"{provider}: connection failed after 3 attempts"
                ) from exc
            time.sleep(2**attempt)
            continue
        if result.status_code < 400:
            return result
        transient = result.status_code == 429 or result.status_code >= 500
        delay = retry_delay(result.headers.get("Retry-After"), attempt)
        if transient and attempt < 2 and delay <= 30:
            time.sleep(delay)
            continue
        message = f"{provider}: HTTP {result.status_code}"
        if transient:
            message += f"; retry later (server/backoff delay: {delay:g}s)"
        if result.status_code in (401, 403):
            message += "; check provider credentials and access"
        raise ProviderError(message, result.status_code)


def request_json(provider, method, url, **kwargs):
    try:
        data = request(provider, method, url, **kwargs).json()
        if not isinstance(data, dict):
            raise ValueError("expected an object")
        return data
    except ValueError as exc:
        raise ProviderError(f"{provider}: invalid JSON response") from exc
