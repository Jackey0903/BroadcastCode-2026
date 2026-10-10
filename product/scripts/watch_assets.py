"""Explicit public assets of the merged desktop watch frontend.

Shared by local preview and verified publication. Tests, arbitrary reference images,
configuration tools, Python servers and arbitrary repository files stay private.
The catalog is generated from the current validated product manifest separately.
"""

WATCH_PUBLIC_FILES = (
    'index.html',
    'app.js',
    'adapters/catalog.js',
    'adapters/historical-records.js',
    'annotations/annotations.css',
    'annotations/annotations.js',
    'annotations/mascot.js',
    'config/config.js',
    'content/content-panel.js',
    'content/content.css',
    'court/court-geometry.js',
    'court/court-panel.js',
    'court/court.css',
    'court/themes.js',
    'data/flagg.json',
    'dev/inspector.css',
    'dev/inspector.js',
    'dev/references/01_immersive.png',
    'dev/references/02_full_court.png',
    'dev/references/03_half_court.png',
    'glass/ambience-source.js',
    'glass/glass-manager.js',
    'glass/optics-model.js',
    'media/media.css',
    'media/player-controls.js',
    'navigation/drawer.js',
    'stage/layout.js',
    'stage/stage.css',
    'vendor/court-viewer.js',
    'vendor/liquid-gl/liquidGL.js',
    'vendor/liquid-gl/liquidGL-helper.js',
    'vendor/liquid-gl/LICENSE',
)


def watch_history_record(report):
    """Copy report facts without inventing content or browser acceptance."""
    import copy
    fields = ('jobId', 'sample', 'mode', 'verifiedAt', 'durationSeconds', 'width',
              'height', 'audioPresent', 'browserPlaybackVerified', 'elapsedSeconds',
              'outputSha256', 'contentReview', 'analysis')
    record = {key: copy.deepcopy(report[key]) for key in fields if key in report}
    record['recordSource'] = f"product/evidence/run-{report['jobId']}.json"
    return record
