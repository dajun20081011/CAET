"""Short-lived viewer grants for sandboxed Learning Card resources."""

from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from hashlib import sha256
import hmac
import json
import logging
import time
from typing import Any


class LearningCardTokenError(ValueError):
    pass


class LearningCardAccessLogFilter(logging.Filter):
    """Do not put bearer viewer URLs in Uvicorn's access log."""
    def filter(self, record: logging.LogRecord) -> bool:
        return '/learning-card-view/' not in record.getMessage()


def _b64(data: bytes) -> str:
    return urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return urlsafe_b64decode(value + "=" * (-len(value) % 4))


class LearningCardViewerSigner:
    def __init__(self, secret: str, ttl_seconds: int = 600) -> None:
        if not secret:
            raise ValueError("JWT secret is required")
        self.secret = secret.encode("utf-8")
        self.ttl_seconds = ttl_seconds

    def issue(self, card_id: str, subject: str, scope: str, *, content_id: str | None = None, assignment_id: str | None = None) -> str:
        payload = {
            "card_id": card_id, "sub": subject, "scope": scope,
            "exp": int(time.time()) + self.ttl_seconds,
            "content_id": content_id, "assignment_id": assignment_id,
        }
        encoded = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        signature = _b64(hmac.new(self.secret, encoded.encode("ascii"), sha256).digest())
        return f"{encoded}.{signature}"

    def verify(self, token: str) -> dict[str, Any]:
        try:
            if len(token) > 2048:
                raise LearningCardTokenError('invalid token')
            encoded, signature = token.split(".", 1)
            expected = _b64(hmac.new(self.secret, encoded.encode("ascii"), sha256).digest())
            if not hmac.compare_digest(signature, expected):
                raise LearningCardTokenError("invalid token")
            payload = json.loads(_unb64(encoded).decode("utf-8"))
            if not isinstance(payload, dict) or int(payload.get("exp", 0)) <= int(time.time()):
                raise LearningCardTokenError("expired token")
            if not isinstance(payload.get("card_id"), str) or payload.get("scope") not in {"admin_preview", "learner_view", "learner_catalog"}:
                raise LearningCardTokenError("invalid token")
            return payload
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            if isinstance(exc, LearningCardTokenError):
                raise
            raise LearningCardTokenError("invalid token") from exc
