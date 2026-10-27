from dataclasses import dataclass
import mimetypes
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from .ai_gateway import AudioBlob
from .http_client import HTTPClient, HTTPClientError


class ObjectStorageError(RuntimeError):
    pass


class ObjectStorageAdapter(Protocol):
    provider: str

    def save(self, object_key: str, data: bytes, content_type: str) -> str: ...
    def read(self, audio_ref: str) -> AudioBlob: ...
    def delete(self, audio_ref: str) -> None: ...


def _safe_key(value: str) -> str:
    key = PurePosixPath(value)
    if key.is_absolute() or ".." in key.parts or not key.parts:
        raise ObjectStorageError("invalid_object_key")
    return key.as_posix()


@dataclass
class LocalObjectStorage:
    root: str
    provider: str = "local"

    def _path(self, key: str) -> Path:
        base = Path(self.root).resolve()
        path = (base / _safe_key(key)).resolve()
        if base not in path.parents:
            raise ObjectStorageError("invalid_object_path")
        return path

    def save(self, object_key: str, data: bytes, content_type: str) -> str:
        path = self._path(object_key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + ".uploading")
            temporary.write_bytes(data)
            temporary.replace(path)
        except OSError as exc:
            raise ObjectStorageError("storage_write_failed") from exc
        return "/media/" + _safe_key(object_key)

    def read(self, audio_ref: str) -> AudioBlob:
        if not audio_ref.startswith("/media/"):
            raise ObjectStorageError("unsupported_audio_reference")
        path = self._path(audio_ref.removeprefix("/media/"))
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise ObjectStorageError("storage_read_failed") from exc
        return AudioBlob(data, mimetypes.guess_type(path.name)[0] or "application/octet-stream", path.name)

    def local_path(self, audio_ref: str) -> Path:
        """Return a validated path for zero-copy/range-aware local delivery."""
        if not audio_ref.startswith("/media/"):
            raise ObjectStorageError("unsupported_audio_reference")
        path = self._path(audio_ref.removeprefix("/media/"))
        if not path.is_file():
            raise ObjectStorageError("storage_read_failed")
        return path

    def delete(self, audio_ref: str) -> None:
        if audio_ref.startswith("/media/"):
            self._path(audio_ref.removeprefix("/media/")).unlink(missing_ok=True)


@dataclass
class PresignedHTTPObjectStorage:
    """Provider-neutral OSS adapter backed by a trusted presign/broker endpoint."""

    endpoint: str
    bucket: str
    api_key: str
    client: HTTPClient
    provider: str = "presigned_http"

    def _presign(self, operation: str, object_key: str, content_type: str | None = None) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            data, _ = self.client.request_json("POST", self.endpoint, payload={
                "operation": operation, "bucket": self.bucket,
                "object_key": _safe_key(object_key), "content_type": content_type,
            }, headers=headers)
        except HTTPClientError as exc:
            raise ObjectStorageError(f"presign_{exc.code}") from exc
        nested = data.get("data")
        return nested if isinstance(nested, dict) else data

    def save(self, object_key: str, data: bytes, content_type: str) -> str:
        signed = self._presign("put", object_key, content_type)
        upload_url = signed.get("upload_url") or signed.get("url")
        if not isinstance(upload_url, str):
            raise ObjectStorageError("missing_upload_url")
        headers = {str(k): str(v) for k, v in (signed.get("headers") or {}).items()}
        headers.setdefault("Content-Type", content_type)
        try:
            self.client.request("PUT", upload_url, body=data, headers=headers)
        except HTTPClientError as exc:
            raise ObjectStorageError(f"upload_{exc.code}") from exc
        return str(signed.get("audio_ref") or f"oss://{self.bucket}/{_safe_key(object_key)}")

    def read(self, audio_ref: str) -> AudioBlob:
        prefix = f"oss://{self.bucket}/"
        if not audio_ref.startswith(prefix):
            raise ObjectStorageError("unsupported_audio_reference")
        key = audio_ref.removeprefix(prefix)
        signed = self._presign("get", key)
        download_url = signed.get("download_url") or signed.get("url")
        if not isinstance(download_url, str):
            raise ObjectStorageError("missing_download_url")
        try:
            response = self.client.request("GET", download_url, headers={str(k): str(v) for k, v in (signed.get("headers") or {}).items()})
        except HTTPClientError as exc:
            raise ObjectStorageError(f"download_{exc.code}") from exc
        return AudioBlob(response.body, response.headers.get("content-type", "application/octet-stream"), PurePosixPath(key).name)

    def delete(self, audio_ref: str) -> None:
        prefix = f"oss://{self.bucket}/"
        if not audio_ref.startswith(prefix):
            return
        signed = self._presign("delete", audio_ref.removeprefix(prefix))
        delete_url = signed.get("delete_url") or signed.get("url")
        if isinstance(delete_url, str):
            try:
                self.client.request("DELETE", delete_url, headers={str(k): str(v) for k, v in (signed.get("headers") or {}).items()})
            except HTTPClientError:
                return


def build_object_storage(settings: Any) -> ObjectStorageAdapter:
    if settings.object_storage_mode == "presigned_http":
        return PresignedHTTPObjectStorage(
            settings.object_storage_endpoint, settings.object_storage_bucket,
            settings.object_storage_api_key,
            HTTPClient(timeout_seconds=settings.object_storage_timeout_seconds,
                       max_retries=settings.object_storage_max_retries,
                       max_response_bytes=settings.audio_max_bytes),
        )
    return LocalObjectStorage(settings.upload_dir)
