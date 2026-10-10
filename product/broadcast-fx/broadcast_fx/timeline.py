"""Frame-exact extension of the preserved 37.7 second editorial cut.

All frame ranges are zero-based and half-open. The live source range is
preserved once, in order; tactical inserts hold a single observed source frame.
"""
from dataclasses import dataclass
from fractions import Fraction

FPS = Fraction(60000, 1001)
SAMPLE_RATE = 48000
LEGACY_SEGMENTS = (
    ("intro", 150), ("live", 1110), ("rewind", 54),
    ("slow1", 324), ("freeze", 130), ("slow2", 163), ("outro", 330),
)
LEGACY_FRAME_COUNT = sum(n for _, n in LEGACY_SEGMENTS)
INSERT_FRAME_COUNT = 220
LIVE_SOURCE_START = 6
INSERT_AFTER_SOURCE = ((500, "T1"), (920, "T2"))


def frame_sample(frame: int, sample_rate: int = SAMPLE_RATE) -> int:
    """Nearest PCM sample at a rational frame boundary (no float drift)."""
    value = Fraction(frame * sample_rate, 1) / FPS
    return (value.numerator * 2 + value.denominator) // (2 * value.denominator)


@dataclass(frozen=True)
class Segment:
    name: str
    start: int
    count: int
    legacy_start: int | None
    local_start: int = 0
    legacy_count: int | None = None
    held_source_frame: int | None = None

    @property
    def end(self) -> int:
        return self.start + self.count

    def as_dict(self) -> dict:
        return {
            "name": self.name, "startFrame": self.start, "endFrameExclusive": self.end,
            "frameCount": self.count, "startSeconds": float(self.start / FPS),
            "durationSeconds": float(self.count / FPS), "legacyStartFrame": self.legacy_start,
            "legacyLocalStart": self.local_start, "heldSourceFrame": self.held_source_frame,
            "sourceFrameStart": LIVE_SOURCE_START + self.local_start if self.name == "live" else None,
            "sourceFrameEndExclusive": LIVE_SOURCE_START + self.local_start + self.count if self.name == "live" else None,
        }


def build_timeline() -> tuple[Segment, ...]:
    timeline, output_at, legacy_at = [], 0, 0
    for name, count in LEGACY_SEGMENTS:
        if name == "live":
            local_at = 0
            for source_frame, insert_name in INSERT_AFTER_SOURCE:
                boundary = source_frame - LIVE_SOURCE_START + 1
                run_count = boundary - local_at
                timeline.append(Segment(name, output_at, run_count, legacy_at + local_at, local_at, count))
                output_at += run_count
                timeline.append(Segment(insert_name, output_at, INSERT_FRAME_COUNT, None,
                                        held_source_frame=source_frame))
                output_at += INSERT_FRAME_COUNT
                local_at = boundary
            timeline.append(Segment(name, output_at, count - local_at, legacy_at + local_at, local_at, count))
            output_at += count - local_at
        else:
            timeline.append(Segment(name, output_at, count, legacy_at, legacy_count=count))
            output_at += count
        legacy_at += count
    return tuple(timeline)


TIMELINE = build_timeline()
FRAME_COUNT = TIMELINE[-1].end
DURATION = Fraction(FRAME_COUNT, 1) / FPS


def locate_frame(frame: int) -> tuple[Segment, int]:
    if not 0 <= frame < FRAME_COUNT:
        raise ValueError(f"Frame must be in [0, {FRAME_COUNT}), got {frame}")
    for segment in TIMELINE:
        if segment.start <= frame < segment.end:
            return segment, frame - segment.start
    raise AssertionError("Timeline has an unassigned frame")


def audio_insertions() -> list[dict]:
    """Locations in both old and new timelines for interruption-safe splicing."""
    result, inserted = [], 0
    for segment in TIMELINE:
        if segment.legacy_start is None:
            result.append({"name": segment.name, "legacyFrame": segment.start - inserted,
                           "outputFrame": segment.start, "frameCount": segment.count})
            inserted += segment.count
    return result
