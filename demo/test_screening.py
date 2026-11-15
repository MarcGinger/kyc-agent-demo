import unittest
from screening import lookup

class FixtureTests(unittest.TestCase):
    def test_unknown_never_clears(self):
        result = lookup('unknown', {'fixture_version':'1', 'subjects':{}})
        self.assertEqual(set(result['coverage'].values()), {'NOT_PERFORMED'})
        self.assertEqual(result['mode'], 'SIMULATED')
    def test_partial_coverage_stays_incomplete(self):
        result = lookup('x', {'fixture_version':'1', 'subjects':{'x':{'pep':'INCOMPLETE'}}})
        self.assertEqual(result['coverage']['pep'], 'INCOMPLETE')
        self.assertEqual(result['coverage']['sanctions'], 'NOT_PERFORMED')
    def test_unknown_status_rejected(self):
        with self.assertRaises(ValueError):
            lookup('x', {'fixture_version':'1', 'subjects':{'x':{'pep':'CLEAR'}}})

if __name__ == '__main__': unittest.main()
