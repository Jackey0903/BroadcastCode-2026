"""Bounded, fail-soft bridge to the separately trained evidence selector.

Only the frozen modules/data are deployed. Training code and credentials are not
packaged. Raw model receipts live in S3, separately from compact job records.
"""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import copy
import json
from pathlib import Path
import sys
import time

PRESENTATION_FIELDS = ('scout', 'playerComparison', 'sources', 'periods', 'videoUse')


def live_selection(sample):
    import boto3
    from botocore.config import Config
    directory = Path(__file__).resolve().parent / 'rl'
    if not directory.is_dir():
        directory = Path(__file__).resolve().parents[1] / 'rl'
    sys.path.insert(0, str(directory))
    from product_bridge import create_bridge
    runtime = boto3.client('sagemaker-runtime', region_name='us-east-1',
        config=Config(connect_timeout=20, read_timeout=25, retries={'total_max_attempts': 1}))
    # These are verified same-game roster choices, not identified defenders.
    opponent = {'flagg': '1641708', 'amen': '1631108'}[sample]
    return create_bridge(runtime).analyse(sample, focus='spacing', opponent_id=opponent)


def start_selection(sample, enabled, runner=None):
    if not enabled or sample not in ('flagg', 'amen'):
        return None
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='rl-evidence')
    return pool, pool.submit(runner or live_selection, sample), time.monotonic()


def collect_selection(pending, story, timeout_seconds=90):
    if pending is None:
        return None
    pool, future, started = pending
    try:
        value = future.result(timeout=max(0, timeout_seconds - (time.monotonic() - started)))
        presentation = value['presentation']
        scout = presentation['scout']
        if not (scout.get('available') is True and scout.get('trainedModelUsed') is True
                and scout.get('selectionVerified') is True and scout.get('lineageVerified') is True
                and scout.get('actualRL') is True and scout.get('modelInvokedThisRequest') is True
                and scout.get('invocationMode') == 'live'):
            raise ValueError('No verified live model selection')
        official = story['officialEvent']
        if (str(presentation.get('gameId')) != str(official['gameId'])
                or str(presentation.get('eventId')) != str(official['eventId'])
                or str(presentation.get('playerId')) != str(official['playerId'])):
            raise ValueError('RL evidence identity differs from registered video event')
        if len(json.dumps(presentation, ensure_ascii=False, separators=(',', ':')).encode()) > 48000:
            raise ValueError('Compact RL presentation exceeds limit')
        return value
    except Exception as error:
        # Error payloads can contain model inputs; expose only the exception type.
        return {'presentation': {'scout': {'available': False, 'trainedModelUsed': False,
                    'modelInvokedThisRequest': False, 'badge': '', 'errorType': type(error).__name__},
                    'videoUse': {'narrativeUsed': False, 'burnedIntoVideo': False, 'evidenceIdsUsed': []}},
                'audit': {'status': 'not_accepted', 'errorType': type(error).__name__,
                          'timeoutDoesNotCancelNetworkRequest': isinstance(error, TimeoutError)}}
    finally:
        # A timeout is a result-acceptance limit, not a cancellation claim.
        pool.shutdown(wait=False)


def narrative_input(presentation):
    scout = presentation.get('scout', {})
    if scout.get('available') is not True:
        return None
    flags = ('available', 'trainedModelUsed', 'selectionVerified', 'lineageVerified', 'actualRL',
             'modelInvoked', 'modelInvokedThisRequest', 'threeLayersCovered', 'invocationMode')
    return {'scout': {**{key: scout.get(key) for key in flags}, 'evidence': copy.deepcopy(scout['evidence'])},
            'sources': copy.deepcopy(presentation['sources']), 'periods': copy.deepcopy(presentation['periods']),
            'playerComparison': {'comparisons': copy.deepcopy(
                presentation.get('playerComparison', {}).get('comparisons', [])[:2])}}


def analysis_fields(presentation, render_receipt=None):
    result = {'scout': copy.deepcopy(presentation['scout']),
              'rlVideoUse': copy.deepcopy(presentation['videoUse'])}
    for source, destination in (('playerComparison', 'playerComparison'),
                                ('sources', 'rlEvidenceSources'), ('periods', 'rlEvidencePeriods')):
        if source in presentation:
            result[destination] = copy.deepcopy(presentation[source])
    if render_receipt and render_receipt.get('prepared') is True:
        result['rlVideoUse'] = {**render_receipt, 'narrativeUsed': True, 'burnedIntoVideo': True,
                                'evidenceIdsUsed': list(render_receipt['evidenceIds']),
                                'verification': 'worker_ffmpeg_success_and_full_media_contract'}
    return result
