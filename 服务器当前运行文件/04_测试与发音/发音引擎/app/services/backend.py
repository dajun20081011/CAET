from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

import numpy as np


@dataclass(frozen=True)
class RawPhoneScore:
    phone: str
    score: float
    error_probability: float
    gop: float | None


@dataclass(frozen=True)
class BackendResult:
    phones: list[RawPhoneScore]
    observed_phones: list[str]


class PronunciationBackend(ABC):
    name: str
    version: str

    @property
    @abstractmethod
    def loaded(self) -> bool: ...

    @property
    @abstractmethod
    def device_name(self) -> str: ...

    @abstractmethod
    def load(self) -> None: ...

    @abstractmethod
    def assess(
        self,
        samples: np.ndarray,
        sample_rate: int,
        expected_phones: list[str],
    ) -> BackendResult: ...


class MockBackend(PronunciationBackend):
    name = "mock"
    version = "deterministic-pipeline-test"

    def __init__(self) -> None:
        self._loaded = False

    @property
    def loaded(self) -> bool:
        return self._loaded

    @property
    def device_name(self) -> str:
        return "cpu"

    def load(self) -> None:
        self._loaded = True

    def assess(
        self,
        samples: np.ndarray,
        sample_rate: int,
        expected_phones: list[str],
    ) -> BackendResult:
        self.load()
        energy = min(1.0, float(np.sqrt(np.mean(np.square(samples)))) * 8)
        base_score = 72.0 + energy * 20.0
        phones = [
            RawPhoneScore(phone=phone, score=base_score, error_probability=0.08, gop=2.5)
            for phone in expected_phones
        ]
        from app.services.phonetics import to_ipa

        return BackendResult(
            phones=phones, observed_phones=[to_ipa(phone) for phone in expected_phones]
        )


class WavLMBackend(PronunciationBackend):
    """WavLM scoring head + XLSR CTC alignment/decoder.

    Heavy libraries are imported lazily so health/live remains useful while models load.
    """

    name = "wavlm-ctc-mdd"
    version = "Jianshu001/wavlm-phoneme-scorer+facebook/xlsr53-espeak"

    def __init__(
        self,
        *,
        model_dir: Path,
        device: str,
        repo_id: str,
        revision: str,
        checkpoint_filename: str,
        checkpoint_sha256: str,
        wavlm_base_model_id: str,
        wavlm_base_revision: str,
        ctc_model_id: str,
        ctc_revision: str,
        hf_token: str | None = None,
    ) -> None:
        self.model_dir = model_dir
        self.requested_device = device
        self.repo_id = repo_id
        self.revision = revision
        self.checkpoint_filename = checkpoint_filename
        self.checkpoint_sha256 = checkpoint_sha256.lower()
        self.wavlm_base_model_id = wavlm_base_model_id
        self.wavlm_base_revision = wavlm_base_revision
        self.ctc_model_id = ctc_model_id
        self.ctc_revision = ctc_revision
        self.hf_token = hf_token
        self._loaded = False
        self._load_lock = Lock()
        self._inference_lock = Lock()
        self._device = "unresolved"

    @property
    def loaded(self) -> bool:
        return self._loaded

    @property
    def device_name(self) -> str:
        return str(self._device)

    def load(self) -> None:
        if self._loaded:
            return
        with self._load_lock:
            if self._loaded:
                return
            self._load_impl()
            self._loaded = True

    def _load_impl(self) -> None:
        import torch
        import torch.nn as nn
        from huggingface_hub import hf_hub_download
        from transformers import Wav2Vec2FeatureExtractor, Wav2Vec2ForCTC, WavLMModel

        if self.requested_device == "auto":
            self._device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        else:
            self._device = torch.device(self.requested_device)
        if self._device.type == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("DEVICE=cuda but CUDA is not available in this container")

        self.model_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_path = hf_hub_download(
            repo_id=self.repo_id,
            filename=self.checkpoint_filename,
            revision=self.revision,
            token=self.hf_token,
            local_dir=self.model_dir / "wavlm-phoneme-scorer",
        )

        class PhoneScorerHead(nn.Module):
            def __init__(self, n_phone_types: int) -> None:
                super().__init__()
                self.phone_emb = nn.Embedding(n_phone_types, 32)
                self.shared = nn.Sequential(
                    nn.Linear(1058, 512),
                    nn.BatchNorm1d(512),
                    nn.GELU(),
                    nn.Dropout(0.3),
                    nn.Linear(512, 512),
                    nn.BatchNorm1d(512),
                    nn.GELU(),
                    nn.Dropout(0.3),
                    nn.Linear(512, 256),
                    nn.BatchNorm1d(256),
                    nn.GELU(),
                    nn.Dropout(0.2),
                )
                self.score_head = nn.Sequential(nn.Linear(256, 64), nn.GELU(), nn.Linear(64, 1))
                self.pherr_head = nn.Sequential(nn.Linear(256, 64), nn.GELU(), nn.Linear(64, 1))

            def forward(self, hidden, phone_id, gop, frames):
                embedding = self.phone_emb(phone_id)
                features = torch.cat((hidden, embedding, gop[:, None], frames[:, None]), dim=-1)
                shared = self.shared(features)
                return self.score_head(shared).squeeze(-1), self.pherr_head(shared).squeeze(-1)

        self._torch = torch
        try:
            checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
        except Exception as safe_load_error:
            import hashlib

            with Path(checkpoint_path).open("rb") as checkpoint_file:
                actual_sha256 = hashlib.file_digest(checkpoint_file, "sha256").hexdigest()
            if actual_sha256 != self.checkpoint_sha256:
                raise RuntimeError(
                    "Checkpoint safe-load failed and SHA-256 does not match the pinned artifact"
                ) from safe_load_error
            checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        state = checkpoint["model_state"]
        backbone_state = {
            key.removeprefix("backbone."): value
            for key, value in state.items()
            if key.startswith("backbone.")
        }
        head_state = {key: value for key, value in state.items() if not key.startswith("backbone.")}

        self._phone_names = sorted(
            [
                "aa",
                "ae",
                "ah",
                "ao",
                "ar",
                "aw",
                "ax",
                "ay",
                "b",
                "ch",
                "d",
                "dh",
                "dr",
                "dz",
                "eh",
                "er",
                "ey",
                "f",
                "g",
                "hh",
                "ih",
                "ir",
                "iy",
                "jh",
                "k",
                "l",
                "m",
                "n",
                "ng",
                "oo",
                "ow",
                "oy",
                "p",
                "r",
                "s",
                "sh",
                "t",
                "th",
                "tr",
                "ts",
                "uh",
                "ur",
                "uw",
                "v",
                "w",
                "y",
                "z",
                "zh",
            ]
        )
        self._phone_to_id = {phone: index for index, phone in enumerate(self._phone_names)}

        self._backbone = WavLMModel.from_pretrained(
            self.wavlm_base_model_id,
            revision=self.wavlm_base_revision,
            token=self.hf_token,
            mask_time_prob=0.0,
        )
        self._backbone.load_state_dict(backbone_state, strict=False)
        self._backbone.to(self._device).eval()
        self._backbone_fe = Wav2Vec2FeatureExtractor.from_pretrained(
            self.wavlm_base_model_id,
            revision=self.wavlm_base_revision,
            token=self.hf_token,
        )

        self._scorer = PhoneScorerHead(len(self._phone_names))
        self._scorer.load_state_dict(head_state)
        self._scorer.to(self._device).eval()

        self._ctc = (
            Wav2Vec2ForCTC.from_pretrained(
                self.ctc_model_id,
                revision=self.ctc_revision,
                token=self.hf_token,
            )
            .to(self._device)
            .eval()
        )
        self._ctc_fe = Wav2Vec2FeatureExtractor.from_pretrained(
            self.ctc_model_id,
            revision=self.ctc_revision,
            token=self.hf_token,
        )
        vocab_file = hf_hub_download(
            repo_id=self.ctc_model_id,
            filename="vocab.json",
            revision=self.ctc_revision,
            token=self.hf_token,
        )
        import json

        self._vocab = json.loads(Path(vocab_file).read_text(encoding="utf-8"))
        self._id_to_token = {value: key for key, value in self._vocab.items()}
        self._blank = self._vocab.get("<pad>", 0)

    @staticmethod
    def _arpabet_candidates(phone: str) -> list[str]:
        from app.services.phonetics import to_ipa

        equivalents = {
            "AH": ["ʌ", "ə", "ɐ"],
            "AA": ["ɑː", "ɑ", "ɒ", "a"],
            "AO": ["ɔː", "ɔ", "ɒ"],
            "ER": ["ɜː", "ɝ", "ɚ", "ɜ"],
            "EH": ["ɛ", "e"],
            "IH": ["ɪ", "ᵻ"],
            "IY": ["iː", "i"],
            "OW": ["oʊ", "o", "əʊ"],
            "UH": ["ʊ"],
            "UW": ["uː", "u"],
            "R": ["ɹ", "r"],
            "G": ["ɡ", "g"],
        }
        from app.services.phonetics import strip_stress

        clean = strip_stress(phone)
        return equivalents.get(clean, [to_ipa(clean)])

    def _model_index(self, phone: str) -> int:
        for candidate in self._arpabet_candidates(phone):
            if candidate in self._vocab:
                return self._vocab[candidate]
        return -1

    @staticmethod
    def _viterbi(emissions, phone_indices: list[int], blank: int) -> list[tuple[int, int]]:
        import numpy as np

        frames, _ = emissions.shape
        if not phone_indices or frames < len(phone_indices):
            return []
        extended = [blank]
        for phone in phone_indices:
            extended.extend((phone, blank))
        states = len(extended)
        dp = np.full((frames, states), -np.inf, dtype=np.float64)
        back = np.zeros((frames, states), dtype=np.int32)
        dp[0, 0] = emissions[0, extended[0]].item()
        if states > 1:
            dp[0, 1] = emissions[0, extended[1]].item()
        for frame in range(1, frames):
            for state in range(states):
                options = [(dp[frame - 1, state], state)]
                if state > 0:
                    options.append((dp[frame - 1, state - 1], state - 1))
                if (
                    state > 1
                    and extended[state] != blank
                    and extended[state] != extended[state - 2]
                ):
                    options.append((dp[frame - 1, state - 2], state - 2))
                best, prior = max(options, key=lambda item: item[0])
                dp[frame, state] = best + emissions[frame, extended[state]].item()
                back[frame, state] = prior
        state = states - 1 if dp[-1, -1] >= dp[-1, -2] else states - 2
        path = []
        for frame in range(frames - 1, -1, -1):
            path.append((frame, extended[state]))
            state = back[frame, state]
        return list(reversed(path))

    def _decode(self, emissions) -> list[str]:
        ids = emissions.argmax(dim=-1).tolist()
        output: list[str] = []
        previous = None
        for token_id in ids:
            if token_id != previous and token_id != self._blank:
                token = self._id_to_token.get(token_id, "")
                if token and token not in {"<pad>", "<s>", "</s>", "<unk>", "|"}:
                    output.append(token)
            previous = token_id
        return output

    def assess(
        self,
        samples: np.ndarray,
        sample_rate: int,
        expected_phones: list[str],
    ) -> BackendResult:
        if sample_rate != 16_000:
            raise ValueError("WavLM backend requires 16 kHz audio")
        self.load()
        with self._inference_lock, self._torch.inference_mode():
            mapped = [(phone, self._model_index(phone)) for phone in expected_phones]
            if any(index < 0 for _, index in mapped):
                missing = [phone for phone, index in mapped if index < 0]
                raise ValueError(f"No CTC vocabulary mapping for: {missing}")
            indices = [index for _, index in mapped]

            ctc_input = self._ctc_fe(samples, sampling_rate=sample_rate, return_tensors="pt")
            logits = self._ctc(ctc_input.input_values.to(self._device)).logits
            emissions = self._torch.log_softmax(logits, dim=-1).squeeze(0).cpu()
            observed = self._decode(emissions)
            path = self._viterbi(emissions, indices, self._blank)
            if not path:
                raise RuntimeError("CTC forced alignment failed")

            segments: list[list[int]] = []
            current, current_frames = None, []
            for frame, token in path:
                if token == self._blank:
                    if current is not None:
                        segments.append(current_frames)
                    current, current_frames = None, []
                elif token != current:
                    if current is not None:
                        segments.append(current_frames)
                    current, current_frames = token, [frame]
                else:
                    current_frames.append(frame)
            if current is not None:
                segments.append(current_frames)

            bb_input = self._backbone_fe(samples, sampling_rate=sample_rate, return_tensors="pt")
            hidden = self._backbone(
                bb_input.input_values.to(self._device)
            ).last_hidden_state.squeeze(0)
            scale = hidden.shape[0] / emissions.shape[0]
            pooled, gops, frame_counts, valid_positions = [], [], [], []
            raw: list[RawPhoneScore | None] = [None] * len(expected_phones)
            for position, expected_index in enumerate(indices):
                if position >= len(segments) or not segments[position]:
                    raw[position] = RawPhoneScore(expected_phones[position], 0.0, 1.0, -20.0)
                    continue
                frames = segments[position]
                start = max(0, int(min(frames) * scale))
                end = min(hidden.shape[0], max(start + 1, int((max(frames) + 1) * scale)))
                pooled.append(hidden[start:end].mean(dim=0))
                segment_emissions = emissions[frames]
                target = segment_emissions[:, expected_index].mean().item()
                mask = self._torch.ones(emissions.shape[1], dtype=self._torch.bool)
                mask[self._blank] = False
                mask[expected_index] = False
                alternative = segment_emissions[:, mask].max(dim=-1).values.mean().item()
                gops.append(target - alternative)
                frame_counts.append(len(frames))
                valid_positions.append(position)

            if pooled:
                phone_ids = self._torch.tensor(
                    [
                        self._phone_to_id.get(expected_phones[pos].rstrip("012").lower(), 0)
                        for pos in valid_positions
                    ],
                    dtype=self._torch.long,
                    device=self._device,
                )
                scores, error_logits = self._scorer(
                    self._torch.stack(pooled),
                    phone_ids,
                    self._torch.tensor(gops, dtype=self._torch.float32, device=self._device),
                    self._torch.tensor(
                        frame_counts, dtype=self._torch.float32, device=self._device
                    ),
                )
                probabilities = self._torch.sigmoid(error_logits)
                for batch_index, position in enumerate(valid_positions):
                    raw[position] = RawPhoneScore(
                        phone=expected_phones[position],
                        score=float(scores[batch_index].clamp(0, 100).cpu()),
                        error_probability=float(probabilities[batch_index].cpu()),
                        gop=round(float(gops[batch_index]), 3),
                    )
            return BackendResult(
                phones=[item for item in raw if item is not None], observed_phones=observed
            )
