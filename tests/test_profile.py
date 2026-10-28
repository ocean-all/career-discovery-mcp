import os
import tempfile
import unittest
from pathlib import Path
from jobmonitor.profile import load,save,validate,search_plan
from jobmonitor.core import assess,Job,Store

class ProfileTests(unittest.TestCase):
    def test_blank_profile_does_not_assume_career(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=load(Path(tmp))
        self.assertEqual(p['roles'],[])
        self.assertEqual(p['experience'],'unknown')
        self.assertFalse(search_plan(p)['ready'])
    def test_unaccepted_expansions_never_searched(self):
        p=validate({'state':'confirmed','roles':['제품기획'],'industries':['게임'],
                    'proposed_expansions':['유통 연구'],'experience':'entry'})
        plan=search_plan(p)
        self.assertEqual(plan['queries'],['게임 제품기획 신입 채용'])
        self.assertNotIn('유통',str(plan))
    def test_draft_hypotheses_are_not_confirmation(self):
        self.assertFalse(search_plan({'roles':['분석'],'proposed_expansions':['AI']})['ready'])
    def test_roundtrip_and_private_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            save(root,{'state':'confirmed','industries':['반도체'],'skills':['Excel']})
            self.assertEqual(load(root)['industries'],['반도체'])
            if os.name != 'nt':
                self.assertEqual((root/'profile.json').stat().st_mode & 0o777,0o600)
    def test_invalid_and_bounds(self):
        for p in [{'state':'confirmed'},{'days':False},{'days':366},{'roles':'engineer'},{'secret':'x'}]:
            with self.assertRaises(ValueError):validate(p)
    def test_profile_controls_scoring_not_retail_default(self):
        p={'roles':['제품기획'],'industries':['게임'],'skills':['분석'],'experience':'entry'}
        self.assertGreater(assess('게임 제품기획 신입 분석',profile=p)[0],assess('물류 학력무관 Excel 연구 신입',profile=p)[0])
        self.assertEqual(assess('물류 학력무관 Excel 연구 신입')[0],0)
    def test_ranking_change_is_not_posting_change(self):
        store=Store(':memory:',profile={'roles':['분석']})
        try:
            j=Job('company','1','https://example.com/job','분석 기획')
            self.assertEqual(store.upsert(j)[1],'new')
            store.profile={'roles':['다른직무']}
            self.assertIsNone(store.upsert(j)[1])
        finally:store.close()
    def test_query_cap_is_explicit(self):
        p={'state':'confirmed','roles':[f'role{i}' for i in range(10)],'industries':[f'industry{i}' for i in range(10)]}
        self.assertTrue(search_plan(p)['truncated'])
        self.assertEqual(len(search_plan(p)['queries']),24)
