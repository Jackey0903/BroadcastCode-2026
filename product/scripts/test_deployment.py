"""Guard formal deployment against stale practice-account configuration, offline."""
import json
from pathlib import Path
import tempfile
import unittest

from deployment import load_deployment, load_outputs, validate_identity


class DeploymentTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'outputs.json'
        self.target = load_deployment()
        self.outputs = {'Bucket': 'new-product-bucket', 'Website': 'https://example.cloudfront.net',
            'Account': self.target['account'], 'Region': self.target['region'],
            'RuntimeArn': f"arn:aws:bedrock-agentcore:us-east-1:{self.target['account']}:runtime/test-runtime"}

    def tearDown(self):
        self.temp.cleanup()

    def save(self):
        self.path.write_text(json.dumps({self.target['stackName']: self.outputs}))

    def test_current_formal_account_outputs_are_accepted(self):
        self.assertEqual(self.target['account'], '555726205424')
        self.save()
        self.assertEqual(load_outputs(self.path, self.target), self.outputs)
        validate_identity({'Account': self.target['account'],
            'Arn': f"arn:aws:sts::{self.target['account']}:assumed-role/NBAHackathonParticipantRole/Team02"}, self.target)

    def test_stale_practice_account_outputs_are_rejected(self):
        self.outputs['RuntimeArn'] = 'arn:aws:bedrock-agentcore:us-east-1:962768510637:runtime/old'
        self.save()
        with self.assertRaisesRegex(ValueError, 'another account'):
            load_outputs(self.path, self.target)

    def test_missing_current_outputs_never_fall_back_to_readiness(self):
        with self.assertRaisesRegex(ValueError, 'old readiness outputs are not reused'):
            load_outputs(self.path, self.target)

    def test_wrong_role_or_account_rejected_before_upload(self):
        for account, role in [('962768510637', 'NBAHackathonParticipantRole'),
                              (self.target['account'], 'AWSReservedSSO_NBAHackathon-Team02')]:
            with self.subTest(account=account, role=role), self.assertRaises(ValueError):
                validate_identity({'Account': account, 'Arn': f'arn:aws:sts::{account}:assumed-role/{role}/Team02'}, self.target)

    def test_resource_region_guard(self):
        target = dict(self.target, region='us-west-2')
        self.path.write_text(json.dumps(target))
        with self.assertRaisesRegex(ValueError, 'us-east-1'):
            load_deployment(self.path)
        self.outputs['RuntimeArn'] = f"arn:aws:bedrock-agentcore:us-west-2:{self.target['account']}:runtime/wrong-region"
        self.save()
        with self.assertRaises(ValueError):
            load_outputs(self.path, self.target)

    def test_conflicting_account_output_is_rejected(self):
        self.outputs['Account'] = '962768510637'
        self.save()
        with self.assertRaisesRegex(ValueError, 'does not match'):
            load_outputs(self.path, self.target)

    def test_unsafe_or_non_cloudfront_site_is_rejected(self):
        for site in ['http://example.cloudfront.net', 'https://example.invalid',
                     'https://user:password@example.cloudfront.net', 'https://example.cloudfront.net/old/path']:
            self.outputs['Website'] = site
            self.save()
            with self.subTest(site=site), self.assertRaises(ValueError):
                load_outputs(self.path, self.target)

    def test_unrelated_stack_output_is_rejected(self):
        self.path.write_text(json.dumps({'OtherStack': self.outputs}))
        with self.assertRaisesRegex(ValueError, 'configured Stack'):
            load_outputs(self.path, self.target)


if __name__ == '__main__':
    unittest.main()
