#!/usr/bin/env python3
"""Loopback-only, file-backed evidence review server; Python standard library + Poppler."""
import argparse
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ID = re.compile(r'^[A-Za-z0-9_-]+$')
LEASE = 12

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def safe_file(root, relative):
    if not isinstance(relative, str) or not relative or '\x00' in relative: raise ValueError('Invalid path')
    try: path = (root / relative).resolve(strict=True)
    except OSError: raise ValueError('Source document is unavailable')
    if not path.is_file() or not path.is_relative_to(root): raise ValueError('Invalid path')
    return path

def pages(path):
    if path.suffix.lower() != '.pdf': return 1
    result = subprocess.run(['pdfinfo', str(path)], capture_output=True, text=True, timeout=15)
    if result.returncode: raise ValueError('Unreadable PDF')
    return next((int(line.split(':', 1)[1].strip()) for line in result.stdout.splitlines() if line.startswith('Pages:')), 0)

class Store:
    def __init__(self, packs, runs, reviews, clock=time.time):
        self.packs = {k: Path(v).resolve(strict=True) for k,v in packs.items()}
        self.runs = Path(runs).resolve(strict=True)
        self.reviews = Path(reviews).resolve()
        self.reviews.mkdir(mode=0o700, parents=True, exist_ok=True)
        if any(self.reviews == p or self.reviews.is_relative_to(p) or p.is_relative_to(self.reviews) for p in [self.runs, *self.packs.values()]): raise ValueError('Review directory must not overlap inputs')
        self.clock = clock
        self.lock = threading.RLock()
        # A server restart ends a previous timer, bounded by its lease.
        for file in self.reviews.glob('*.json'):
            try:
                state = json.loads(file.read_text())
                if state.get('timer', {}).get('owner'):
                    self.stop_timer(state, self.clock(), accrue=False)
                    self.write(file, state)
            except (OSError, ValueError, KeyError, json.JSONDecodeError): pass
    def write(self, path, data):
        fd, temp = tempfile.mkstemp(dir=self.reviews, prefix='.review-', suffix='.tmp')
        try:
            with os.fdopen(fd, 'w') as f: json.dump(data, f, indent=2, ensure_ascii=False)
            os.chmod(temp, 0o600); os.replace(temp, path)
        finally:
            if os.path.exists(temp): os.unlink(temp)
    def catalog(self):
        out = []
        for d in sorted(self.runs.iterdir()):
            if not d.is_dir() or d.is_symlink() or not ID.fullmatch(d.name): continue
            try:
                m = json.loads(safe_file(d, 'metadata.json').read_text())
                safe_file(d, 'results.json')
                if m.get('pack_type') not in self.packs or m.get('execution_status') != 'COMPLETED' or m.get('working_tree_dirty') is not False: continue
                if not isinstance(json.loads((d/'results.json').read_text()).get('rule_outcomes'), list): continue
                out.append({'run':d.name, 'pack':m['pack_type'], 'policy':m.get('policy_version'), 'date':m.get('assessment_date')})
            except (OSError, ValueError, json.JSONDecodeError): continue
        return out
    def load(self, pack, run):
        if pack not in self.packs or not ID.fullmatch(run): raise ValueError('Unknown pack or run')
        if not any(x['run']==run and x['pack']==pack for x in self.catalog()): raise ValueError('Unknown pack or run')
        directory = (self.runs / run).resolve(strict=True)
        if not directory.is_relative_to(self.runs): raise ValueError('Invalid run')
        rp, mp = safe_file(directory,'results.json'), safe_file(directory,'metadata.json')
        data, meta = json.loads(rp.read_text()), json.loads(mp.read_text())
        commit = meta.get('code_commit', '')
        if not isinstance(commit, str) or not re.fullmatch(r'[0-9a-f]{40}', commit): raise ValueError('Run commit unavailable')
        historical = subprocess.run(['git','show',commit+':demo/policy.json'], cwd=ROOT, capture_output=True, timeout=10)
        if historical.returncode: raise ValueError('Run policy unavailable at recorded commit')
        policy = json.loads(historical.stdout)
        if policy['version'] != meta.get('policy_version'): raise ValueError('Run policy version mismatch')
        binding = {'pack':pack,'run':run,'results_sha256':digest(rp),'metadata_sha256':digest(mp),'policy_version':policy['version'],'policy_sha256':hashlib.sha256(historical.stdout).hexdigest()}
        key = hashlib.sha256(json.dumps(binding,sort_keys=True).encode()).hexdigest()
        inventory = {x['filename']:x for x in meta.get('input_inventory', [])}
        items = []
        for i, fact in enumerate(data.get('facts',[])):
            refs = [fact]
            for field in ('citations', 'sources'):
                if isinstance(fact.get(field), list): refs.extend(fact[field])
            items.append({'id':f'fact-{i}', 'kind':'fact', 'original':fact, 'citations':self.citations(pack, inventory, refs), 'method':inventory.get(fact.get('filename'),{}).get('status','unknown')})
        for i, missing in enumerate(data.get('missing_values', [])):
            display = missing if isinstance(missing, dict) else {'field':str(missing)}
            items.append({'id':f'missing-{i}', 'kind':'missing', 'original':display, 'raw_original':missing, 'citations':self.citations(pack, inventory, [display]) if display.get('filename') else [], 'method':'not provided'})
        rulemap = {r['id']:r['requirement'] for r in policy['rules']}
        for i, rule in enumerate(data.get('rule_outcomes',[])):
            # Only structured references supplied by the agent are used; prose is never interpreted as a citation.
            refs = rule.get('citations', rule.get('sources', []))
            if not isinstance(refs, list): refs = []
            items.append({'id':f'rule-{i}', 'kind':'rule', 'original':rule, 'rule_text':rulemap.get(rule.get('rule_id'),'Rule text unavailable'), 'citations':self.citations(pack, inventory, refs)})
        return {'binding':binding,'key':key,'metadata':meta,'data':data,'items':items,'inventory':list(inventory.values())}, self.reviews / (key+'.json')
    def citations(self, pack, inventory, refs):
        citations=[]
        for ref in refs:
            if not isinstance(ref, dict): citations.append({'valid':False,'reason':'Invalid citation'}); continue
            name, page = ref.get('filename'), ref.get('page')
            try:
                if not isinstance(name, str) or name not in inventory: raise ValueError('Not in run inventory')
                file = safe_file(self.packs[pack], name)
                if digest(file) != inventory[name].get('sha256'): raise ValueError('Document differs from run hash')
                total = pages(file)
                if page is not None and (not isinstance(page,int) or isinstance(page,bool) or page < 1 or page > total): raise ValueError('Invalid page')
                citations.append({'filename':name,'page':page,'pages':total,'valid':True})
            except (OSError, ValueError, subprocess.SubprocessError) as e: citations.append({'filename':name,'page':page,'valid':False,'reason':str(e)})
        return citations
    def state(self, bundle, path):
        if path.exists():
            state=json.loads(path.read_text())
            if state.get('binding') != bundle['binding']: raise ValueError('Review binding mismatch')
            return state
        return {'binding':bundle['binding'],'decisions':{},'timer':{'seconds':0.0,'owner':None,'last':None},'finished':False}
    def stop_timer(self, state, now, accrue=True):
        timer=state['timer']
        if accrue and timer.get('owner') and timer.get('last') is not None:
            timer['seconds'] += max(0, min(now-timer['last'], LEASE))
        timer.update(owner=None,last=None)
    def mutate(self, bundle, path, payload):
        with self.lock:
            state=self.state(bundle,path); action=payload.get('action'); now=self.clock(); timer=state['timer']
            owner=payload.get('client')
            if not isinstance(owner,str) or not re.fullmatch(r'[A-Za-z0-9-]{16,80}',owner): raise ValueError('Invalid client')
            if timer.get('owner') and now-timer['last'] > LEASE: self.stop_timer(state,now,accrue=False)
            if action in ('start','resume'):
                for other_path in self.reviews.glob('*.json'):
                    if other_path == path: continue
                    other = json.loads(other_path.read_text())
                    if other.get('timer', {}).get('owner'):
                        if now - other['timer']['last'] > LEASE:
                            self.stop_timer(other, now, accrue=False); self.write(other_path, other)
                        else: raise ValueError('Another review timer is active')
                if state['finished']: raise ValueError('Review already finished')
                if timer['owner'] and timer['owner'] != owner: raise ValueError('Review timer is active in another tab')
                # Resuming with the same owner discards any unacknowledged interval,
                # including time hidden if a pause request was lost.
                if timer['owner'] == owner: self.stop_timer(state,now,accrue=False)
                timer.update(owner=owner,last=now)
            elif action == 'heartbeat':
                if timer['owner'] != owner: raise ValueError('Timer not owned by this tab')
                timer['seconds'] += max(0,min(now-timer['last'],LEASE)); timer['last']=now
            elif action == 'pause':
                if timer['owner'] == owner: self.stop_timer(state,now)
            elif action == 'decision':
                if state['finished']: raise ValueError('Review already finished')
                item=next((x for x in bundle['items'] if x['id']==payload.get('item')),None)
                if not item: raise ValueError('Unknown item')
                status=payload.get('status'); value=payload.get('value',''); note=payload.get('note','')
                if status not in ('confirmed','corrected','unable'): raise ValueError('Invalid disposition')
                if not isinstance(value,str) or not isinstance(note,str) or len(value)>10000 or len(note)>5000: raise ValueError('Invalid review text')
                if status == 'corrected' and (not value.strip() or (item['kind']=='rule' and not note.strip())): raise ValueError('Correction and rule rationale required')
                if item['kind']=='rule' and status=='corrected' and value not in ('satisfied','gap','unknown','not_applicable'): raise ValueError('Invalid rule outcome')
                if status == 'unable' and not note.strip(): raise ValueError('Reason required')
                state['decisions'][item['id']]={'status':status,'value':value if status=='corrected' else '', 'note':note, 'original':item['original']}
            elif action == 'finish':
                if timer['owner'] and timer['owner'] != owner: raise ValueError('Review timer is active in another tab')
                if any(x['id'] not in state['decisions'] for x in bundle['items']): raise ValueError('Every item needs a disposition')
                self.stop_timer(state,now); state['finished']=True; state['finished_at']=now
            else: raise ValueError('Unknown action')
            self.write(path,state); return state

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass
    def send(self,status,body,ctype='application/json'):
        if isinstance(body,(dict,list)): body=json.dumps(body,ensure_ascii=False).encode()
        elif isinstance(body,str): body=body.encode()
        self.send_response(status); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(body))); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"); self.send_header('Referrer-Policy','no-referrer'); self.end_headers(); self.wfile.write(body)
    def valid_host(self):
        return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'
    def do_GET(self):
        try:
            if not self.valid_host(): raise ValueError('Invalid host')
            url=urlsplit(self.path); q=parse_qs(url.query); store=self.server.store
            if url.path in ('/','/app.js','/style.css'):
                path=HERE/('index.html' if url.path=='/' else url.path[1:]); return self.send(200,path.read_bytes(),mimetypes.guess_type(path.name)[0] or 'text/plain')
            if url.path == '/api/catalog': return self.send(200,store.catalog())
            pack,run=q.get('pack',[''])[0],q.get('run',[''])[0]; bundle,path=store.load(pack,run)
            if url.path=='/api/run':
                with store.lock:
                    state=store.state(bundle,path)
                    if state['timer'].get('owner') and store.clock()-state['timer']['last'] > LEASE:
                        store.stop_timer(state,store.clock(),accrue=False); store.write(path,state)
                    return self.send(200,{'bundle':bundle,'review':state})
            if url.path=='/api/docinfo':
                name=q.get('file',[''])[0]
                return self.send(200,store.citations(pack,{x['filename']:x for x in bundle['inventory']},[{'filename':name,'page':None}])[0])
            if url.path=='/api/document':
                name=q.get('file',[''])[0]; page=int(q.get('page',['1'])[0]); info=store.citations(pack,{x['filename']:x for x in bundle['inventory']},[{'filename':name,'page':page}])[0]
                if not info['valid']: raise ValueError(info['reason'])
                file=safe_file(store.packs[pack],name)
                if file.suffix.lower()=='.pdf':
                    result=subprocess.run(['pdftoppm','-f',str(page),'-l',str(page),'-singlefile','-scale-to','1800','-png',str(file)],capture_output=True,timeout=30)
                    if result.returncode: raise ValueError('Unable to render page')
                    return self.send(200,result.stdout,'image/png')
                if file.suffix.lower() not in ('.png','.jpg','.jpeg','.gif','.webp'): raise ValueError('Unsupported image')
                return self.send(200,file.read_bytes(),mimetypes.guess_type(file.name)[0])
            if url.path=='/api/export':
                with store.lock:
                    state=store.state(bundle,path)
                    # Export a current bounded snapshot without changing the live timer.
                    snapshot=json.loads(json.dumps(state)); now=store.clock(); timer=snapshot['timer']; stale=timer.get('owner') and now-timer['last'] > LEASE; store.stop_timer(snapshot,now,accrue=not stale)
                    return self.send(200,{'provenance':bundle['binding'],'metadata':bundle['metadata'],'review':snapshot,'items':bundle['items']})
            return self.send(404,{'error':'Not found'})
        except (ValueError,OSError,KeyError,json.JSONDecodeError,subprocess.SubprocessError) as e: return self.send(400,{'error':str(e)})
    def do_POST(self):
        try:
            if not self.valid_host(): raise ValueError('Invalid host')
            origin=self.headers.get('Origin')
            if origin and origin != f'http://{self.headers.get("Host")}': raise ValueError('Origin rejected')
            if self.path != '/api/review': return self.send(404,{'error':'Not found'})
            length=int(self.headers.get('Content-Length','0'))
            if length < 1 or length > 100000: raise ValueError('Invalid request size')
            data=json.loads(self.rfile.read(length)); bundle,path=self.server.store.load(data.get('pack',''),data.get('run',''))
            return self.send(200,self.server.store.mutate(bundle,path,data))
        except (ValueError,OSError,KeyError,json.JSONDecodeError) as e: return self.send(400,{'error':str(e)})

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--person-pack',required=True,type=Path); p.add_argument('--company-pack',required=True,type=Path); p.add_argument('--runs-dir',required=True,type=Path); p.add_argument('--reviews-dir',required=True,type=Path); p.add_argument('--port',type=int,default=8765); a=p.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',a.port),Handler); server.store=Store({'person':a.person_pack,'company':a.company_pack},a.runs_dir,a.reviews_dir)
    print(f'Local review: http://127.0.0.1:{server.server_port}',flush=True); server.serve_forever()
if __name__=='__main__': main()
