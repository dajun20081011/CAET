from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import quote
from urllib.request import urlopen
import json
import re


SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".m4v"}


class TencentCosError(RuntimeError):
    pass


class TencentCosNotConfigured(TencentCosError):
    pass


class TencentCosObjectMissing(TencentCosError):
    pass


class TencentCosUnsupportedVideo(TencentCosError):
    pass


@dataclass(frozen=True)
class TencentCosVideo:
    key: str
    filename: str
    size: int
    etag: str
    last_modified: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "filename": self.filename,
            "size": self.size,
            "etag": self.etag,
            "last_modified": self.last_modified,
        }


class TencentCosVideoService:
    def __init__(self, settings: Any, client: Any | None = None):
        self.settings = settings
        self.prefix = str(settings.tencent_cos_prefix or "").strip().lstrip("/")
        if self.prefix and not self.prefix.endswith("/"):
            self.prefix += "/"
        self.bucket = str(settings.tencent_cos_bucket or "").strip()
        self.ttl_seconds = int(settings.tencent_cos_signed_url_ttl_seconds)
        self._client = client

    @property
    def configured(self) -> bool:
        return bool(self.settings.tencent_cos_enabled and self.bucket and self.settings.tencent_cos_region)

    def _get_client(self):
        if not self.configured:
            raise TencentCosNotConfigured("腾讯云 COS 尚未配置")
        role_name = str(getattr(self.settings, "tencent_cos_cvm_role_name", "") or "").strip()
        if self._client is None or role_name:
            try:
                from qcloud_cos import CosConfig, CosS3Client
                secret_id = self.settings.tencent_cos_secret_id
                secret_key = self.settings.tencent_cos_secret_key
                token = self.settings.tencent_cos_security_token or None
                if role_name:
                    metadata_url = "http://metadata.tencentyun.com/latest/meta-data/cam/security-credentials/" + quote(role_name, safe="")
                    with urlopen(metadata_url, timeout=2) as response:
                        credentials = json.loads(response.read(32 * 1024).decode("utf-8"))
                    if int(credentials.get("Code", -1)) != 0:
                        raise TencentCosError("CVM 云角色临时凭证获取失败")
                    secret_id = str(credentials.get("AccessKeyId") or "")
                    secret_key = str(credentials.get("SecretAccessKey") or "")
                    token = str(credentials.get("Token") or "")
                    if not secret_id or not secret_key or not token:
                        raise TencentCosError("CVM 云角色临时凭证不完整")
                config = CosConfig(
                    Region=self.settings.tencent_cos_region,
                    SecretId=secret_id,
                    SecretKey=secret_key,
                    Token=token,
                    Scheme="https",
                )
                client = CosS3Client(config)
                if role_name:
                    return client
                self._client = client
            except Exception as exc:
                if isinstance(exc, TencentCosError):
                    raise
                raise TencentCosError("腾讯云 COS 客户端初始化失败") from exc
        return self._client

    def validate_key(self, key: str) -> str:
        clean = str(key or "").strip().lstrip("/")
        if not clean or "\\" in clean or any(part in {"", ".", ".."} for part in clean.split("/")):
            raise TencentCosUnsupportedVideo("COS 对象路径无效")
        if self.prefix and not clean.startswith(self.prefix):
            raise TencentCosUnsupportedVideo("COS 对象不在允许的课程目录中")
        if PurePosixPath(clean).suffix.lower() not in SUPPORTED_VIDEO_EXTENSIONS:
            raise TencentCosUnsupportedVideo("仅支持 MP4、WebM、MOV 或 M4V 视频")
        return clean

    @staticmethod
    def _error_code(exc: Exception) -> str:
        getter = getattr(exc, "get_error_code", None)
        return str(getter() if callable(getter) else "")

    @staticmethod
    def _status_code(exc: Exception) -> int:
        getter = getattr(exc, "get_status_code", None)
        try:
            return int(getter() if callable(getter) else 0)
        except (TypeError, ValueError):
            return 0

    def _get_video_metadata(self, clean: str) -> TencentCosVideo:
        response = self._get_client().get_object(Bucket=self.bucket, Key=clean, Range="bytes=0-0")
        body = response.get("Body")
        try:
            if body:
                body.get_raw_stream().read(1)
        finally:
            if body:
                raw = body.get_raw_stream()
                close = getattr(raw, "close", None)
                if callable(close):
                    close()
        content_range = str(response.get("Content-Range") or response.get("content-range") or "")
        match = re.search(r"/(\d+)$", content_range)
        size = int(match.group(1)) if match else int(response.get("Content-Length") or response.get("content-length") or 0)
        content_type = str(response.get("Content-Type") or response.get("content-type") or "")
        if content_type and not (content_type.startswith("video/") or content_type == "application/octet-stream"):
            raise TencentCosUnsupportedVideo("COS 对象不是受支持的视频")
        return TencentCosVideo(clean, PurePosixPath(clean).name, size, str(response.get("ETag") or "").strip('"'))

    def head_video(self, key: str) -> TencentCosVideo:
        clean = self.validate_key(key)
        try:
            response = self._get_client().head_object(Bucket=self.bucket, Key=clean)
        except Exception as exc:
            if self._error_code(exc) in {"NoSuchKey", "NotFound", "404"}:
                raise TencentCosObjectMissing("COS 视频不存在或已被移除") from exc
            if self._status_code(exc) != 403:
                raise TencentCosError("COS 视频校验失败") from exc
            try:
                return self._get_video_metadata(clean)
            except TencentCosUnsupportedVideo:
                raise
            except Exception as fallback_exc:
                if self._error_code(fallback_exc) in {"NoSuchKey", "NotFound", "404"}:
                    raise TencentCosObjectMissing("COS 视频不存在或已被移除") from fallback_exc
                raise TencentCosError("COS 视频校验失败") from fallback_exc
        size = int(response.get("Content-Length") or response.get("content-length") or 0)
        content_type = str(response.get("Content-Type") or response.get("content-type") or "")
        if content_type and not (content_type.startswith("video/") or content_type == "application/octet-stream"):
            raise TencentCosUnsupportedVideo("COS 对象不是受支持的视频")
        return TencentCosVideo(clean, PurePosixPath(clean).name, size, str(response.get("ETag") or "").strip('"'))

    def list_videos(self, search: str = "", marker: str = "", limit: int = 100) -> dict[str, Any]:
        try:
            response = self._get_client().list_objects(
                Bucket=self.bucket,
                Prefix=self.prefix,
                Marker=marker,
                MaxKeys=max(1, min(int(limit), 200)),
            )
        except Exception as exc:
            fallback_keys = tuple(getattr(self.settings, "tencent_cos_fallback_video_keys", ()) or ())
            if self._status_code(exc) != 403 or not fallback_keys:
                raise TencentCosError("COS 文件列表加载失败") from exc
            return self._list_fallback_videos(fallback_keys, search, marker, limit)
        needle = search.strip().casefold()
        videos = []
        for item in response.get("Contents") or []:
            key = str(item.get("Key") or "")
            try:
                clean = self.validate_key(key)
            except TencentCosUnsupportedVideo:
                continue
            filename = PurePosixPath(clean).name
            if needle and needle not in filename.casefold() and needle not in clean.casefold():
                continue
            videos.append(TencentCosVideo(
                clean, filename, int(item.get("Size") or 0), str(item.get("ETag") or "").strip('"'),
                str(item.get("LastModified") or ""),
            ).as_dict())
        return {
            "bucket": self.bucket,
            "prefix": self.prefix,
            "items": videos,
            "next_marker": str(response.get("NextMarker") or ((response.get("Contents") or [{}])[-1].get("Key") if str(response.get("IsTruncated") or "false").lower() == "true" else "") or ""),
            "is_truncated": str(response.get("IsTruncated") or "false").lower() == "true",
        }

    def _list_fallback_videos(self, keys: tuple[str, ...], search: str, marker: str, limit: int) -> dict[str, Any]:
        needle = search.strip().casefold()
        videos = []
        for key in sorted(set(keys)):
            try:
                clean = self.validate_key(key)
                if marker and clean <= marker:
                    continue
                video = self.head_video(clean)
            except (TencentCosObjectMissing, TencentCosUnsupportedVideo):
                continue
            if needle and needle not in video.filename.casefold() and needle not in video.key.casefold():
                continue
            videos.append(video.as_dict())
        page_size = max(1, min(int(limit), 200))
        page = videos[:page_size]
        truncated = len(videos) > page_size
        return {
            "bucket": self.bucket,
            "prefix": self.prefix,
            "items": page,
            "next_marker": page[-1]["key"] if truncated and page else "",
            "is_truncated": truncated,
        }

    def signed_url(self, key: str) -> dict[str, Any]:
        video = self.head_video(key)
        try:
            url = self._get_client().get_presigned_url(
                Method="GET", Bucket=self.bucket, Key=video.key, Expired=self.ttl_seconds,
            )
        except Exception as exc:
            raise TencentCosError("COS 鉴权预览地址生成失败") from exc
        return {"url": url, "expires_in": self.ttl_seconds, "video": video.as_dict()}
