"""New-source-only broadcast/SFX mix for the formal 45.2 second cut."""
from pathlib import Path
import hashlib
import subprocess
import wave

import numpy as np

try:
    from .timeline import FPS, FRAME_COUNT, SAMPLE_RATE, SEGMENTS, SOURCE_SHA256, frame_sample
except ImportError:  # Direct script execution from the formal directory.
    from timeline import FPS, FRAME_COUNT, SAMPLE_RATE, SEGMENTS, SOURCE_SHA256, frame_sample


def fade(signal, seconds=.025):
    result = np.asarray(signal, dtype=np.float32).copy()
    n = min(round(seconds * SAMPLE_RATE), len(result) // 2)
    if n:
        ramp = np.linspace(0, 1, n, dtype=np.float32)[:, None]
        result[:n] *= ramp
        result[-n:] *= ramp[::-1]
    return result


def fit(signal, count):
    """Align FFmpeg and rational frame rounding without changing segment length."""
    if len(signal) == count:
        return signal.copy()
    if not len(signal):
        return np.zeros((count, 2), np.float32)
    if len(signal) < count:
        return np.pad(signal, ((0, count - len(signal)), (0, 0)))
    return signal[:count].copy()


def sfx(count, name):
    """Deterministic procedural tones; contains no imported media or speech."""
    t = np.arange(count, dtype=np.float64) / SAMPLE_RATE
    duration = count / SAMPLE_RATE
    base = 55 if name in ("intro", "outro") else 62
    signal = .035 * (np.sin(2 * np.pi * base * t) + .35 * np.sin(2 * np.pi * 2 * base * t))
    for onset in (.12, .7, 1.45, 2.2):
        age = np.maximum(t - onset, 0)
        signal += (t >= onset) * .055 * np.sin(2 * np.pi * (145 * age - 55 * age ** 2)) * np.exp(-age * 12)
    if name == "rewind":
        signal += .025 * np.sin(2 * np.pi * (850 * t - 430 * t ** 2))
    envelope = np.clip(t / .08, 0, 1) * np.clip((duration - t) / .18, 0, 1)
    return np.stack((signal * envelope, signal * envelope * .98), axis=1).astype(np.float32)


def decode_source(source):
    result = subprocess.run(["ffmpeg", "-v", "error", "-i", str(source), "-vn",
                             "-f", "f32le", "-ac", "2", "-ar", str(SAMPLE_RATE), "pipe:1"],
                            capture_output=True, check=True)
    return np.frombuffer(result.stdout, dtype="<f4").reshape(-1, 2).copy()


def half_speed(signal):
    result = subprocess.run(["ffmpeg", "-v", "error", "-f", "f32le", "-ac", "2", "-ar", str(SAMPLE_RATE),
                             "-i", "pipe:0", "-af", "atempo=0.5", "-f", "f32le", "-ac", "2",
                             "-ar", str(SAMPLE_RATE), "pipe:1"],
                            input=signal.astype("<f4").tobytes(), capture_output=True, check=True)
    return np.frombuffer(result.stdout, dtype="<f4").reshape(-1, 2).copy()


def assemble_audio(source_audio, slow_audio, segments=SEGMENTS, frame_count=FRAME_COUNT):
    """Place source-contiguous live spans and split a single half-speed replay."""
    result = np.zeros((frame_sample(frame_count), 2), np.float32)
    records, replay_at = [], 0
    for segment in segments:
        start = frame_sample(segment["start"])
        end = frame_sample(segment["start"] + segment["count"])
        count, name = end - start, segment["name"]
        record = {**segment, "outputSample": start, "sampleCount": count}
        if name == "live":
            source_start = frame_sample(round(segment["sourceStart"]))
            source_end = frame_sample(round(segment["sourceStart"]) + segment["count"])
            if source_end > len(source_audio):
                raise ValueError("Source broadcast audio is shorter than the full live source range")
            audio = fade(fit(source_audio[source_start:source_end], count)) * .90
            record.update(sourceSampleStart=source_start, sourceSampleEndExclusive=source_end,
                          audioKind="original-broadcast", gain=.90)
        elif name in ("replay1", "replay2"):
            audio = fade(fit(slow_audio[replay_at:replay_at + count], count), .04) * .48
            record.update(replaySampleStart=replay_at, audioKind="same-source-half-speed-broadcast", gain=.48)
            replay_at += count
            audio += sfx(count, name) * .18
        else:
            audio = sfx(count, name)
            record.update(audioKind="procedural-sfx-no-speech")
        result[start:end] = audio
        records.append(record)
    if not np.isfinite(result).all():
        raise ValueError("Non-finite audio sample")
    peak = float(np.max(np.abs(result)))
    safety_gain = min(1.0, .94 / max(peak, 1e-9))
    result *= safety_gain
    return result, {"segments": records, "peakBeforeSafetyGain": peak,
                    "safetyGain": safety_gain, "peak": float(np.max(np.abs(result)))}


def build_audio(source, output, segments=SEGMENTS, frame_count=FRAME_COUNT):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output:
        raise ValueError("Output must not overwrite the source")
    with source.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != SOURCE_SHA256:
        raise ValueError("Formal source SHA-256 mismatch; old or unrelated media is not accepted")
    original = decode_source(source)
    # One continuous 12.0..15.253s excerpt is slowed once, then split around the
    # metric freeze. This avoids processing a replay boundary twice.
    start = round(12.0 * SAMPLE_RATE)
    end = round((12.0 + 195 / float(FPS)) * SAMPLE_RATE)
    slow = half_speed(original[start:end])
    audio, metadata = assemble_audio(original, slow, segments, frame_count)
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as stream:
        stream.setnchannels(2)
        stream.setsampwidth(2)
        stream.setframerate(SAMPLE_RATE)
        stream.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
    with output.open("rb") as stream:
        output_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    return {**metadata, "sourceSha256": digest, "outputSha256": output_hash,
            "source": str(source), "output": str(output), "sampleRate": SAMPLE_RATE,
            "channels": 2, "samples": len(audio), "sampleCount": len(audio),
            "durationSeconds": len(audio) / SAMPLE_RATE,
            "speech": "Original formal-source broadcast only; no new TTS or AI voiceover",
            "mediaInputs": [str(source)], "legacyMediaUsed": False}
