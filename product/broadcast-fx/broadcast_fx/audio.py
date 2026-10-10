"""Preserve broadcast/SFX alignment while adding two quiet tactical interludes.

No speech is synthesized here. The existing mix contains source broadcast audio
and procedural sound effects, not a new AI voiceover.
"""
from pathlib import Path
import subprocess
import sys
import wave

import numpy as np

from .timeline import FPS, FRAME_COUNT, LEGACY_FRAME_COUNT, SAMPLE_RATE, audio_insertions, frame_sample


def fade_edges(signal: np.ndarray, fade_in: bool = True, fade_out: bool = True,
               milliseconds: float = 10) -> np.ndarray:
    result = np.asarray(signal, dtype=np.float32).copy()
    length = min(round(milliseconds * SAMPLE_RATE / 1000), len(result) // 2)
    if length:
        ramp = np.linspace(0, 1, length, dtype=np.float32)[:, None]
        if fade_in:
            result[:length] *= ramp
        if fade_out:
            result[-length:] *= ramp[::-1]
    return result


def tactical_sfx(samples: int, index: int = 0) -> np.ndarray:
    """Deterministic low pulse / scan sound, deliberately below the live mix."""
    time = np.arange(samples, dtype=np.float64) / SAMPLE_RATE
    duration = samples / SAMPLE_RATE
    bass = 57 + index * 7
    signal = .052 * np.sin(2 * np.pi * bass * time)
    signal += .023 * np.sin(2 * np.pi * bass * 2 * time)
    signal *= .62 + .38 * np.sin(2 * np.pi * .65 * time) ** 2
    for beat in (.08, .68, 1.38, 2.12, 2.84):
        age = np.maximum(time - beat, 0)
        signal += (time >= beat) * .074 * np.sin(2 * np.pi * 138 * age) * np.exp(-age * 14)
    # A quiet tonal scan avoids abrasive noise or an accidental spoken cue.
    scan_phase = 2 * np.pi * (420 * time + 70 * time ** 2)
    signal += .008 * np.sin(scan_phase) * np.sin(np.pi * time / max(duration, .001)) ** 2
    envelope = np.minimum(time / .12, 1) * np.minimum((duration - time) / .28, 1)
    signal *= np.clip(envelope, 0, 1)
    stereo = np.stack((signal, signal * .98), axis=1).astype(np.float32)
    return fade_edges(stereo)


def splice_audio(original: np.ndarray) -> tuple[np.ndarray, dict]:
    if original.ndim != 2 or original.shape[1] != 2:
        raise ValueError("Expected a stereo audio array")
    expected_original = frame_sample(LEGACY_FRAME_COUNT)
    # Legacy rendering rounded down by one sample. Larger truncation is an error.
    missing = expected_original - len(original)
    if missing > 2:
        raise ValueError(f"Legacy audio is truncated by {missing} samples")
    if missing > 0:
        original = np.pad(original, ((0, missing), (0, 0)))
    original = original[:expected_original]
    parts, previous, insert_records = [], 0, []
    for index, insertion in enumerate(audio_insertions()):
        boundary = frame_sample(insertion["legacyFrame"])
        parts.append(fade_edges(original[previous:boundary], fade_in=previous > 0))
        start = frame_sample(insertion["outputFrame"])
        end = frame_sample(insertion["outputFrame"] + insertion["frameCount"])
        parts.append(tactical_sfx(end - start, index))
        insert_records.append({**insertion, "legacySample": boundary,
                               "outputSample": start, "sampleCount": end - start})
        previous = boundary
    parts.append(fade_edges(original[previous:], fade_out=True))
    result = np.concatenate(parts)
    expected = frame_sample(FRAME_COUNT)
    if len(result) != expected:
        raise ValueError(f"Audio timeline mismatch: {len(result)} vs {expected} samples")
    if not np.isfinite(result).all():
        raise ValueError("Audio contains non-finite samples")
    peak = float(np.abs(result).max())
    if peak > .95:
        result *= .95 / peak
    return result, {"sampleRate": SAMPLE_RATE, "channels": 2, "sampleCount": expected,
                    "peakBeforeSafetyGain": peak, "peak": float(np.abs(result).max()),
                    "legacyPaddingSamples": max(missing, 0), "insertions": insert_records,
                    "speech": "Preserved source broadcast; no new TTS or AI voiceover"}


def read_pcm(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as stream:
        if (stream.getframerate(), stream.getnchannels(), stream.getsampwidth()) != (SAMPLE_RATE, 2, 2):
            raise ValueError("Legacy WAV must be 48 kHz, stereo, signed 16-bit PCM")
        return np.frombuffer(stream.readframes(stream.getnframes()), dtype="<i2").reshape(-1, 2).astype(np.float32) / 32768


def build_audio(workdir: Path, source: Path, output: Path) -> dict:
    legacy = workdir / "out" / "audio.wav"
    if not legacy.is_file():
        generator = Path(__file__).resolve().parents[1] / "legacy_audio.py"
        if not generator.is_file():
            raise FileNotFoundError(f"Missing legacy audio mix and generator: {legacy}")
        legacy.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, str(generator), str(workdir), str(source)], check=True)
    audio, metadata = splice_audio(read_pcm(legacy))
    output.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    with wave.open(str(output), "wb") as stream:
        stream.setnchannels(2)
        stream.setsampwidth(2)
        stream.setframerate(SAMPLE_RATE)
        stream.writeframes(pcm.tobytes())
    return {**metadata, "legacyAudio": str(legacy), "output": str(output)}
