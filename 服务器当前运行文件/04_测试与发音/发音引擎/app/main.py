from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .alignment import assess_alignment
from .audio import AudioError, SAMPLE_RATE, decode_audio, prepare_waveform
from .config import ROOT, settings
from .g2p import normalize_word, resolve_word
from .model import PhonemeRecognizer
from .schemas import AssessmentResponse, HealthResponse, ResolveWordsRequest, WordSummary
from .wordbank import load_word_bank, public_word


recognizer = PhonemeRecognizer(settings.model_path, settings.vocab_path, settings.onnx_intra_threads)
assessment_slots = asyncio.Semaphore(settings.max_concurrent_assessments)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.model_preload:
        await asyncio.to_thread(recognizer.load)
    yield


app = FastAPI(
    title="CabinLingo Pronunciation Engine",
    version=__version__,
    description="Independent, lightweight phoneme-level pronunciation training service.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__, model_ready=recognizer.ready)


@app.get("/ready", response_model=HealthResponse)
async def ready() -> HealthResponse:
    if not recognizer.ready:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="model is not ready")
    return HealthResponse(status="ok", version=__version__, model_ready=True)


@app.get("/api/v1/words", response_model=list[WordSummary])
async def list_words() -> list[dict]:
    return [public_word(word) for word in load_word_bank(settings.word_bank_path).values()]


@app.post("/api/v1/words/resolve", response_model=list[WordSummary])
async def resolve_words(data: ResolveWordsRequest) -> list[dict]:
    bank = load_word_bank(settings.word_bank_path)
    resolved: list[dict] = []
    seen: set[str] = set()
    for raw_word in data.words:
        word_id = normalize_word(raw_word)
        if not word_id or word_id in seen:
            continue
        seen.add(word_id)
        try:
            word = bank.get(word_id) or await asyncio.to_thread(resolve_word, word_id)
        except (OSError, subprocess.SubprocessError, ValueError):
            continue
        resolved.append(public_word(word))
    if not resolved:
        raise HTTPException(status_code=422, detail="没有可解析的英文单词")
    return resolved


@app.get("/api/v1/words/{word_id}", response_model=WordSummary)
async def get_word(word_id: str) -> dict:
    normalized = normalize_word(word_id)
    try:
        word = load_word_bank(settings.word_bank_path).get(normalized) or await asyncio.to_thread(resolve_word, normalized)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="word not found") from exc
    return public_word(word)


async def _save_upload(upload: UploadFile) -> Path:
    suffix = Path(upload.filename or "recording.webm").suffix[:12] or ".audio"
    handle, raw_path = tempfile.mkstemp(prefix="cabinlingo-", suffix=suffix)
    path = Path(raw_path)
    total = 0
    try:
        with os.fdopen(handle, "wb") as output:
            while chunk := await upload.read(64 * 1024):
                total += len(chunk)
                if total > settings.max_audio_bytes:
                    raise HTTPException(status_code=413, detail="录音文件过大")
                output.write(chunk)
        if total == 0:
            raise HTTPException(status_code=400, detail="录音为空")
        return path
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()


@app.post("/api/v1/assess", response_model=AssessmentResponse)
async def assess(word_id: str = Form(...), audio: UploadFile = File(...)) -> dict:
    normalized = normalize_word(word_id)
    try:
        word = load_word_bank(settings.word_bank_path).get(normalized) or await asyncio.to_thread(resolve_word, normalized)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="word not found") from exc
    path = await _save_upload(audio)
    try:
        try:
            waveform = await asyncio.to_thread(decode_audio, path, settings.max_audio_seconds)
            audio_seconds = len(waveform) / SAMPLE_RATE
            waveform = prepare_waveform(waveform)
        except AudioError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        async with assessment_slots:
            started = time.perf_counter()
            recognition = await asyncio.to_thread(recognizer.recognize_word, waveform, word["phonemes"])
            inference_ms = round((time.perf_counter() - started) * 1000)
        result = assess_alignment(word, recognition.heard, recognition.target_confidence)
        return {
            "request_id": str(uuid.uuid4()),
            "word": public_word(word),
            "score": result["score"],
            "verdict": result["verdict"],
            "expected_phones": word["phonemes"],
            "heard_phones": [item.phone for item in recognition.heard],
            "heard_phone_confidence": [item.confidence for item in recognition.heard],
            "phonemes": result["phonemes"],
            "feedback": result["feedback"],
            "metrics": {
                "audio_seconds": round(audio_seconds, 3),
                "inference_ms": inference_ms,
                "target_error_count": result["target_error_count"],
            },
        }
    finally:
        path.unlink(missing_ok=True)

