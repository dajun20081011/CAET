"""Password hashing and HS256 JWT primitives.

JWTs contain identity/version only. Roles and permissions are loaded from the
database for every request, so client claims cannot elevate privileges.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any


PASSWORD_ITERATIONS = 600_000


class TokenError(ValueError):
    pass


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str, *, iterations: int = PASSWORD_ITERATIONS, salt: bytes | None = None) -> str:
    if len(password) < 10:
        raise ValueError("password must contain at least 10 characters")
    actual_salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), actual_salt, iterations)
    return f"pbkdf2_sha256${iterations}${_b64url(actual_salt)}${_b64url(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), _b64url_decode(salt), int(iterations))
        return hmac.compare_digest(actual, _b64url_decode(expected))
    except (ValueError, TypeError):
        return False


def create_access_token(
    *, user_id: str, token_version: int, secret: str, issuer: str, audience: str, ttl_seconds: int
) -> str:
    if len(secret) < 32:
        raise ValueError("JWT secret must contain at least 32 characters")
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id, "ver": token_version, "iat": now, "exp": now + ttl_seconds,
        "iss": issuer, "aud": audience, "jti": _b64url(os.urandom(16)),
    }
    signing_input = ".".join(
        _b64url(json.dumps(part, separators=(",", ":"), sort_keys=True).encode())
        for part in (header, payload)
    )
    signature = hmac.new(secret.encode(), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url(signature)}"


def decode_access_token(token: str, *, secret: str, issuer: str, audience: str) -> dict[str, Any]:
    try:
        encoded_header, encoded_payload, encoded_signature = token.split(".")
        signing_input = f"{encoded_header}.{encoded_payload}"
        expected = hmac.new(secret.encode(), signing_input.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64url_decode(encoded_signature)):
            raise TokenError("invalid signature")
        header = json.loads(_b64url_decode(encoded_header))
        payload = json.loads(_b64url_decode(encoded_payload))
        if header != {"alg": "HS256", "typ": "JWT"}:
            raise TokenError("unsupported token header")
        if payload.get("iss") != issuer or payload.get("aud") != audience:
            raise TokenError("invalid issuer or audience")
        if int(payload.get("exp", 0)) <= int(time.time()):
            raise TokenError("token expired")
        if not payload.get("sub") or not isinstance(payload.get("ver"), int):
            raise TokenError("invalid token claims")
        return payload
    except TokenError:
        raise
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise TokenError("malformed token") from exc
