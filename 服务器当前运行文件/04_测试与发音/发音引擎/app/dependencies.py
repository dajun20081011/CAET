import secrets
from typing import Annotated

from fastapi import Header, HTTPException, Request, status

from app.services.engine import PronunciationEngine


def get_engine(request: Request) -> PronunciationEngine:
    return request.app.state.engine


def verify_api_key(
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
) -> None:
    expected = request.app.state.settings.api_key
    if expected and (not x_api_key or not secrets.compare_digest(x_api_key, expected)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
