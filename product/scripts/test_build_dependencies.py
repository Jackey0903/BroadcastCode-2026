"""Offline tests for SDK reproducibility; never run build or touch its assets."""
from importlib import metadata
from pathlib import Path
import tempfile
import unittest

from build_dependencies import BuildDependencyError, read_pins, verify_dependencies

AUDITED = {'boto3': '1.43.108', 'botocore': '1.43.108', 's3transfer': '0.19.2',
           'jmespath': '1.1.0', 'python-dateutil': '2.9.0.post0',
           'urllib3': '2.8.0', 'six': '1.17.0'}


class BuildDependenciesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.requirements = Path(self.temp.name) / 'requirements.txt'
        self.text = '# audited test pins\n' + ''.join(f'{name}=={version}\n' for name, version in AUDITED.items())
        self.requirements.write_text(self.text, encoding='utf-8')

    def tearDown(self):
        self.temp.cleanup()

    def test_checked_in_requirements_match_all_seven_actual_audited_versions(self):
        path = Path(__file__).resolve().parents[1] / 'agent/requirements.txt'
        self.assertEqual(read_pins(path), AUDITED)

    def test_all_seven_exact_installed_versions_pass(self):
        queried = []
        def lookup(name):
            queried.append(name)
            return AUDITED[name]
        self.assertEqual(verify_dependencies(self.requirements, version_lookup=lookup), AUDITED)
        self.assertEqual(queried, list(AUDITED))

    def test_each_missing_distribution_is_rejected_with_install_instruction(self):
        for missing in AUDITED:
            def lookup(name):
                if name == missing:
                    raise metadata.PackageNotFoundError(name)
                return AUDITED[name]
            with self.subTest(distribution=missing), self.assertRaisesRegex(BuildDependencyError, 'Missing SDK distribution: ' + missing) as caught:
                verify_dependencies(self.requirements, version_lookup=lookup)
            self.assertIn('-r product/agent/requirements.txt', str(caught.exception))

    def test_each_mismatched_distribution_is_rejected(self):
        for mismatch in AUDITED:
            def lookup(name):
                return '0.0.0' if name == mismatch else AUDITED[name]
            with self.subTest(distribution=mismatch), self.assertRaisesRegex(BuildDependencyError, 'SDK version mismatch: ' + mismatch):
                verify_dependencies(self.requirements, version_lookup=lookup)

    def test_incomplete_duplicate_extra_or_unpinned_lock_is_rejected_before_lookup(self):
        variants = [self.text.replace('six==1.17.0\n', ''), self.text + 'six==1.17.0\n',
                    self.text + 'unreviewed==1.0\n', self.text.replace('six==1.17.0', 'six>=1.17.0')]
        for text in variants:
            self.requirements.write_text(text, encoding='utf-8')
            def never_lookup(name):
                self.fail('Invalid requirements must fail before querying installed versions')
            with self.subTest(text=text), self.assertRaises(BuildDependencyError):
                verify_dependencies(self.requirements, version_lookup=never_lookup)

    def test_unreadable_requirements_are_rejected(self):
        self.requirements.unlink()
        with self.assertRaisesRegex(BuildDependencyError, 'Cannot read'):
            verify_dependencies(self.requirements, version_lookup=AUDITED.get)


if __name__ == '__main__':
    unittest.main()
