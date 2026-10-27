from __future__ import annotations

from dataclasses import dataclass
import json
import socket
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class HTTPClientError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class HTTPResponse:
    body: bytes
    headers: dict[str, str]
    attempts: int
    latency_ms: int

    def json(self) -> dict[str, Any]:
        try:
            value = json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HTTPClientError("invalid_json_response") from exc
        if not isinstance(value, dict):
            raise HTTPClientError("invalid_json_shape")
        return value


class HTTPClient:
    """Dependency-free HTTP client with bounded retries and response size."""

    def __init__(self, *, timeout_seconds: float = 15, max_retries: int = 1,
                 backoff_seconds: float = 0.25, max_response_bytes: int = 2 * 1024 * 1024,
                 opener: Callable[..., Any] = urlopen, sleeper: Callable[[float], None] = time.sleep) -> None:
        self.timeout_seconds = max(0.1, timeout_seconds)
        self.max_retries = max(0, max_retries)
        self.backoff_seconds = max(0, backoff_seconds)
        self.max_response_bytes = max(1024, max_response_bytes)
        self.opener = opener
        self.sleeper = sleeper

    def request(self, method: str, url: str, *, body: bytes | None = None,
                headers: dict[str, str] | None = None) -> HTTPResponse:
        started = time.monotonic()
        last_error: HTTPClientError | None = None
        total_attempts = self.max_retries + 1
        for attempt in range(1, total_attempts + 1):
            request = Request(url, data=body, headers=headers or {}, method=method.upper())
            try:
                with self.opener(request, timeout=self.timeout_seconds) as response:
                    data = response.read(self.max_response_bytes + 1)
                    if len(data) > self.max_response_bytes:
                        raise HTTPClientError("response_too_large")
                    response_headers = {str(k).lower(): str(v) for k, v in response.headers.items()}
                    return HTTPResponse(data, response_headers, attempt, round((time.monotonic() - started) * 1000))
            except HTTPClientError:
                raise
            except HTTPError as exc:
                retryable = exc.code == 429 or 500 <= exc.code <= 599
                last_error = HTTPClientError(f"http_{exc.code}", retryable=retryable)
            except (URLError, TimeoutError, socket.timeout, ConnectionError):
                last_error = HTTPClientError("network_timeout_or_unavailable", retryable=True)
            if not last_error.retryable or attempt >= total_attempts:
                raise last_error
            self.sleeper(self.backoff_seconds * (2 ** (attempt - 1)))
        raise last_error or HTTPClientError("request_failed")

    def request_json(self, method: str, url: str, *, payload: dict[str, Any],
                     headers: dict[str, str] | None = None) -> tuple[dict[str, Any], HTTPResponse]:
        request_headers = {"Content-Type": "application/json", "Accept": "application/json", **(headers or {})}
        response = self.request(method, url, body=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=request_headers)
        return response.json(), response

