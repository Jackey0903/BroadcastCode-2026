"""55-second formal edit, with original Flagg intro/outro animation durations."""
from formal.timeline import FPS, SAMPLE_RATE, SOURCE_SHA256, SOURCE_FRAME_COUNT, REPLAY_START, REPLAY_MID, frame_sample


def build_timeline():
    specs = (
        ('intro', 150, 0, 0),
        ('live', 241, 0, 1),
        ('T1', 260, 240, 0),
        ('live', 240, 241, 1),
        ('T3', 270, 480, 0),
        ('live', 239, 481, 1),
        ('T2', 260, 719, 0),
        ('live', 704, 720, 1),
        ('rewind', 54, 1423, (REPLAY_START - 1423) / 53),
        ('replay1', 186, REPLAY_START, .5),
        ('metric', 162, REPLAY_MID, 0),
        ('replay2', 204, REPLAY_MID, .5),
        ('outro', 330, 1423, 0),
    )
    result, at = [], 0
    for name, count, source_start, source_rate in specs:
        result.append(dict(name=name, start=at, count=count, sourceStart=float(source_start), sourceRate=float(source_rate)))
        at += count
    return tuple(result)


SEGMENTS = build_timeline()
FRAME_COUNT = sum(segment['count'] for segment in SEGMENTS)
DURATION = FRAME_COUNT / float(FPS)


def locate_frame(frame):
    if not isinstance(frame, int) or not 0 <= frame < FRAME_COUNT:
        raise ValueError('Invalid output frame')
    for segment in SEGMENTS:
        if segment['start'] <= frame < segment['start'] + segment['count']:
            return segment, frame - segment['start']
    raise AssertionError('Unassigned output frame')
