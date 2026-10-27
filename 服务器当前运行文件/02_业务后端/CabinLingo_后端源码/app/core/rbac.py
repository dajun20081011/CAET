from dataclasses import dataclass, field

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .auth_repository import AuthRepository
from .config import settings
from .security import TokenError, decode_access_token


@dataclass(frozen=True)
class ProductMembership:
    product_code: str
    roles: frozenset[str] = field(default_factory=frozenset)
    permissions: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class Principal:
    user_id: str
    memberships: tuple[ProductMembership, ...]
    display_name: str = ""

    def has_permission(self, product_code: str, permission: str) -> bool:
        return any(m.product_code == product_code and permission in m.permissions for m in self.memberships)

    def has_role(self, product_code: str, role: str) -> bool:
        return any(m.product_code == product_code and role in m.roles for m in self.memberships)


bearer = HTTPBearer(auto_error=False)


def _repository() -> AuthRepository:
    return AuthRepository(settings.database_url)


async def get_principal(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Principal:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required")
    try:
        claims = decode_access_token(
            credentials.credentials, secret=settings.jwt_secret,
            issuer=settings.jwt_issuer, audience=settings.jwt_audience,
        )
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token") from exc
    identity = _repository().get_identity(claims["sub"])
    if not identity or not identity["is_active"] or identity["token_version"] != claims["ver"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Access token revoked")
    memberships = tuple(
        ProductMembership(code, frozenset(item["roles"]), frozenset(item["permissions"]))
        for code, item in identity["memberships"].items()
    )
    return Principal(identity["id"], memberships, identity["display_name"])


def require_permission(product_code: str, permission: str):
    async def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        assert_permission(principal, product_code, permission)
        return principal
    return dependency


def assert_permission(principal: Principal, product_code: str, permission: str) -> None:
    if not principal.has_permission(product_code, permission):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
