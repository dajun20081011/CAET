import re
import time
import uuid
from collections import defaultdict

from app.core.config import Settings
from app.schemas import AssessmentResponse, AudioInfo, Diagnosis, PhonemeResult, WordResult
from app.services.alignment import align_phones, observed_for_expected
from app.services.audio import ProcessedAudio
from app.services.backend import MockBackend, PronunciationBackend, WavLMBackend
from app.services.phonetics import feedback_zh, strip_stress, to_ipa
from app.services.wordbank import get_word, normalize_expected_text


class PronunciationEngine:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.backend = self._create_backend()

    def _create_backend(self) -> PronunciationBackend:
        if self.settings.engine_backend == "mock":
            return MockBackend()
        return WavLMBackend(
            model_dir=self.settings.model_dir,
            device=self.settings.device,
            repo_id=self.settings.wavlm_repo_id,
            revision=self.settings.wavlm_revision,
            checkpoint_filename=self.settings.wavlm_checkpoint,
            checkpoint_sha256=self.settings.wavlm_checkpoint_sha256,
            wavlm_base_model_id=self.settings.wavlm_base_model_id,
            wavlm_base_revision=self.settings.wavlm_base_revision,
            ctc_model_id=self.settings.ctc_model_id,
            ctc_revision=self.settings.ctc_revision,
            hf_token=self.settings.hf_token,
        )

    def load(self) -> None:
        self.backend.load()

    @property
    def ready(self) -> bool:
        return self.backend.loaded

    def _g2p(self, text: str) -> tuple[list[str], list[str]]:
        import cmudict

        words = re.findall(r"[A-Za-z']+", text)
        phones: list[str] = []
        phone_words: list[str] = []
        dictionary = cmudict.dict()
        for word in words:
            pronunciations = dictionary.get(word.lower())
            if not pronunciations:
                continue
            for phone in pronunciations[0]:
                phones.append(strip_stress(phone))
                phone_words.append(word.lower())
        return phones, phone_words

    def assess(
        self,
        *,
        audio: ProcessedAudio,
        original_filename: str,
        word_id: str | None,
        expected_text: str | None,
    ) -> AssessmentResponse:
        started = time.perf_counter()
        if word_id:
            entry = get_word(word_id)
            text = entry.word
            expected = [strip_stress(phone) for phone in entry.arpabet]
            phone_words = [entry.word] * len(expected)
            result_word_id = entry.id
        else:
            text = normalize_expected_text(expected_text or "")
            expected, phone_words = self._g2p(text)
            result_word_id = None
        if not expected:
            raise ValueError("No supported English phonemes could be extracted")

        backend_result = self.backend.assess(audio.samples, audio.sample_rate, expected)
        expected_ipa = [to_ipa(phone) for phone in expected]
        alignment = align_phones(expected_ipa, backend_result.observed_phones)
        aligned_observed = observed_for_expected(alignment)

        grouped: dict[str, list[PhonemeResult]] = defaultdict(list)
        for index, raw in enumerate(backend_result.phones):
            observed = aligned_observed[index] if index < len(aligned_observed) else None
            ipa = expected_ipa[index]
            aligned_match = observed == ipa
            if observed is None:
                diagnosis = Diagnosis.deletion
            elif not aligned_match and raw.error_probability >= self.settings.pherr_threshold:
                diagnosis = Diagnosis.substitution
            elif (
                raw.score < self.settings.weak_score_threshold
                or raw.error_probability >= self.settings.pherr_threshold
                or not aligned_match
            ):
                diagnosis = Diagnosis.weak
            else:
                diagnosis = Diagnosis.correct
            grouped[phone_words[index]].append(
                PhonemeResult(
                    index=index,
                    expected=strip_stress(raw.phone),
                    expected_ipa=ipa,
                    observed=observed,
                    score=round(raw.score, 1),
                    error_probability=round(raw.error_probability, 3),
                    gop=raw.gop,
                    diagnosis=diagnosis,
                    feedback_zh=feedback_zh(ipa, observed, diagnosis.value),
                )
            )

        words = [
            WordResult(
                word=word,
                score=round(sum(phone.score for phone in phones) / len(phones), 1),
                phonemes=phones,
            )
            for word, phones in grouped.items()
        ]
        flat = [phone for word in words for phone in word.phonemes]
        overall = round(sum(phone.score for phone in flat) / len(flat), 1)
        errors = sum(phone.diagnosis != Diagnosis.correct for phone in flat)
        return AssessmentResponse(
            request_id=str(uuid.uuid4()),
            engine=self.backend.name,
            model_version=self.backend.version,
            word_id=result_word_id,
            expected_text=text,
            overall_score=overall,
            error_count=errors,
            latency_ms=round((time.perf_counter() - started) * 1000),
            audio=AudioInfo(
                original_filename=original_filename,
                duration_ms=audio.duration_ms,
                trimmed=audio.trimmed,
            ),
            observed_phonemes=backend_result.observed_phones,
            words=words,
        )
