"""Explicit public assets of the merged desktop watch frontend.

Shared by local preview and verified publication. Tests, arbitrary reference images,
configuration tools, Python servers and arbitrary repository files stay private.
The catalog is generated from the current validated product manifest separately.
"""

WATCH_PUBLIC_FILES = (
    'companions/game-buddy/game-buddy-embed.js',
    'companions/game-buddy/sprite-atlas.js',
    'companions/game-buddy/assets/game-buddy-crt.webp',
    'assets/teams/dallas-mavericks.svg',
    'assets/teams/houston-rockets.svg',
    'index.html',
    'app.js',
    'adapters/catalog.js',
    'adapters/historical-records.js',
    'annotations/annotations.css',
    'annotations/annotations.js',
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
