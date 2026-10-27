from __future__ import annotations

import os
from pathlib import Path
import sys
from uuid import uuid4

from app.core.config import settings
from app.integrations.ai_gateway import aggregate_status
from app.integrations.oss import build_object_storage
from app.integrations.runtime import build_ai_gateway


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python -m app.integrations.provider_smoke <safe-test-audio>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    reference_text = os.getenv("PHASE7_REFERENCE_TEXT", "Ladies and gentlemen, welcome aboard.").strip()
    if not path.is_file() or not reference_text:
        print("PHASE7_INPUT=FAIL", file=sys.stderr)
        return 2
    storage = build_object_storage(settings)
    object_key = f"phase7-smoke/{uuid4().hex}{path.suffix.lower()}"
    audio_ref = storage.save(object_key, path.read_bytes(), "audio/wav" if path.suffix.lower() == ".wav" else "audio/webm")
    try:
        gateway = build_ai_gateway(settings, storage.read)
        results = gateway.analyze(reference_text=reference_text, audio_ref=audio_ref,
                                  requested_adapters=list(settings.ai_required_adapters))
        for result in results:
            print(f"ADAPTER={result.adapter} PROVIDER={result.provider} STATUS={result.status} ATTEMPTS={result.attempts}")
        status = aggregate_status(results)
        print(f"AI_GATEWAY_STATUS={status}")
        print(f"OBJECT_STORAGE={storage.provider}")
        return 0 if status == "completed" else 1
    finally:
        storage.delete(audio_ref)


if __name__ == "__main__":
    raise SystemExit(main())

