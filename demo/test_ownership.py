import unittest
from ownership_check import check

class OwnershipTests(unittest.TestCase):
    def test_single_tier_and_disagreement(self):
        source = {'filename':'source.pdf','page':1}
        data = {'intermediate':{'percent':60,'source':source}, 'owners':[
            {'owner':'A','route':'intermediate','direct_percent':75,'stated_effective_percent':45,'direct_source':source,'declaration_source':source},
            {'owner':'B','route':'direct','direct_percent':40,'stated_effective_percent':41,'direct_source':source,'declaration_source':source}]}
        result = check(data)['results']
        self.assertTrue(result[0]['matches'])
        self.assertFalse(result[1]['matches'])
        self.assertEqual(result[0]['calculated_percent'], '45')
        self.assertEqual(result[0]['intermediate_source'], source)
