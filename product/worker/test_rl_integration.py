"""Offline integration-boundary tests; service fixtures are not new cloud calls."""
import copy
import json
from pathlib import Path
import unittest
from rl_integration import start_selection, collect_selection, narrative_input, analysis_fields

PRODUCT = Path(__file__).resolve().parents[1]


def payload():
    return json.loads((PRODUCT / 'rl/results/product-integration/flagg-live-20261010.json').read_text())


class RLIntegrationTests(unittest.TestCase):
    def collect(self, value=None, story=None, runner=None):
        value = payload() if value is None else value
        story = story or {'officialEvent': {key: value[key] for key in ('gameId', 'eventId', 'playerId')}}
        task = start_selection('flagg', True, runner or (lambda sample: {'presentation': value, 'audit': {'test': True}}))
        return collect_selection(task, story)

    def test_live_receipt_enters_narrative_without_full_profiles_or_raw_audit(self):
        result = self.collect()
        request = narrative_input(result['presentation'])
        self.assertTrue(request['scout']['threeLayersCovered'])
        self.assertTrue(request['scout']['modelInvoked'])
        self.assertEqual(len(request['scout']['evidence']), 3)
        self.assertLessEqual(len(request['playerComparison']['comparisons']), 2)
        self.assertNotIn('attacker', request['playerComparison'])
        self.assertNotIn('audit', request)

    def test_wrong_event_and_recorded_receipt_fail_soft_with_no_badge(self):
        wrong = {'officialEvent': {'gameId': 'other', 'eventId': 'other', 'playerId': 'other'}}
        for result in (self.collect(story=wrong), self.collect(value={**payload(), 'scout': {**payload()['scout'], 'invocationMode': 'recorded_live_replay'}})):
            self.assertFalse(result['presentation']['scout']['available'])
            self.assertEqual(result['presentation']['scout']['badge'], '')
            self.assertIsNone(narrative_input(result['presentation']))

    def test_exception_does_not_expose_model_payload_and_unsupported_input_does_not_call(self):
        def fail(sample): raise RuntimeError('sensitive model payload')
        result = self.collect(runner=fail)
        self.assertNotIn('sensitive', json.dumps(result))
        self.assertIsNone(start_selection('unknown', True, fail))
        self.assertIsNone(start_selection('flagg', False, fail))

    def test_selection_alone_does_not_claim_burned_video(self):
        presentation = payload()
        fields = analysis_fields(presentation)
        self.assertFalse(fields['rlVideoUse']['burnedIntoVideo'])
        receipt = {'prepared': True, 'evidenceIds': [row['evidenceId'] for row in presentation['scout']['evidence']]}
        used = analysis_fields(presentation, receipt)
        self.assertTrue(used['rlVideoUse']['burnedIntoVideo'])
        self.assertEqual(used['rlVideoUse']['evidenceIdsUsed'], receipt['evidenceIds'])
        self.assertEqual(fields['playerComparison']['trainedModelUsed'], False)

if __name__ == '__main__': unittest.main()

class RLWorkerChainTests(unittest.TestCase):
    def test_verified_live_selection_reaches_agent_and_successful_render_usage(self):
        from test_rl_story import rl_fixture
        from test_story import execute, FakeS3
        from test_product_worker import FakeRuntime, FakeTable, CONFIG, fake_inspector
        from handler import run_story_job
        request, plan = rl_fixture()
        result, _, _ = execute(request=request, plan=plan)
        presentation = {**request['rlEvidence'], **request['story']['officialEvent'],
            'videoUse': {'narrativeUsed': False, 'burnedIntoVideo': False, 'evidenceIdsUsed': []}}
        runtime, s3, table = FakeRuntime(result), FakeS3(request), FakeTable()
        def renderer(source, output, actual, context):
            self.assertEqual(actual['rlEvidence']['scout']['evidence'], request['rlEvidence']['scout']['evidence'])
            output.write_bytes(b'offline-enhanced-video-fixture')
            return {'prepared': True, 'evidenceIds': actual['plan']['rlEvidenceIds']}
        status = run_story_job({'jobId': 'job-1', 'sample': 'flagg', 'mode': 'story'}, s3, table, runtime,
            {**CONFIG, 'enableRL': True}, renderer=renderer, inspector=fake_inspector,
            rl_runner=lambda sample: {'presentation': presentation, 'audit': {'explicitOfflineDouble': True}})
        self.assertEqual(status['status'], 'completed')
        self.assertEqual(table.item['analysis']['rlVideoUse']['evidenceIdsUsed'], plan['rlEvidenceIds'])
        self.assertTrue(table.item['analysis']['rlVideoUse']['burnedIntoVideo'])
        self.assertIn('product/outputs/job-1/rl-audit.json', s3.objects)
        self.assertEqual(float(table.item['analysis']['plan']['metrics'][0]['rawValue']), .51)
