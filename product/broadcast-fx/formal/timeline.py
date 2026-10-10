"""Independent frame-exact edit for the formal Christie source.

sourceStart is measured in source frames; sourceRate advances source frames
per output frame. Frame ranges are zero-based and half-open.
"""
from fractions import Fraction

FPS = Fraction(60000, 1001)
SAMPLE_RATE = 48000
SOURCE_SHA256 = "f2c0fb6aa1ec10bd78ea9e6724190b7f03bf48f21af2f743c694bbdb49254c91"
SOURCE_FRAME_COUNT = 1424
REPLAY_START = Fraction(12) * FPS
REPLAY_MID = REPLAY_START + 93


def frame_sample(frame, sample_rate=SAMPLE_RATE):
    value = Fraction(frame) * sample_rate / FPS
    return (2 * value.numerator + value.denominator) // (2 * value.denominator)


def build_timeline():
    specs = (
        ("intro", 120, 0, 0),
        ("live", 241, 0, 1),
        ("T1", 210, 240, 0),
        ("live", 479, 241, 1),
        ("T2", 210, 719, 0),
        ("live", 704, 720, 1),
        ("rewind", 36, 1423, (REPLAY_START - 1423) / 35),
        ("replay1", 186, REPLAY_START, Fraction(1, 2)),
        ("metric", 110, REPLAY_MID, 0),
        ("replay2", 204, REPLAY_MID, Fraction(1, 2)),
        ("outro", 210, 1423, 0),
    )
    result, at = [], 0
    for name, count, source_start, source_rate in specs:
        result.append({"name": name, "start": at, "count": count,
                       "sourceStart": float(source_start), "sourceRate": float(source_rate)})
        at += count
    return tuple(result)


SEGMENTS = build_timeline()
FRAME_COUNT = sum(segment["count"] for segment in SEGMENTS)
DURATION = Fraction(FRAME_COUNT, 1) / FPS
TOTAL_FRAMES = FRAME_COUNT
TOTAL_SECONDS = float(DURATION)


def locate_frame(frame):
    if not isinstance(frame, int) or not 0 <= frame < FRAME_COUNT:
        raise ValueError(f"Output frame must be an integer in [0,{FRAME_COUNT})")
    for segment in SEGMENTS:
        if segment["start"] <= frame < segment["start"] + segment["count"]:
            return segment, frame - segment["start"]
    raise AssertionError("Unassigned output frame")


def source_frame_at(frame):
    segment, local = locate_frame(frame)
    return segment["sourceStart"] + local * segment["sourceRate"]
