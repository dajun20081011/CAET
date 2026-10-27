from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from ...core.rbac import Principal, assert_permission, get_principal
from .broadcast_repository import build_broadcast_repository
from .broadcast_schemas import (
    BroadcastScriptCreate,
    BroadcastScriptDetail,
    BroadcastScriptItem,
    BroadcastScriptPage,
    BroadcastScriptUpdate,
    BroadcastSliceCreate,
    BroadcastSliceOut,
    BroadcastSliceUpdate,
    BroadcastVersionCreate,
    BroadcastVersionOut,
    FullTextUpdate,
    FullTextUpdateResult,
    SliceGenerateRequest,
    SliceOrderRequest,
)
from .broadcast_service import BroadcastLibraryError


router = APIRouter(prefix="/api/v1/cabinlingo/admin", tags=["CabinLingo Broadcast Library"])
broadcast_repository = build_broadcast_repository()


def require_broadcast_admin(principal: Principal = Depends(get_principal)) -> Principal:
    assert_permission(principal, "cabinlingo", "cabinlingo:admin")
    return principal


def _http_error(exc: BroadcastLibraryError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get("/broadcast-scripts", response_model=BroadcastScriptPage)
async def list_broadcast_scripts(
    keyword: str | None = Query(default=None, max_length=160),
    language: str | None = Query(default=None, max_length=20),
    script_type: str | None = Query(default=None, max_length=60),
    company_id: UUID | None = None,
    frozen: bool | None = None,
    enabled: bool | None = None,
    archived: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: Principal = Depends(require_broadcast_admin),
):
    return broadcast_repository.list_scripts(
        keyword=keyword, language=language, script_type=script_type,
        company_id=str(company_id) if company_id else None, frozen=frozen,
        enabled=enabled, archived=archived, page=page, page_size=page_size,
    )


@router.post("/broadcast-scripts", response_model=BroadcastScriptItem, status_code=201)
async def create_broadcast_script(data: BroadcastScriptCreate, principal: Principal = Depends(require_broadcast_admin)):
    try:
        return broadcast_repository.create_script(data.model_dump(), principal.user_id)
    except BroadcastLibraryError as exc:
        raise _http_error(exc) from exc


@router.get("/broadcast-scripts/{script_id}", response_model=BroadcastScriptDetail)
async def get_broadcast_script(script_id: UUID, _: Principal = Depends(require_broadcast_admin)):
    try:
        return broadcast_repository.get_script(str(script_id))
    except BroadcastLibraryError as exc:
        raise _http_error(exc) from exc


@router.patch("/broadcast-scripts/{script_id}", response_model=BroadcastScriptDetail)
async def update_broadcast_script(script_id: UUID, data: BroadcastScriptUpdate, _: Principal = Depends(require_broadcast_admin)):
    try:
        return broadcast_repository.update_script(str(script_id), data.model_dump(exclude_unset=True))
    except BroadcastLibraryError as exc:
        raise _http_error(exc) from exc


@router.delete("/broadcast-scripts/{script_id}", response_model=BroadcastScriptDetail)
async def archive_broadcast_script(script_id: UUID, _: Principal = Depends(require_broadcast_admin)):
    try:
        return broadcast_repository.archive_script(str(script_id))
    except BroadcastLibraryError as exc:
        raise _http_error(exc) from exc


@router.get("/broadcast-scripts/{script_id}/versions", response_model=list[BroadcastVersionOut])
async def list_broadcast_versions(script_id: UUID, _: Principal = Depends(require_broadcast_admin)):
    try:
        return broadcast_repository.list_versions(str(script_id))
    except BroadcastLibraryError as exc:
        raise _http_error(exc) from exc


@router.post("/broadcast-scripts/{script_id}/versions", response_model=BroadcastVersionOut, status_code=201)
async def create_broadcast_version(script_id: UUID, data: BroadcastVersionCreate, principal: Principal = Depends(require_broadcast_admin)):
    try:
        return broadcast_repository.create_version(str(script_id), data.full_text, principal.user_id)
    except BroadcastLibraryError as exc:
        raise _http_error(exc) from exc


@router.get("/broadcast-script-versions/{version_id}", response_model=BroadcastVersionOut)
async def get_broadcast_version(version_id: UUID, _: Principal = Depends(require_broadcast_admin)):
    try:
        return broadcast_repository.get_version(str(version_id))
    except BroadcastLibraryError as exc:
        raise _http_error(exc) from exc


@router.put("/broadcast-script-versions/{version_id}/full-text", response_model=FullTextUpdateResult)
async def update_broadcast_full_text(version_id: UUID, data: FullTextUpdate, _: Principal = Depends(require_broadcast_admin)):
    try:
        return broadcast_repository.update_full_text(str(version_id), data.full_text)
    except BroadcastLibraryError as exc:
        raise _http_error(exc) from exc


@router.post("/broadcast-script-versions/{version_id}/freeze", response_model=BroadcastVersionOut)
async def freeze_broadcast_version(version_id: UUID, _: Principal = Depends(require_broadcast_admin)):
    try:
        return broadcast_repository.freeze_version(str(version_id))
    except BroadcastLibraryError as exc:
        raise _http_error(exc) from exc


@router.get("/broadcast-script-versions/{version_id}/slices", response_model=list[BroadcastSliceOut])
async def list_broadcast_slices(version_id: UUID, _: Principal = Depends(require_broadcast_admin)):
    try:
        return broadcast_repository.list_slices(str(version_id))
    except BroadcastLibraryError as exc:
        raise _http_error(exc) from exc


@router.post("/broadcast-script-versions/{version_id}/slices", response_model=BroadcastSliceOut, status_code=201)
async def create_broadcast_slice(version_id: UUID, data: BroadcastSliceCreate, _: Principal = Depends(require_broadcast_admin)):
    try:
        return broadcast_repository.create_slice(str(version_id), data.text, data.position, data.verified)
    except BroadcastLibraryError as exc:
        raise _http_error(exc) from exc


@router.post("/broadcast-script-versions/{version_id}/slices/generate", response_model=list[BroadcastSliceOut])
async def generate_broadcast_slices(version_id: UUID, data: SliceGenerateRequest, _: Principal = Depends(require_broadcast_admin)):
    try:
        return broadcast_repository.generate_slices(str(version_id), data.max_chars)
    except BroadcastLibraryError as exc:
        raise _http_error(exc) from exc


@router.put("/broadcast-script-versions/{version_id}/slices/order", response_model=list[BroadcastSliceOut])
async def order_broadcast_slices(version_id: UUID, data: SliceOrderRequest, _: Principal = Depends(require_broadcast_admin)):
    try:
        return broadcast_repository.reorder_slices(str(version_id), data.slice_ids)
    except BroadcastLibraryError as exc:
        raise _http_error(exc) from exc


@router.put("/broadcast-slices/{slice_id}", response_model=BroadcastSliceOut)
async def update_broadcast_slice(slice_id: UUID, data: BroadcastSliceUpdate, _: Principal = Depends(require_broadcast_admin)):
    try:
        return broadcast_repository.update_slice(str(slice_id), data.model_dump(exclude_unset=True))
    except BroadcastLibraryError as exc:
        raise _http_error(exc) from exc


@router.delete("/broadcast-slices/{slice_id}", response_model=BroadcastSliceOut)
async def delete_broadcast_slice(slice_id: UUID, _: Principal = Depends(require_broadcast_admin)):
    try:
        return broadcast_repository.delete_slice(str(slice_id))
    except BroadcastLibraryError as exc:
        raise _http_error(exc) from exc
