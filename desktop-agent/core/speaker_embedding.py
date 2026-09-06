from __future__ import annotations

"""
Speaker embedding extraction for wake-word authentication (spec section 8).

HONEST SCOPE NOTE: this is a lightweight, dependency-free (numpy only)
MFCC-statistics embedding — mean+std of 13 MFCC coefficients across the
utterance, L2-normalized into a 26-dim vector, compared by cosine
similarity. It is real, working, on-device speaker discrimination, not a
placeholder. It is also NOT a deep neural speaker embedding (ECAPA-TDNN,
resemblyzer, etc.) — it will separate clearly different voices well with
a sensibly chosen threshold, but it's more easily fooled by a similar-
sounding voice than a production biometric model would be, and it has no
liveness detection (a recording of the enrolled user's voice would pass).
get_embedding() is the single seam a stronger provider would replace —
nothing else in speaker_verification.py or voice.py needs to change to
swap it out later, mirroring how backend/app/services/voice_providers
already isolates the TTS-cloning provider choice.

No external dependency (librosa/scipy) is required — MFCC extraction is
implemented directly against numpy's FFT so this runs anywhere the agent
already runs, fully offline.
"""

import numpy as np

EMBEDDING_DIM = 26  # 13 MFCC coefficients x (mean, std) — must match backend/app/models/speaker_profile.py
SAMPLE_RATE = 16000
N_MFCC = 13
N_MELS = 26
FRAME_LENGTH = 400  # 25ms at 16kHz
FRAME_STEP = 160  # 10ms at 16kHz
N_FFT = 512
PRE_EMPHASIS = 0.97


def _hz_to_mel(hz: np.ndarray) -> np.ndarray:
    return 2595.0 * np.log10(1.0 + hz / 700.0)


def _mel_to_hz(mel: np.ndarray) -> np.ndarray:
    return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)


def _mel_filterbank(sample_rate: int, n_fft: int, n_mels: int) -> np.ndarray:
    low_mel, high_mel = 0.0, _hz_to_mel(np.array(sample_rate / 2.0))
    mel_points = np.linspace(low_mel, high_mel, n_mels + 2)
    hz_points = _mel_to_hz(mel_points)
    bins = np.floor((n_fft + 1) * hz_points / sample_rate).astype(int)

    filters = np.zeros((n_mels, n_fft // 2 + 1))
    for m in range(1, n_mels + 1):
        left, center, right = bins[m - 1], bins[m], bins[m + 1]
        for k in range(left, center):
            if center > left:
                filters[m - 1, k] = (k - left) / (center - left)
        for k in range(center, right):
            if right > center:
                filters[m - 1, k] = (right - k) / (right - center)
    return filters


def _dct_matrix(n_out: int, n_in: int) -> np.ndarray:
    """DCT-II basis, computed directly so no scipy dependency is needed."""
    n = np.arange(n_in)
    k = np.arange(n_out).reshape(-1, 1)
    basis = np.cos(np.pi / n_in * (n + 0.5) * k)
    basis[0] *= 1.0 / np.sqrt(2.0)
    return basis * np.sqrt(2.0 / n_in)


_MEL_FILTERS = _mel_filterbank(SAMPLE_RATE, N_FFT, N_MELS)
_DCT = _dct_matrix(N_MFCC, N_MELS)
_WINDOW = np.hamming(FRAME_LENGTH)


def _to_float(pcm_int16: np.ndarray) -> np.ndarray:
    return pcm_int16.astype(np.float32) / 32768.0


def _compute_mfcc(signal: np.ndarray) -> np.ndarray:
    """Returns an (n_frames, N_MFCC) matrix. Pure numpy: pre-emphasis ->
    framing -> Hamming window -> power spectrum (rfft) -> mel filterbank ->
    log -> DCT-II. Standard MFCC pipeline, just written out by hand."""
    emphasized = np.append(signal[0], signal[1:] - PRE_EMPHASIS * signal[:-1])

    n_frames = 1 + max(0, (len(emphasized) - FRAME_LENGTH) // FRAME_STEP)
    if n_frames < 1:
        pad = FRAME_LENGTH - len(emphasized)
        emphasized = np.pad(emphasized, (0, pad))
        n_frames = 1

    frames = np.stack(
        [emphasized[i * FRAME_STEP : i * FRAME_STEP + FRAME_LENGTH] for i in range(n_frames)]
    )
    frames = frames * _WINDOW

    spectrum = np.fft.rfft(frames, n=N_FFT)
    power = (np.abs(spectrum) ** 2) / N_FFT

    mel_energy = power @ _MEL_FILTERS.T
    mel_energy = np.maximum(mel_energy, 1e-10)  # avoid log(0)
    log_mel = np.log(mel_energy)

    mfcc = log_mel @ _DCT.T
    return mfcc


def get_embedding(pcm_int16: np.ndarray) -> np.ndarray:
    """
    pcm_int16: mono 16kHz int16 samples (exactly what VoiceListener already
    records for wake-word STT — this is run against that SAME buffer, no
    extra recording, which is what keeps verification from adding latency
    before Nova can act on a command).

    Returns an L2-normalized EMBEDDING_DIM-length float32 vector, or None
    if the buffer is too quiet/short to extract anything meaningful from
    (silence would otherwise produce a degenerate, near-random embedding).
    """
    signal = _to_float(pcm_int16)

    if np.sqrt(np.mean(signal**2)) < 1e-4:  # effectively silence
        return None

    mfcc = _compute_mfcc(signal)
    if mfcc.shape[0] < 2:
        return None

    features = np.concatenate([mfcc.mean(axis=0), mfcc.std(axis=0)])  # -> 26-dim
    norm = np.linalg.norm(features)
    if norm < 1e-9:
        return None
    return (features / norm).astype(np.float32)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    a_arr, b_arr = np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)
    denom = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
    if denom < 1e-9:
        return 0.0
    return float(np.dot(a_arr, b_arr) / denom)
