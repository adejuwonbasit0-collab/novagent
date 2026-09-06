from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.api_client import APIError, NovaAPIClient
from core.device_store import DeviceStore
from core.speaker_embedding import EMBEDDING_DIM, cosine_similarity, get_embedding

DEFAULT_THRESHOLD = 0.90  # mirrors backend/app/models/speaker_profile.py's default — see that file's comment for calibration basis


@dataclass
class VerificationResult:
    verified: bool
    score: float | None  # None when there's no enrolled template to compare against
    reason: str


class SpeakerVerifier:
    """
    Owns the locally-cached template (embedding + threshold + enabled)
    and answers "does this audio buffer sound like the enrolled user"
    with zero network calls — the gate has to be fast and offline-capable
    (spec sections 8 and 38), since it runs on every single wake event.

    The template itself is synced from the backend (source of truth, so a
    second device or a dashboard "reset voice profile" action stays
    consistent) but verification never needs the network once a template
    is cached — see verify().
    """

    def __init__(self):
        self._embedding: list[float] | None = None
        self._threshold: float = DEFAULT_THRESHOLD
        self._enabled: bool = True
        self._load_local()

    def _load_local(self) -> None:
        cached = DeviceStore.get_speaker_template()
        if cached:
            self._embedding = cached.get("embedding")
            self._threshold = cached.get("threshold", DEFAULT_THRESHOLD)
            self._enabled = cached.get("enabled", True)

    @property
    def is_enrolled(self) -> bool:
        return self._embedding is not None

    @property
    def is_gate_active(self) -> bool:
        """False means every wake event passes through unverified — either
        the user explicitly disabled verification, or they've never
        enrolled. Both cases behave identically at the gate; only the
        dashboard/UI needs to distinguish "disabled" from "not set up"."""
        return self._enabled and self.is_enrolled

    async def sync_from_backend(self, client: NovaAPIClient) -> None:
        """Pulls the current template from the backend and caches it
        locally. Call this at agent startup and right after (re)enrolling
        elsewhere (e.g. from the web dashboard) so this device picks up
        the change without waiting for its own next enrollment."""
        try:
            data = await client.get_speaker_template()
        except APIError:
            return  # offline or backend down — keep using whatever's cached locally
        self._embedding = data.get("embedding")
        self._threshold = data.get("threshold", DEFAULT_THRESHOLD)
        self._enabled = data.get("enabled", True)
        DeviceStore.save_speaker_template(self._embedding, self._threshold, self._enabled)

    async def enroll(self, recordings: list[np.ndarray], client: NovaAPIClient) -> tuple[bool, str]:
        """
        recordings: several int16 PCM buffers of the user speaking (spec
        section 9 — "record multiple samples," not one). Embeddings are
        computed here, on-device; only the resulting vectors are sent to
        the backend — the audio itself never leaves this machine.
        """
        embeddings = [get_embedding(r) for r in recordings]
        usable = [e for e in embeddings if e is not None]

        if len(usable) < 3:
            return False, (
                f"Only {len(usable)} of {len(recordings)} recordings had enough clear speech to use. "
                "Try again somewhere quieter, or speak a bit longer in each sample."
            )

        try:
            data = await client.enroll_speaker([e.tolist() for e in usable])
        except APIError as e:
            return False, f"Could not save your voice profile: {e.detail}"

        self._embedding = data.get("embedding")  # enroll response doesn't include it; refreshed below
        await self.sync_from_backend(client)
        return True, f"Voice profile trained from {len(usable)} sample(s)."

    def verify(self, pcm_int16: np.ndarray) -> VerificationResult:
        """
        Runs against the SAME buffer VoiceListener already recorded to
        detect the wake phrase — no extra recording round, so there's no
        added latency between "Hey Nova" and Nova actually responding.
        """
        if not self.is_gate_active:
            return VerificationResult(verified=True, score=None, reason="verification_disabled")

        embedding = get_embedding(pcm_int16)
        if embedding is None:
            return VerificationResult(verified=False, score=None, reason="no_clear_speech")

        template = np.asarray(self._embedding, dtype=np.float32)
        if template.shape[0] != EMBEDDING_DIM:
            return VerificationResult(verified=False, score=None, reason="template_invalid")

        score = cosine_similarity(embedding, template)
        return VerificationResult(verified=score >= self._threshold, score=score, reason="match" if score >= self._threshold else "no_match")
