from __future__ import annotations

import io
import subprocess
from tempfile import TemporaryDirectory
import wave
from dataclasses import dataclass
from typing import Any, Callable


class AudioTranscodeError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class TranscodedAudio:
    data: bytes
    content_type: str = "audio/wav"
    extension: str = ".wav"
    sample_rate: int = 16000
    channels: int = 1
    sample_width: int = 2


@dataclass(frozen=True)
class EncodedAudio:
    data: bytes
    content_type: str
    encoding: str
    sample_rate: int = 16000
    channels: int = 1
    bit_depth: int = 16


Runner = Callable[..., Any]


def normalize_speech_audio(
    data: bytes,
    content_type: str,
    *,
    ffmpeg_binary: str = "ffmpeg",
    timeout_seconds: float = 30,
    max_seconds: int = 300,
    max_input_bytes: int = 25 * 1024 * 1024,
    max_output_bytes: int = 12 * 1024 * 1024,
    runner: Runner = subprocess.run,
) -> TranscodedAudio:
    """Return a bounded 16 kHz, signed 16-bit, mono WAV for speech providers."""
    if not data:
        raise AudioTranscodeError("audio_empty")
    if len(data) > max_input_bytes:
        raise AudioTranscodeError("audio_too_large")
    if max_seconds <= 0 or timeout_seconds <= 0 or max_output_bytes <= 44:
        raise AudioTranscodeError("audio_transcode_configuration_invalid")

    if _is_standard_wav(data):
        if len(data) > max_output_bytes:
            raise AudioTranscodeError("audio_transcoded_too_large")
        return TranscodedAudio(data)

    with TemporaryDirectory(prefix="cabinlingo-audio-") as directory:
        output_path = f"{directory}/normalized.wav"
        command = [
            ffmpeg_binary,
            "-hide_banner",
            "-loglevel", "error",
            "-nostdin",
            "-threads", "1",
            "-i", "pipe:0",
            "-map", "0:a:0",
            "-vn",
            "-sn",
            "-dn",
            "-ac", "1",
            "-ar", "16000",
            "-sample_fmt", "s16",
            "-t", str(max_seconds),
            "-f", "wav",
            output_path,
        ]
        try:
            completed = runner(
                command,
                input=data,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise AudioTranscodeError("audio_transcode_timeout") from exc
        except (FileNotFoundError, OSError) as exc:
            raise AudioTranscodeError("audio_transcoder_unavailable") from exc

        from pathlib import Path
        output_file = Path(output_path)
        if completed.returncode != 0 or not output_file.is_file():
            raise AudioTranscodeError("audio_format_unsupported")
        try:
            output_size = output_file.stat().st_size
        except OSError as exc:
            raise AudioTranscodeError("audio_transcode_invalid_output") from exc
        if output_size > max_output_bytes:
            raise AudioTranscodeError("audio_transcoded_too_large")
        try:
            output = output_file.read_bytes()
        except OSError as exc:
            raise AudioTranscodeError("audio_transcode_invalid_output") from exc
        if not output or not _is_standard_wav(output):
            raise AudioTranscodeError("audio_transcode_invalid_output")
        return TranscodedAudio(output)


def encode_suntone_mp3(
    data: bytes,
    *,
    ffmpeg_binary: str = "ffmpeg",
    timeout_seconds: float = 30,
    max_seconds: int = 300,
    max_input_bytes: int = 15 * 1024 * 1024,
    max_output_bytes: int = 7 * 1024 * 1024,
    runner: Runner = subprocess.run,
) -> EncodedAudio:
    """Encode provider-ready 16 kHz mono MP3 without passing user text to a shell."""
    if not data:
        raise AudioTranscodeError("audio_empty")
    if len(data) > max_input_bytes:
        raise AudioTranscodeError("audio_too_large")
    if max_seconds <= 0 or timeout_seconds <= 0 or max_output_bytes <= 64:
        raise AudioTranscodeError("audio_transcode_configuration_invalid")

    with TemporaryDirectory(prefix="cabinlingo-suntone-") as directory:
        output_path = f"{directory}/suntone.mp3"
        command = [
            ffmpeg_binary,
            "-hide_banner",
            "-loglevel", "error",
            "-nostdin",
            "-threads", "1",
            "-i", "pipe:0",
            "-map", "0:a:0",
            "-vn",
            "-sn",
            "-dn",
            "-ac", "1",
            "-ar", "16000",
            "-codec:a", "libmp3lame",
            "-b:a", "24k",
            "-t", str(max_seconds),
            "-f", "mp3",
            output_path,
        ]
        try:
            completed = runner(
                command,
                input=data,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise AudioTranscodeError("audio_transcode_timeout") from exc
        except (FileNotFoundError, OSError) as exc:
            raise AudioTranscodeError("audio_transcoder_unavailable") from exc

        from pathlib import Path
        output_file = Path(output_path)
        if completed.returncode != 0 or not output_file.is_file():
            raise AudioTranscodeError("audio_format_unsupported")
        try:
            output_size = output_file.stat().st_size
            if output_size > max_output_bytes:
                raise AudioTranscodeError("audio_transcoded_too_large")
            output = output_file.read_bytes()
        except AudioTranscodeError:
            raise
        except OSError as exc:
            raise AudioTranscodeError("audio_transcode_invalid_output") from exc
        if not _looks_like_mp3(output):
            raise AudioTranscodeError("audio_transcode_invalid_output")
        return EncodedAudio(output, "audio/mpeg", "lame")


def _is_standard_wav(data: bytes) -> bool:
    try:
        with wave.open(io.BytesIO(data), "rb") as audio:
            return (
                audio.getnchannels() == 1
                and audio.getsampwidth() == 2
                and audio.getframerate() == 16000
                and audio.getnframes() > 0
                and audio.getcomptype() == "NONE"
            )
    except (wave.Error, EOFError):
        return False


def _looks_like_mp3(data: bytes) -> bool:
    if len(data) < 64:
        return False
    if data.startswith(b"ID3"):
        return True
    return any(data[index] == 0xFF and data[index + 1] & 0xE0 == 0xE0
               for index in range(min(len(data) - 1, 4096)))
