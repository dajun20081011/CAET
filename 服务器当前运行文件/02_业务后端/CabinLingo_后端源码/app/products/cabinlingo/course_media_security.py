"""Short-lived, file-scoped grants for native browser media streaming."""

from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from hashlib import sha256
import hmac
import json
import logging
import time
from typing import Any


class CourseMediaTokenError(ValueError):
    pass


class CourseMediaAccessLogFilter(logging.Filter):
    """Keep signed playback URLs out of Uvicorn access logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "/course-v23-media-stream/" not in record.getMessage()


def _b64(data: bytes) -> str:
    return urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return urlsafe_b64decode(value + "=" * (-len(value) % 4))


class CourseMediaSigner:
    def __init__(self, secret: str, ttl_seconds: int = 3600) -> None:
        if not secret:
            raise ValueError("JWT secret is required")
        self.secret = secret.encode("utf-8")
        self.ttl_seconds = ttl_seconds

    def issue(self, file_id: str, subject: str) -> str:
        payload = {
            "file_id": file_id,
            "sub": subject,
            "scope": "course_media_playback",
            "exp": int(time.time()) + self.ttl_seconds,
        }
        encoded = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        signature = _b64(hmac.new(self.secret, encoded.encode("ascii"), sha256).digest())
        return f"{encoded}.{signature}"

    def verify(self, token: str, file_id: str) -> dict[str, Any]:
        try:
            if len(token) > 2048:
                raise CourseMediaTokenError("invalid token")
            encoded, signature = token.split(".", 1)
            expected = _b64(hmac.new(self.secret, encoded.encode("ascii"), sha256).digest())
            if not hmac.compare_digest(signature, expected):
                raise CourseMediaTokenError("invalid token")
            payload = json.loads(_unb64(encoded).decode("utf-8"))
            if (
                not isinstance(payload, dict)
                or int(payload.get("exp", 0)) <= int(time.time())
                or payload.get("scope") != "course_media_playback"
                or payload.get("file_id") != file_id
                or not isinstance(payload.get("sub"), str)
            ):
                raise CourseMediaTokenError("invalid or expired token")
            return payload
        except CourseMediaTokenError:
            raise
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise CourseMediaTokenError("invalid token") from exc
