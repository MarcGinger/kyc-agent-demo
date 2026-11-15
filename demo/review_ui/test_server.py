import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen

spec=importlib.util.spec_from_file_location('review_server',Path(__file__).with_name('server.py'))
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); self.now=1000.0
        self.person=self.root/'person'; self.company=self.root/'company'; self.runs=self.root/'runs'; self.reviews=self.root/'reviews'
        self.person.mkdir(); self.company.mkdir(); self.runs.mkdir()
        self.commit=subprocess.check_output(['git','rev-parse','a21babf'],cwd=mod.ROOT,text=True).strip()
        for pack, root in [('person',self.person),('company',self.company)]:
            (root/'documents').mkdir(); (root/'documents'/'source.png').write_bytes((pack+'-image').encode())
            for n in (1,2):
                run=self.runs/f'{pack}-{n}';run.mkdir()
                meta={'pack_type':pack,'execution_status':'COMPLETED','working_tree_dirty':False,'policy_version':'DEMO-1.1','code_commit':self.commit,'input_inventory':[{'filename':'documents/source.png','sha256':mod.digest(root/'documents'/'source.png'),'status':'ocr_needs_review'}]}
                results={'facts':[{'field':'name','value':'original','filename':'documents/source.png','page':1}], 'rule_outcomes':[{'rule_id':'D3','outcome':'satisfied','explanation':'source provided'}], 'missing_values':['Missing date']}
                (run/'metadata.json').write_text(json.dumps(meta)); (run/'results.json').write_text(json.dumps(results))
        self.store=mod.Store({'person':self.person,'company':self.company},self.runs,self.reviews,clock=lambda:self.now)
        self.bundle,self.path=self.store.load('person','person-1'); self.client='0123456789abcdef0123456789abcdef'
    def tearDown(self): self.tmp.cleanup()
    def act(self,action,**kwargs): return self.store.mutate(self.bundle,self.path,{'client':self.client,'action':action,**kwargs})
    def test_citations_and_missing_or_escaped_sources(self):
        self.assertEqual(self.bundle['items'][1]['raw_original'], 'Missing date')
        cite=self.bundle['items'][0]['citations'][0]; self.assertTrue(cite['valid']); self.assertEqual(cite['page'],1)
        inventory={'../escape':{'sha256':'x'}}
        self.assertFalse(self.store.citations('person',inventory,[{'filename':'../escape','page':1}])[0]['valid'])
        self.assertFalse(self.store.citations('person',{'documents/source.png':{'sha256':mod.digest(self.person/'documents'/'source.png')}},[{'filename':'documents/source.png','page':2}])[0]['valid'])
        (self.person/'documents'/'source.png').unlink()
        self.assertFalse(self.store.citations('person',{'documents/source.png':{'sha256':'x'}},[{'filename':'documents/source.png','page':1}])[0]['valid'])
    def test_correction_persists_with_original_and_isolated(self):
        before=mod.digest(self.person/'documents'/'source.png'); self.act('decision',item='fact-0',status='corrected',value='corrected',note='checked')
        restored=self.store.state(self.bundle,self.path); self.assertEqual(restored['decisions']['fact-0']['original']['value'],'original');self.assertEqual(restored['decisions']['fact-0']['value'],'corrected')
        for pack,run in [('person','person-2'),('company','company-1')]:
            b,p=self.store.load(pack,run); self.assertEqual(self.store.state(b,p)['decisions'],{})
        self.assertEqual(before,mod.digest(self.person/'documents'/'source.png'))
        self.assertEqual(self.bundle['binding']['results_sha256'],mod.digest(self.runs/'person-1'/'results.json'))
    def test_changed_artifact_cannot_reuse_review(self):
        self.act('decision',item='fact-0',status='confirmed')
        path = self.runs/'person-1'/'results.json'
        changed = json.loads(path.read_text()); changed['facts'][0]['value'] = 'changed'; path.write_text(json.dumps(changed))
        bundle, review_path = self.store.load('person','person-1')
        self.assertNotEqual(bundle['binding']['results_sha256'], self.bundle['binding']['results_sha256'])
        self.assertEqual(self.store.state(bundle,review_path)['decisions'], {})

    def test_timer_exclusive_pause_and_finish(self):
        self.act('start'); self.now+=5; self.act('heartbeat');self.now+=4
        with self.assertRaisesRegex(ValueError,'another tab'):
            self.store.mutate(self.bundle,self.path,{'client':'another-client-0123456789','action':'resume'})
        b,p=self.store.load('company','company-1')
        with self.assertRaisesRegex(ValueError,'Another review'):
            self.store.mutate(b,p,{'client':self.client,'action':'start'})
        self.act('pause'); self.now+=100; state=self.store.state(self.bundle,self.path);self.assertEqual(state['timer']['seconds'],9)
        with self.assertRaisesRegex(ValueError,'Every item'): self.act('finish')
        with self.assertRaisesRegex(ValueError,'Reason'): self.act('decision',item='fact-0',status='unable',note='')
        with self.assertRaisesRegex(ValueError,'rationale'): self.act('decision',item='rule-0',status='corrected',value='gap',note='')
        self.act('decision',item='fact-0',status='unable',note='unreadable');self.act('decision',item='rule-0',status='confirmed');self.act('decision',item='missing-0',status='unable',note='No date'); self.act('resume');self.now+=3
        state=self.act('finish'); self.assertTrue(state['finished']);self.assertEqual(state['timer']['seconds'],12)
        with self.assertRaisesRegex(ValueError,'finished'): self.act('resume')
    def test_resume_discards_unacknowledged_interval(self):
        self.act('start'); self.now += 4; self.act('heartbeat'); self.now += 6
        self.act('resume'); self.now += 2; state = self.act('pause')
        self.assertEqual(state['timer']['seconds'], 6)

    def test_stale_lease_caps_time_and_reload_pauses(self):
        self.act('start');self.now+=100
        other=mod.Store({'person':self.person,'company':self.company},self.runs,self.reviews,clock=lambda:self.now)
        state=other.state(self.bundle,self.path);self.assertEqual(state['timer']['seconds'],0);self.assertIsNone(state['timer']['owner'])
    def test_http_invalid_paths_and_wrong_host(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),mod.Handler);server.store=self.store
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            base=f'http://127.0.0.1:{server.server_port}'
            with urlopen(base+'/api/catalog') as response: self.assertEqual(len(json.load(response)),4)
            with self.assertRaises(HTTPError) as bad_path: urlopen(base+'/api/document?pack=person&run=person-1&file=../../etc/passwd&page=1')
            bad_path.exception.close()
            with self.assertRaises(HTTPError) as bad_pack: urlopen(base+'/api/run?pack=company&run=person-1')
            bad_pack.exception.close()
        finally: server.shutdown();server.server_close();thread.join()

if __name__=='__main__': unittest.main()
