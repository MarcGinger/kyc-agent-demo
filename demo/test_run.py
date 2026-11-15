import importlib.util
import datetime
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

spec = importlib.util.spec_from_file_location('runner', Path(__file__).with_name('run.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

from policy_checks import applicable_rules, three_month_window, expired
from result_validation import validate_outcomes

class PolicyTests(unittest.TestCase):
    def test_month_end_and_expiry_boundaries(self):
        day = datetime.date(2024, 5, 31)
        self.assertEqual(three_month_window(day), (datetime.date(2024, 2, 29), day))
        self.assertFalse(expired(day, day))
        self.assertTrue(expired(datetime.date(2024, 5, 30), day))
        self.assertIsNone(expired(None, day))
    def test_applicability(self):
        policy = {'rules': [{'id':'D1','applies_to':'person'}, {'id':'D3','applies_to':'company'}, {'id':'D5','applies_to':'both'}]}
        self.assertEqual([r['id'] for r in applicable_rules(policy, 'company')], ['D3', 'D5'])

class OutcomeTests(unittest.TestCase):
    policy = {'rules':[{'id':'D1','applies_to':'person'}, {'id':'D3','applies_to':'company'}, {'id':'D5','applies_to':'both'}]}
    def test_d3_satisfied_does_not_become_gap(self):
        rows = [{'rule_id':'D3','outcome':'satisfied','explanation':'Evidence supplied'}, {'rule_id':'D5','outcome':'gap','explanation':'Explanation missing'}]
        outcomes, gaps = validate_outcomes(rows, self.policy, 'company')
        self.assertEqual([r['rule_id'] for r in gaps], ['D5'])
        self.assertEqual(outcomes[0]['outcome'], 'not_applicable')
    def test_company_rejects_person_rule(self):
        with self.assertRaisesRegex(ValueError, 'Inapplicable'):
            validate_outcomes([{'rule_id':'D1','outcome':'gap','explanation':'x'}], self.policy, 'company')
    def test_duplicate_and_missing_rejected(self):
        row = {'rule_id':'D3','outcome':'satisfied','explanation':'x'}
        with self.assertRaisesRegex(ValueError, 'Duplicate'): validate_outcomes([row,row], self.policy, 'company')
        with self.assertRaisesRegex(ValueError, 'Missing'): validate_outcomes([row], self.policy, 'company')

class InventoryTests(unittest.TestCase):
    def test_inventory_hash_and_unreadable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'scan.png').write_bytes(b'evidence')
            with patch.object(runner, 'command', return_value=type('Result', (), {'returncode': 1, 'stdout': ''})()):
                docs, texts = runner.inventory(root)
            self.assertEqual(docs[0]['status'], 'unreadable')
            self.assertEqual(docs[0]['sha256'], 'ee8250fb76e094b34b471f13a73dbbe51d1ae142e9df59d7c0d31ec20f0a0a8e')
    def test_authoring_metadata_excluded_from_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'profile.json').write_text('{\"answer\": \"secret\"}')
            (root/'manifest.json').write_text('{\"expected\": true}')
            (root/'evidence.png').write_bytes(b'evidence')
            with patch.object(runner, 'command', return_value=type('Result', (), {'returncode': 0, 'stdout': 'image'})()):
                docs, texts = runner.inventory(root)
            self.assertEqual([d['filename'] for d in docs], ['evidence.png'])
            self.assertNotIn('secret', str(texts))

    def test_image_ocr_is_flagged_for_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'scan.png').write_bytes(b'image')
            with patch.object(runner, 'command', return_value=type('Result', (), {'returncode': 0, 'stdout': 'OCR text'})()):
                docs, texts = runner.inventory(root)
            self.assertEqual(docs[0]['status'], 'ocr_needs_review')
            self.assertEqual(texts[0]['pages'][0]['method'], 'ocr')

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'link').symlink_to('/etc/passwd')
            with self.assertRaises(ValueError): runner.inventory(root)

if __name__ == '__main__': unittest.main()
