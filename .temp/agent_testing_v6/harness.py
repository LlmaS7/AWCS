"""Isolated production-chain driver. No production files are changed."""
import sys, json, time, hashlib, threading, re
from pathlib import Path
from copy import deepcopy
from uuid import uuid4
from dataclasses import asdict

PROJECT = Path(r'E:\_PROJECTS\AWCS')
sys.dont_write_bytecode = True
sys.path.insert(0, str(PROJECT))
from controller import Controller
from ai.service import AIService
from ai.configuration import Configuration
from ai.provider import DeepSeek, CancelToken, ProviderError, Stopped
from ai.tools import TOOLS, WRITES, query, normalize, task_view
from simulation import Simulation

def write(path, obj):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
    deadline=time.monotonic()+1
    while True:
        try:tmp.replace(path);break
        except PermissionError:
            # Windows readers can briefly deny atomic replacement. Retry only this
            # file operation, never a provider request or business command.
            if time.monotonic()>=deadline:raise
            time.sleep(.02)

def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def scrub(obj, secret=''):
    if isinstance(obj,dict):
        return {k:scrub(v,secret) for k,v in obj.items() if k not in ('reasoning_content','headers','Authorization','api_key')}
    if isinstance(obj,list): return [scrub(v,secret) for v in obj]
    if isinstance(obj,str) and secret: return obj.replace(secret,'[REDACTED]')
    return obj

class MemoryStore:
    def read(self,*a): return ''
    def write(self,*a): raise AssertionError('credential persistence forbidden')
    def delete(self,*a): pass

def configuration(path, values=None):
    cfg=Configuration(path=path,store=MemoryStore())
    cfg.save(values or {'base_url':'http://127.0.0.1:1','api_key':'synthetic-local-only',
                       'model':'synthetic','effort':'high','timeout':300,'remember':False})
    return cfg

def parse_key(path):
    """Accept JSON or labeled Markdown without printing the credential text."""
    raw=Path(path).read_text(encoding='utf-8-sig').strip()
    aliases={'baseurl':'base_url','base_url':'base_url','api_base':'base_url','url':'base_url',
             'apikey':'api_key','api_key':'api_key','key':'api_key','modelid':'model','model_id':'model',
             'model':'model','effort':'effort','reasoning_effort':'effort','timeout':'timeout'}
    try: obj=json.loads(raw)
    except ValueError:
        obj={}
        for line in raw.splitlines():
            line=line.strip().strip('|').strip()
            match=re.match(r'^[#*\s`-]*([A-Za-z_ ]+?)[*`\s]*(?::|：|=|\|)\s*(.+?)\s*$',line)
            if not match: continue
            label=re.sub(r'\s+','',match[1]).lower()
            if label not in aliases: continue
            k=aliases[label]; v=match[2].strip().strip('|').strip().strip('`').strip('"').strip("'")
            if k in obj and obj[k]!=v: raise ValueError('ambiguous configuration field: '+k)
            obj[k]=v
    if not isinstance(obj,dict): raise ValueError('configuration must be labeled fields')
    values={}
    for k,v in obj.items():
        label=re.sub(r'\s+','',k).lower()
        if label in aliases: values[aliases[label]]=v
    for k in ('base_url','api_key','model'):
        if not isinstance(values.get(k),str) or not values[k]: raise ValueError('missing field: '+k)
    if 'timeout' in values:
        try: values['timeout']=int(values['timeout'])
        except (TypeError,ValueError): raise ValueError('invalid field: timeout') from None
    values['remember']=False
    Configuration.clean({k:v for k,v in values.items() if k!='api_key'})
    return values

def sources():
    files=[]
    for folder in ('ai','task_imports','coordination','planning','map_support'):
        files.extend((PROJECT/folder).glob('*.py'))
    files.extend(PROJECT.glob('*.py'))
    return {str(p.relative_to(PROJECT)):digest(p) for p in sorted(files)}

class AuditController(Controller):
    """Read-only actor snapshot; never exposed as a model tool."""
    def _execute(self,op,data):
        if op=='_test_snapshot': return
        return super()._execute(op,data)
    def _business(self,envelope,future):
        # An internal read request stays on the owning actor. Business execution untouched.
        if envelope['name']=='_test_snapshot':
            future.set_result({'generation':self.generation,'tick':self.sim.tick,
              'tasks':[asdict(t) for t in self.sim.tasks.values()],
              'task_views':[task_view(t,self.sim.warehouse) for t in self.sim.tasks.values()],
              'robots':[asdict(r) for r in self.sim.robots], 'dirty':self.sim.dirty,
              'auto':self.sim.auto,'planning':self._planning,'metrics':deepcopy(self.sim.metrics),
              'assignment':deepcopy(self.sim.assignment)})
            return
        guard=getattr(self,'effect_guard',None)
        if guard and envelope['name'] in WRITES:
            original_progress=envelope.get('on_progress'); original_valid=envelope.get('valid',lambda:True)
            blocked=[False]
            def progress(result):
                if original_progress:original_progress(result)
                if not guard(result,self.sim):
                    blocked[0]=True
                    cancel=getattr(self,'effect_cancel',None)
                    if cancel:cancel()
            envelope={**envelope,'on_progress':progress,'valid':lambda:not blocked[0] and original_valid()}
        return super()._business(envelope,future)

def call(name,args):
    return {'id':uuid4().hex,'type':'function','function':{'name':name,'arguments':args if isinstance(args,str) else json.dumps(args,ensure_ascii=False)}}
def reply(*calls,content=''):
    value={'role':'assistant','content':content}
    if calls:value['tool_calls']=list(calls)
    return value

class Scripted:
    def __init__(self,script): self.script=list(script); self.count=0
    def chat(self,cfg,messages,tools,token,on_text=None):
        if hasattr(self,'case_deadline') and time.monotonic()>=self.case_deadline:raise ProviderError('CASE_TIME_LIMIT')
        token.check(); self.count+=1
        value=self.script.pop(0) if self.script else reply(content='合成回复：请核对真实回执。')
        if isinstance(value,Exception): raise value
        if callable(value): value=value(cfg,messages,tools,token,on_text)
        if on_text and value.get('content'):on_text(value['content'])
        return value,None

class Observed:
    def __init__(self,provider,directory,budget=None,phase='offline'):
        self.provider=provider; self.directory=Path(directory); self.budget=budget; self.phase=phase
        self.calls=[]; self.secret=''; self.request_context={}
    def chat(self,cfg,messages,tools,token,on_text=None):
        if time.monotonic()>=getattr(self,'case_deadline',float('inf')):raise ProviderError('CASE_TIME_LIMIT')
        self.secret=cfg['api_key']; number=len(self.calls)+1
        entry={'index':number,'kind':'summary' if not tools else 'chat','start':time.time(),
               'context':deepcopy(self.context_supplier() if hasattr(self,'context_supplier') else self.request_context),'state':'reserved'}
        self.calls.append(entry)
        reservation=self.budget.reserve(self.phase,entry['kind']) if self.budget else None
        entry['messages']=scrub(messages,self.secret)
        entry['state']='send_attempted'; self.flush()
        if self.budget:self.budget.update(reservation,'send_attempted')
        try:
            value,usage=self.provider.chat(cfg,messages,tools,token,on_text)
            entry.update(state='stream_complete',response=scrub(value,self.secret),usage=scrub(usage,self.secret),
                         seconds=time.time()-entry['start'])
            if self.budget:self.budget.update(reservation,'stream_complete',usage=scrub(usage,self.secret))
            return value,usage
        except Exception as exc:
            entry.update(state='error',error_type=type(exc).__name__,error=scrub(str(exc),self.secret),seconds=time.time()-entry['start'])
            if self.budget:self.budget.update(reservation,'error',error=entry['error'])
            raise
        finally:self.flush()
    def flush(self):
        try:write(self.directory/'provider_calls.json',self.calls)
        except OSError as exc:
            self.infrastructure_error={'type':type(exc).__name__,'message':scrub(str(exc),self.secret)}
            raise

class Budget:
    def __init__(self,directory,limit=1200):
        self.path=Path(directory)/'budget.json'; self.limit=min(limit,1200)
        self.value=read(self.path) if self.path.exists() else {'start':None,'reservations':[]}
    def reserve(self,phase,kind):
        now=time.time()
        if self.value['start'] is None:self.value['start']=now
        if now-self.value['start']>=14400:raise ProviderError('BATCH_TIME_LIMIT')
        entries=self.value['reservations']
        if len(entries)>=self.limit:raise ProviderError('API_BUDGET_LIMIT')
        if phase in ('protocol','smoke') and sum(x['phase'] in ('protocol','smoke') for x in entries)>=60:
            raise ProviderError('SMOKE_API_LIMIT')
        item={'id':len(entries)+1,'phase':phase,'kind':kind,'reserved_at':now,'state':'reserved','reserved':True,
              'send_attempted':False,'response_received':False,'stream_complete':False,'usage_known':False}
        entries.append(item); write(self.path,self.value);return item['id']
    def update(self,identity,state,**extra):
        item=self.value['reservations'][identity-1]; item.update(state=state,**extra)
        if state=='send_attempted':item['send_attempted']=True
        if state=='stream_complete':item.update(response_received=True,stream_complete=True)
        item['usage_known']=extra.get('usage') is not None
        write(self.path,self.value)

class Session:
    def __init__(self,scenario,directory,provider=None,values=None,budget=None,phase='offline',before_start=None):
        self.case_deadline=time.monotonic()+900
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        # Redirect only incidental output paths, never domain algorithms, prompts or limits.
        import controller,persistence
        controller.OUTPUTS=persistence.OUTPUTS=self.directory/'incidental_outputs'
        self.controller=AuditController(scenario=Path(scenario),paused=True,auto=False)
        if before_start:before_start(self.controller.sim)
        self.observed=Observed(provider or Scripted([]),directory,budget,phase)
        self.observed.case_deadline=self.case_deadline
        self.ai=AIService(self.controller,configuration(self.directory/'isolated_settings.json',values),self.observed)
        self.controller.effect_cancel=lambda:self.ai.active['token'].event.set() if self.ai.active else None
        self.observed.context_supplier=lambda:{k:self.ai.active[k] for k in ('id','generation','session') if self.ai.active and k in self.ai.active}
        def context():
            a=self.ai.active
            return {'request_id':a['id'],'generation':a['generation'],'session':a['session']} if a else {}
        self.observed.context_supplier=context
        self.tool_trace=[]; original=self.ai.tool
        def traced(request,name,args,operation_id):
            entry={'request_id':request['id'],'name':name,'arguments':deepcopy(args),'operation_id':operation_id,
                   'generation':request['generation'],'start':time.time()}
            self.tool_trace.append(entry)
            try:
                result=original(request,name,args,operation_id);entry['result']=scrub(result);return result
            except Exception as exc:
                entry.update(error=str(exc),error_type=type(exc).__name__);raise
            finally:
                entry['seconds']=time.time()-entry['start'];write(self.directory/'tool_trace.json',self.tool_trace)
        self.ai.tool=traced
        self.controller.start();self.barrier();self.initial=self.snapshot();write(self.directory/'initial.json',self.initial)
    def barrier(self,limit=40):
        end=time.monotonic()+limit
        while time.monotonic()<end:
            s=self.snapshot()
            if not s['planning']:
                if s['dirty']:raise RuntimeError('FIXTURE_INVALID: initial planning unavailable')
                return s
            time.sleep(.02)
        raise TimeoutError('controller planning barrier')
    def snapshot(self):
        return self.controller.submit('_ai_business',{'name':'_test_snapshot'}).result(timeout=10)
    def business(self,name,args,identity=None,**extra):
        return self.controller.submit('_ai_business',{'name':name,'arguments':args,'generation':self.controller.generation,
                'operation_id':identity or uuid4().hex,**extra}).result(timeout=60)
    def wait(self,identity,limit=900):
        end=min(time.monotonic()+limit,self.case_deadline); cursor=0; events=[]
        while time.monotonic()<end:
            page=self.ai.event_page(cursor)
            if page['gap']:raise RuntimeError('event evidence gap')
            cursor=page['cursor'];events.extend(page['events'])
            write(self.directory/'events.json',scrub(events,self.observed.secret))
            if any(e['kind']=='done' and e.get('request_id')==identity for e in events):
                if hasattr(self.observed,'infrastructure_error'):raise RuntimeError('TEST_INFRASTRUCTURE recorder failed: '+str(self.observed.infrastructure_error))
                while self.snapshot()['planning'] and time.monotonic()<end:time.sleep(.02)
                write(self.directory/'final.json',self.snapshot());return [e for e in events if e.get('request_id')==identity]
            time.sleep(.03)
        self.ai.stop(identity);raise TimeoutError('session hard deadline')
    def message(self,text,task_id=None,kind='message',**extra):
        data={'generation':self.controller.generation,**extra}
        if kind=='message':data['text']=text
        if task_id is not None:data['task_id']=task_id
        r=self.ai.launch(kind,data);return self.wait(r['request_id'])
    def advance(self,predicate,steps=2000,seconds=180):
        frames=[self.snapshot()];end=min(time.monotonic()+seconds,self.case_deadline)
        while not predicate(frames[-1]) and len(frames)<=steps and time.monotonic()<end:
            self.controller.submit('step').result(timeout=min(40,max(1,end-time.monotonic())))
            self.barrier();frames.append(self.snapshot())
        write(self.directory/'trajectory.json',frames);return frames
    def close(self):
        self.ai.stop()
        end=time.monotonic()+10
        while self.ai.public()['busy'] and time.monotonic()<end:time.sleep(.02)
        self.ai.close();self.controller.stop(save_on_exit=False)
    def __enter__(self):return self
    def __exit__(self,*a):self.close()
