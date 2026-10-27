from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import onnxruntime as ort


@dataclass(frozen=True)
class HeardPhone:
    phone: str
    confidence: float


@dataclass(frozen=True)
class RecognitionResult:
    heard: list[HeardPhone]
    target_confidence: list[float]


class PhonemeRecognizer:
    def __init__(self, model_path: Path, vocab_path: Path, threads: int = 2) -> None:
        self.model_path = model_path
        self.vocab_path = vocab_path
        self.threads = max(1, threads)
        self._session: ort.InferenceSession | None = None
        self._vocab: tuple[str, ...] = ()
        self._token_ids: dict[str, int] = {}
        self._lock = threading.Lock()

    @property
    def ready(self) -> bool:
        return self._session is not None

    def load(self) -> None:
        if self._session is not None:
            return
        with self._lock:
            if self._session is not None:
                return
            if not self.model_path.is_file():
                raise FileNotFoundError(f"ONNX model not found: {self.model_path}")
            vocabulary = json.loads(self.vocab_path.read_text(encoding="utf-8"))
            self._vocab = tuple(token for token, _ in sorted(vocabulary.items(), key=lambda item: item[1]))
            self._token_ids = {token: int(token_id) for token, token_id in vocabulary.items()}
            options = ort.SessionOptions()
            options.intra_op_num_threads = self.threads
            options.inter_op_num_threads = 1
            options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            self._session = ort.InferenceSession(
                str(self.model_path),
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )

    def recognize(self, waveform: np.ndarray) -> list[HeardPhone]:
        return self.recognize_word(waveform, []).heard

    def recognize_word(self, waveform: np.ndarray, expected_phones: list[str]) -> RecognitionResult:
        self.load()
        assert self._session is not None
        logits = self._session.run(
            ["logits"], {"input_values": np.ascontiguousarray(waveform[None, :], dtype=np.float32)}
        )[0][0]
        return RecognitionResult(
            heard=self._decode_ctc(logits),
            target_confidence=self._forced_target_confidence(logits, expected_phones),
        )

    def _forced_target_confidence(self, logits: np.ndarray, expected_phones: list[str]) -> list[float]:
        """Return a tolerant CTC confidence for each phone in a known target word."""
        if not expected_phones:
            return []
        try:
            token_ids = [self._token_ids[phone] for phone in expected_phones]
        except KeyError:
            return [0.0] * len(expected_phones)

        maximum = logits.max(axis=-1, keepdims=True)
        exp = np.exp(logits - maximum)
        probabilities = exp / exp.sum(axis=-1, keepdims=True)
        log_probabilities = np.log(np.maximum(probabilities, 1e-12))
        blank = self._token_ids.get("[PAD]", 42)
        extended = [blank]
        for token_id in token_ids:
            extended.extend((token_id, blank))

        frames, states = logits.shape[0], len(extended)
        if frames == 0 or frames < len(expected_phones):
            return [0.0] * len(expected_phones)
        scores = np.full((frames, states), -np.inf, dtype=np.float32)
        back = np.full((frames, states), -1, dtype=np.int32)
        scores[0, 0] = log_probabilities[0, blank]
        if states > 1:
            scores[0, 1] = log_probabilities[0, extended[1]]

        for frame in range(1, frames):
            for state, token_id in enumerate(extended):
                candidates = [(scores[frame - 1, state], state)]
                if state > 0:
                    candidates.append((scores[frame - 1, state - 1], state - 1))
                if state > 1 and token_id != blank and token_id != extended[state - 2]:
                    candidates.append((scores[frame - 1, state - 2], state - 2))
                best_score, prior_state = max(candidates, key=lambda item: item[0])
                scores[frame, state] = best_score + log_probabilities[frame, token_id]
                back[frame, state] = prior_state

        final_candidates = [(scores[-1, states - 1], states - 1)]
        if states > 1:
            final_candidates.append((scores[-1, states - 2], states - 2))
        _, state = max(final_candidates, key=lambda item: item[0])
        path: list[int] = []
        for frame in range(frames - 1, -1, -1):
            path.append(state)
            state = int(back[frame, state]) if frame else state
        path.reverse()

        aligned: list[list[float]] = [[] for _ in expected_phones]
        for frame, state in enumerate(path):
            if state % 2 == 1:
                target_index = state // 2
                aligned[target_index].append(float(probabilities[frame, token_ids[target_index]]))
        return [round(max(values), 4) if values else 0.0 for values in aligned]

    def _decode_ctc(self, logits: np.ndarray) -> list[HeardPhone]:
        maximum = logits.max(axis=-1, keepdims=True)
        exp = np.exp(logits - maximum)
        probabilities = exp / exp.sum(axis=-1, keepdims=True)
        ids = logits.argmax(axis=-1)
        output: list[HeardPhone] = []
        start = 0
        ignored = {0, 41, 42, 43, 44}  # delimiter, unknown, CTC blank, BOS, EOS
        for end in range(1, len(ids) + 1):
            if end < len(ids) and ids[end] == ids[start]:
                continue
            token_id = int(ids[start])
            if token_id not in ignored:
                confidence = float(probabilities[start:end, token_id].max())
                output.append(HeardPhone(self._vocab[token_id], round(confidence, 4)))
            start = end
        return output

