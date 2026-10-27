from __future__ import annotations

from typing import Any

from .practice_feedback import suntone_evidence


def enrich_instructor_review_detail(store: Any, detail: dict[str, Any], review_type: str, target_id: str) -> dict[str, Any]:
    """Expose already-persisted AI evidence without invoking an AI adapter."""
    detail.update(suntone_evidence(None))
    detail["recognized_text"] = None
    detail["alignment"] = []
    detail["alignment_source"] = None
    detail["alignment_provider"] = None

    if review_type == "practice":
        with store._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT transcript,feedback FROM cl_practice_attempts WHERE id=%s",
                (target_id,),
            )
            attempt = cur.fetchone()
        if attempt:
            transcript = attempt.get("transcript")
            feedback = attempt.get("feedback") if isinstance(attempt.get("feedback"), dict) else {}
            detail["recognized_text"] = transcript if isinstance(transcript, str) else (
                feedback.get("iat_transcript") or feedback.get("browser_transcript")
            )
            alignment = feedback.get("alignment")
            if isinstance(alignment, list):
                detail["alignment"] = alignment
            detail["alignment_source"] = feedback.get("alignment_source")
            detail["alignment_provider"] = feedback.get("alignment_provider")

    evidence = detail.get("ai_evidence") if isinstance(detail.get("ai_evidence"), dict) else {}
    suntone = evidence.get("suntone") if isinstance(evidence.get("suntone"), dict) else {}
    suntone_payload = suntone.get("payload") if isinstance(suntone.get("payload"), dict) else None
    if suntone.get("status") == "completed" and suntone_payload is not None:
        detail.update(suntone_evidence(suntone_payload))
        scores = suntone_payload.get("scores")
        if isinstance(scores, dict):
            detail.setdefault("ai_scores", {}).update(scores)

    iat = evidence.get("asr_iat") if isinstance(evidence.get("asr_iat"), dict) else {}
    iat_payload = iat.get("payload") if isinstance(iat.get("payload"), dict) else None
    if iat.get("status") == "completed" and iat_payload is not None:
        transcript = iat_payload.get("transcript")
        if isinstance(transcript, str):
            detail["recognized_text"] = transcript
        alignment = iat_payload.get("alignment")
        if isinstance(alignment, list):
            detail["alignment"] = alignment
            detail["alignment_source"] = iat_payload.get("alignment_source")
            detail["alignment_provider"] = iat.get("provider")
    return detail
