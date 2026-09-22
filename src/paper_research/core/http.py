"""Shared request delays and bounded retries."""

import time
from email.utils import parsedate_to_datetime

import httpx

USER_AGENT = "paper-research-agent/0.1"
REQUEST_DELAYS = {"arxiv": 4, "semantic_scholar": 1}


class ProviderError(RuntimeError):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def retry_delay(value, attempt):
    try:
        return max(0, float(value))
    except (ValueError, TypeError):
        try:
            return max(0, parsedate_to_datetime(value).timestamp() - time.time())
        except (ValueError, TypeError, OverflowError):
            return 2**attempt


def request(provider, method, url, *, timeout=30, max_bytes=50_000_000, **kwargs):
    headers = {"User-Agent": USER_AGENT, **kwargs.pop("headers", {})}
    request_delay = REQUEST_DELAYS.get(provider, 0)
    for attempt in range(3):
        if request_delay:
            time.sleep(request_delay)
        try:
            with (
                httpx.Client(timeout=timeout, follow_redirects=True) as client,
                client.stream(method, url, headers=headers, **kwargs) as response,
            ):
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
        endpoint = str(httpx.URL(url).copy_with(query=None, fragment=None))
        message = f"{provider}: HTTP {result.status_code} from {endpoint}"
        if transient:
            message += f"; retry later (server/backoff delay: {delay:g}s)"
        if result.status_code in (401, 403):
            message += "; check provider credentials and access"
        body_excerpt = " ".join(result.text.split())
        if body_excerpt:
            if len(body_excerpt) > 300:
                body_excerpt = body_excerpt[:297] + "..."
            message += f"; response: {body_excerpt}"
        raise ProviderError(message, result.status_code)


def request_json(provider, method, url, **kwargs):
    try:
        data = request(provider, method, url, **kwargs).json()
    except ValueError as exc:
        raise ProviderError(f"{provider}: invalid JSON response") from exc
    if not isinstance(data, dict):
        raise ProviderError(f"{provider}: JSON response is not an object")
    return data
