import base64
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .xfyun_iat import build_xfyun_auth_url


_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass(frozen=True)
class XfyunSuperTTSConfig:
    endpoint: str
    app_id: str
    api_key: str
    api_secret: str

    storage_dir: str = "/uploads/tts"
    provider: str = "xfyun_super_tts"
    version: str = "v1"

    timeout_seconds: float = 30.0
    max_text_bytes: int = 64 * 1024

    # Verified against the production XFYUN endpoint: payload.text.text
    # must contain Base64-encoded UTF-8 source text.
    request_text_base64: bool = True

    @property
    def configured(self) -> bool:
        return all(
            (
                self.endpoint,
                self.app_id,
                self.api_key,
                self.api_secret,
            )
        )


class XfyunSuperTTSError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        sid: str | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.sid = sid
        self.retryable = retryable


class XfyunSuperTTSAdapter:
    def __init__(
        self,
        config: XfyunSuperTTSConfig,
        connector: Callable[..., Any] | None = None,
    ) -> None:
        self.config = config
        self.connector = connector

    def generate(
        self,
        *,
        text: str,
        vcn: str,
        speed: int = 50,
        volume: int = 50,
        pitch: int = 50,
        rhy: int = 1,
        force: bool = False,
        oral_level: str | None = None,
    ) -> dict[str, Any]:
        if not self.config.configured:
            raise XfyunSuperTTSError("xfyun_super_tts_unconfigured")

        normalized_text = self._normalize_text(text)

        self._validate_range("speed", speed, 0, 100)
        self._validate_range("volume", volume, 0, 100)
        self._validate_range("pitch", pitch, 0, 100)

        if rhy not in {0, 1}:
            raise XfyunSuperTTSError("xfyun_super_tts_rhy_invalid")

        voice = vcn.strip()
        if not voice:
            raise XfyunSuperTTSError("xfyun_super_tts_vcn_required")

        cache_key = self._cache_key(
            text=normalized_text,
            vcn=voice,
            speed=speed,
            volume=volume,
            pitch=pitch,
            rhy=rhy,
            oral_level=oral_level,
        )

        target_dir = Path(self.config.storage_dir) / cache_key
        mp3_path = target_dir / "standard.mp3"
        source_path = target_dir / "source.txt"
        pybuf_path = target_dir / "pybuf.txt"
        metadata_path = target_dir / "metadata.json"

        if (
            not force
            and mp3_path.is_file()
            and source_path.is_file()
            and metadata_path.is_file()
        ):
            return {
                "status": "cached",
                "cache_key": cache_key,
                "mp3_path": str(mp3_path),
                "source_path": str(source_path),
                "pybuf_path": str(pybuf_path) if pybuf_path.is_file() else None,
                "metadata_path": str(metadata_path),
            }

        request = self._build_request(
            text=normalized_text,
            vcn=voice,
            speed=speed,
            volume=volume,
            pitch=pitch,
            rhy=rhy,
            oral_level=oral_level,
        )

        audio_bytes, pybuf_text, sid = self._request_provider(request)

        if not audio_bytes:
            raise XfyunSuperTTSError(
                "xfyun_super_tts_audio_empty",
                sid=sid,
            )

        target_dir.mkdir(parents=True, exist_ok=True)

        metadata = {
            "cache_key": cache_key,
            "provider": self.config.provider,
            "product": "super_tts",
            "version": self.config.version,
            "sid": sid,
            "vcn": voice,
            "speed": speed,
            "volume": volume,
            "pitch": pitch,
            "rhy": rhy,
            "oral_level": oral_level,
            "audio": {
                "encoding": "lame",
                "format": "mp3",
                "sample_rate": 24000,
                "channels": 1,
                "bit_depth": 16,
            },
            "request_text_encoding": (
                "base64"
                if self.config.request_text_base64
                else "utf8"
            ),
            "source_hash": hashlib.sha256(
                normalized_text.encode("utf-8")
            ).hexdigest(),
            "text_bytes": len(normalized_text.encode("utf-8")),
            "audio_bytes": len(audio_bytes),
            "pybuf_available": bool(pybuf_text),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "endpoint": self.config.endpoint,
        }

        self._atomic_write_bytes(mp3_path, audio_bytes)
        self._atomic_write_text(source_path, normalized_text)

        if pybuf_text:
            self._atomic_write_text(pybuf_path, pybuf_text)
        elif pybuf_path.exists():
            pybuf_path.unlink()

        self._atomic_write_text(
            metadata_path,
            json.dumps(
                metadata,
                ensure_ascii=False,
                indent=2,
            ),
        )

        return {
            "status": "generated",
            "cache_key": cache_key,
            "sid": sid,
            "mp3_path": str(mp3_path),
            "source_path": str(source_path),
            "pybuf_path": str(pybuf_path) if pybuf_text else None,
            "metadata_path": str(metadata_path),
            "metadata": metadata,
        }

    def _build_request(
        self,
        *,
        text: str,
        vcn: str,
        speed: int,
        volume: int,
        pitch: int,
        rhy: int,
        oral_level: str | None,
    ) -> dict[str, Any]:
        tts: dict[str, Any] = {
            "vcn": vcn,
            "speed": speed,
            "volume": volume,
            "pitch": pitch,
            "bgs": 0,
            "reg": 0,
            "rdn": 0,
            "rhy": rhy,
            "audio": {
                "encoding": "lame",
                "sample_rate": 24000,
                "channels": 1,
                "bit_depth": 16,
                "frame_size": 0,
            },
        }

        parameter: dict[str, Any] = {
            "tts": tts,
        }

        # XFYUN documents parameter.oral for x4-family voices only.
        # Never send an empty oral object for x5/x6 voices.
        if oral_level is not None:
            if not vcn.lower().startswith("x4"):
                raise XfyunSuperTTSError(
                    "xfyun_super_tts_oral_requires_x4"
                )

            parameter["oral"] = {
                "oral_level": oral_level,
                "spark_assist": 0,
                "stop_split": 0,
                "remain": 1,
            }

        payload_text = (
            base64.b64encode(text.encode("utf-8")).decode("ascii")
            if self.config.request_text_base64
            else text
        )

        return {
            "header": {
                "app_id": self.config.app_id,
                "status": 2,
            },
            "parameter": parameter,
            "payload": {
                "text": {
                    "encoding": "utf8",
                    "compress": "raw",
                    "format": "plain",
                    "status": 2,
                    "seq": 0,
                    "text": payload_text,
                }
            },
        }

    def _request_provider(
        self,
        request: dict[str, Any],
    ) -> tuple[bytes, str, str | None]:
        connector = self.connector

        if connector is None:
            try:
                from websockets.sync.client import connect
            except ImportError as exc:
                raise XfyunSuperTTSError(
                    "websockets_dependency_missing"
                ) from exc

            connector = connect

        url = build_xfyun_auth_url(
            self.config.endpoint,
            self.config.api_key,
            self.config.api_secret,
        )

        audio_chunks: list[tuple[int, bytes]] = []
        pybuf_chunks: list[tuple[int, bytes]] = []
        sid: str | None = None

        try:
            with connector(
                url,
                open_timeout=self.config.timeout_seconds,
                close_timeout=self.config.timeout_seconds,
                max_size=16 * 1024 * 1024,
            ) as socket:
                socket.send(
                    json.dumps(
                        request,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                )

                deadline = (
                    time.monotonic()
                    + self.config.timeout_seconds
                )

                while time.monotonic() < deadline:
                    try:
                        raw = socket.recv(
                            timeout=max(
                                0.1,
                                deadline - time.monotonic(),
                            )
                        )
                    except TimeoutError:
                        break

                    if not raw:
                        break

                    payload = json.loads(raw)

                    header = (
                        payload.get("header")
                        if isinstance(
                            payload.get("header"),
                            dict,
                        )
                        else {}
                    )

                    code = int(header.get("code", 0) or 0)
                    sid = (
                        str(header.get("sid") or sid or "")
                        or None
                    )

                    if code:
                        raise XfyunSuperTTSError(
                            f"xfyun_super_tts_code_{code}",
                            sid=sid,
                        )

                    response_payload = payload.get("payload") or {}

                    audio = response_payload.get("audio")
                    if isinstance(audio, dict):
                        encoded = audio.get("audio")
                        if not isinstance(encoded, str):
                            encoded = audio.get("text")

                        if isinstance(encoded, str) and encoded:
                            try:
                                decoded = base64.b64decode(
                                    encoded,
                                    validate=True,
                                )
                            except (ValueError, TypeError) as exc:
                                raise XfyunSuperTTSError(
                                    "xfyun_super_tts_audio_invalid",
                                    sid=sid,
                                ) from exc

                            audio_chunks.append(
                                (
                                    int(
                                        audio.get(
                                            "seq",
                                            len(audio_chunks),
                                        )
                                        or 0
                                    ),
                                    decoded,
                                )
                            )

                    pybuf = response_payload.get("pybuf")
                    if isinstance(pybuf, dict):
                        encoded = pybuf.get("text")

                        if isinstance(encoded, str) and encoded:
                            try:
                                decoded = base64.b64decode(
                                    encoded,
                                    validate=True,
                                )
                            except (ValueError, TypeError) as exc:
                                raise XfyunSuperTTSError(
                                    "xfyun_super_tts_pybuf_invalid",
                                    sid=sid,
                                ) from exc

                            pybuf_chunks.append(
                                (
                                    int(
                                        pybuf.get(
                                            "seq",
                                            len(pybuf_chunks),
                                        )
                                        or 0
                                    ),
                                    decoded,
                                )
                            )

                    header_status = int(
                        header.get("status", 0) or 0
                    )

                    if header_status == 2:
                        break

        except XfyunSuperTTSError:
            raise
        except Exception as exc:
            raise XfyunSuperTTSError(
                "xfyun_super_tts_transport_error",
                sid=sid,
                retryable=True,
            ) from exc

        if not audio_chunks:
            raise XfyunSuperTTSError(
                "xfyun_super_tts_no_audio",
                sid=sid,
            )

        audio_bytes = b"".join(
            chunk
            for _, chunk in sorted(
                audio_chunks,
                key=lambda item: item[0],
            )
        )

        pybuf_bytes = b"".join(
            chunk
            for _, chunk in sorted(
                pybuf_chunks,
                key=lambda item: item[0],
            )
        )

        pybuf_text = (
            pybuf_bytes.decode("utf-8", errors="replace")
            if pybuf_bytes
            else ""
        )

        return audio_bytes, pybuf_text, sid

    def _cache_key(
        self,
        *,
        text: str,
        vcn: str,
        speed: int,
        volume: int,
        pitch: int,
        rhy: int,
        oral_level: str | None,
    ) -> str:
        payload = {
            "text": text,
            "vcn": vcn,
            "speed": speed,
            "volume": volume,
            "pitch": pitch,
            "rhy": rhy,
            "oral_level": oral_level,
            "audio_encoding": "lame",
            "sample_rate": 24000,
        }

        return hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    def _normalize_text(self, text: str) -> str:
        if not isinstance(text, str):
            raise XfyunSuperTTSError(
                "xfyun_super_tts_text_invalid"
            )

        normalized = (
            text.replace("\r\n", "\n")
            .replace("\r", "\n")
            .strip()
        )

        if not normalized:
            raise XfyunSuperTTSError(
                "xfyun_super_tts_text_empty"
            )

        if "\t" in normalized:
            raise XfyunSuperTTSError(
                "xfyun_super_tts_text_contains_tab"
            )

        if _CONTROL_RE.search(normalized):
            raise XfyunSuperTTSError(
                "xfyun_super_tts_text_contains_control_character"
            )

        text_bytes = len(normalized.encode("utf-8"))

        if text_bytes > self.config.max_text_bytes:
            raise XfyunSuperTTSError(
                "xfyun_super_tts_text_too_large"
            )

        return normalized

    @staticmethod
    def _validate_range(
        name: str,
        value: int,
        minimum: int,
        maximum: int,
    ) -> None:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < minimum
            or value > maximum
        ):
            raise XfyunSuperTTSError(
                f"xfyun_super_tts_{name}_invalid"
            )

    @staticmethod
    def _atomic_write_bytes(
        path: Path,
        data: bytes,
    ) -> None:
        temporary = path.with_suffix(
            path.suffix + ".tmp"
        )
        temporary.write_bytes(data)
        os.replace(temporary, path)

    @staticmethod
    def _atomic_write_text(
        path: Path,
        text: str,
    ) -> None:
        temporary = path.with_suffix(
            path.suffix + ".tmp"
        )
        temporary.write_text(
            text,
            encoding="utf-8",
        )
        os.replace(temporary, path)
