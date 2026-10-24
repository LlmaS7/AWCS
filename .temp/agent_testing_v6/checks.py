"""H/O checks. Scripted decisions are never real-model capability scores."""
from harness import *
from oracle import *
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from io import BytesIO
from zipfile import ZipFile,ZIP_DEFLATED
from xml.sax.saxutils import escape
SSE_RECEIVED={}
class EnvironmentBlocked(Exception):pass

def docx(lines):
    out=BytesIO()
    with ZipFile(out,'w',ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:tbl>'+''.join('<w:tr><w:tc><w:p><w:r><w:t>'+escape(x)+'</w:t></w:r></w:p></w:tc></w:tr>' for x in lines)+'</w:tbl></w:body></w:document>')
    return out.getvalue()

@contextmanager
def sse_server(complete=True,status=200):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            SSE_RECEIVED[self.server.server_port]=SSE_RECEIVED.get(self.server.server_port,0)+1
            self.rfile.read(int(self.headers.get('Content-Length',0)))
            self.send_response(status);self.send_header('Content-Type','text/event-stream');self.end_headers()
            if status!=200:return
            delta={'choices':[{'delta':{'tool_calls':[{'index':0,**call('create_tasks',{'tasks':[{'pickup_id':'P03','delivery_id':'D2'}]})}]},'finish_reason':'tool_calls'}]}
            self.wfile.write(('data: '+json.dumps(delta)+'\n\n').encode())
            if complete:self.wfile.write(b'data: [DONE]\n\n')
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    SSE_RECEIVED[server.server_port]=0
    try:yield f'http://127.0.0.1:{server.server_port}'
    finally:server.shutdown();server.server_close();thread.join(timeout=2)

def must_reject(fn):
    try:fn()
    except (ValueError,ProviderError,Stopped):return True
    raise AssertionError('invalid operation unexpectedly accepted')

def assertion(ok,label):
    if not ok:raise AssertionError(label)

def run_record(root,identity,fn,scope):
    start=time.monotonic()
    try:
        details=fn() or {}; record={'case_id':identity,'status':'PASS','scope':scope,'details':details}
    except (PermissionError,EnvironmentBlocked) as exc:record={'case_id':identity,'status':'BLOCKED','scope':scope,'error':str(exc)}
    except Exception as exc:record={'case_id':identity,'status':'FAIL' if isinstance(exc,AssertionError) else 'TEST_INVALID','scope':scope,'error_type':type(exc).__name__,'error':str(exc)}
    record['seconds']=time.monotonic()-start
    write(root/(identity+'.json'),record);print(identity,record['status'],record.get('error',''),flush=True)
    return record

def selftest(root):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    a={'pickup_id':'P03','delivery_id':'D2','priority':2}
    def pair(ok,bad,label):assertion(ok and bad,label);return {'positive':True,'negative_detected':True}
    def h01():return pair(multiset([a,a])==multiset([a,a]),multiset([a,a])!=multiset([a]),'multiplicity')
    def h02():
        full={'actions':[{'outcome':'applied'},{'outcome':'applied'}]};partial={'actions':[{'outcome':'applied'},{'outcome':'not_executed'}]}
        return pair(receipt_counts(full)['applied']==2,receipt_counts(partial)['applied']==1 and receipt_counts(partial)['not_executed']==1 and classify(network=True)=='INCONCLUSIVE','actual committed prefix vs HTTP outcome')
    def h03():return pair(multiset([a])==multiset([dict(a)]),multiset([a])!=multiset([{**a,'pickup_id':'P04'}]) and multiset([a])!=multiset([{**a,'delivery_id':'D1'}]),'mapping')
    def h04():
        t={'name':'get_status','arguments':{'task_id':'T999'},'error':'任务不存在'}
        return pair(query_satisfied([t],'get_status',{'task_id':'T0999'},'任务不存在'),
                    not query_satisfied([{**t,'error':'network'}],'get_status',{'task_id':'T999'},'任务不存在') and not query_satisfied([t],'get_status',{'task_id':'T998'},'任务不存在'),'domain error vs network/other target')
    def h05():
        c=[{'response':reply(call('assign_task',{'task_id':'T1','robot_id':'R3'}))}]
        return pair(not process_errors([{'response':reply(call('raise_task_priorities',{'changes':[{'task_id':'T1','mode':'increment'}]}))}],[],'increment'), bool(process_errors(c,[],'assignment')),'dependencies')
    def h06():return pair(resolve_target('T2','T1')=='T2',resolve_target(None,'T1',True) is None and resolve_target(None,None) is None,'explicit/ambiguous/cleared object')
    def h07():
        facts={'created':True,'completed':False}
        return pair(not claim_errors([{'fact':'created','value':True}],facts),bool(claim_errors([{'fact':'completed','value':True}],facts)),'claim timing')
    def h08():
        facts={'requested_robot':'R3','exclusive_future_robot':False,'guaranteed_actual_robot':False}
        return pair(not claim_errors([{'fact':'requested_robot','value':'R3'}],facts),len(claim_errors([{'fact':'exclusive_future_robot','value':True},{'fact':'guaranteed_actual_robot','value':True}],facts))==2,'preference/exclusivity guarantee')
    def h09():
        from task_imports.prompts import OUTPUT_TOOL
        schema=OUTPUT_TOOL['function']['parameters']
        return pair(not schema_errors({'candidates':[],'excluded':[]},schema),bool(schema_errors({'candidates':[]},schema)),'required excluded')
    def h10():return pair(not claim_errors([{'fact':'source_delivery','value':'D2'}],{'source_delivery':'D2'}),bool(claim_errors([{'fact':'source_delivery','value':'D1'}],{'source_delivery':'D2'})),'source semantic field')
    def h11():
        from task_imports.schema import candidate_state
        row={'pickup_id':'P03','delivery_id':'D2','count':1,'issues':['核对'], 'reviewed':True,'constraints':[],'ignore_constraints':False}
        return pair(not candidate_state(row),bool(candidate_state({**row,'constraints':['期限']})),'review does not waive constraints')
    def h12():return pair(not occurrence_errors([('c1',1),('c1',2)],[('c1',1),('c1',2)]),occurrence_errors([('c1',1),('c1',1)],[('c1',1),('c1',2)]) and occurrence_errors([('c1',1),('c1',2),('c1',3)],[('c1',1),('c1',2)]),'occurrence identity and remaining effects')
    def h13():
        cfg={'api_key':'synthetic','model':'synthetic','effort':'high'}
        with sse_server(True) as url:
            try:response,_=DeepSeek().chat({**cfg,'base_url':url},[],TOOLS,CancelToken())
            except ProviderError:
                if not SSE_RECEIVED[int(url.rsplit(':',1)[1])]:raise EnvironmentBlocked('HTTP client could not reach own exact loopback SSE fixture') from None
                raise
            assertion(len(response['tool_calls'])==1,'complete SSE')
        with sse_server(False) as url:must_reject(lambda:DeepSeek().chat({**cfg,'base_url':url},[],TOOLS,CancelToken()))
        return {'positive':True,'negative_detected':True,'production_SSE':True}
    def h14():
        b=Budget(root/'budget_fixture',3);b.reserve('protocol','chat');b.reserve('matrix','summary')
        resumed=Budget(root/'budget_fixture',3);assertion(len(resumed.value['reservations'])==2,'reservation recovery')
        return {'positive':True,'negative_detected':len(resumed.value['reservations'])!=0}
    def h15():
        t=CancelToken();t.deadline=time.monotonic()-1;must_reject(t.check)
        return {'deadline_stops':True,'process_cleanup':'owned PlannerWorker.close only'}
    def h16():
        v=reply(call('create_tasks','{bad'));original=deepcopy(v);scrub(v,'fake')
        return pair(v==original,v['tool_calls'][0]['function']['arguments']=='{bad','transparent raw invalid JSON')
    def h17():
        v=scrub({'api_key':'fake-key','headers':{'Authorization':'fake-key'},'reasoning_content':'PRIVATE','content':'fake-key'},'fake-key')
        assertion(v=={'content':'[REDACTED]'} and 'PRIVATE' not in json.dumps(v),'redaction')
        path=root/'recorder_failure_target';path.write_text('file, not a directory',encoding='utf-8')
        provider=Scripted([]);observed=Observed(provider,path)
        try:observed.chat({'api_key':'fake-key'},[],[],CancelToken())
        except OSError:pass
        else:raise AssertionError('recorder write failure swallowed')
        assertion(provider.count==0,'record failure must stop before model call')
        return {'positive':True,'negative_detected':True,'recorder_failure_blocks_send':True}
    def h18():
        from coordination.contracts import snapshot_for_planning
        sim=Simulation(initial_tasks=0);snapshot=snapshot_for_planning(sim)
        import pickle
        blob=pickle.dumps(snapshot)
        return pair(snapshot is not sim,b'api_key' not in blob and b'CancelToken' not in blob,'picklable secret-free snapshot')
    def h19():
        import copy
        m={'width':9,'height':9,'walls':[[0,0]],'shelves':[],'voids':[],'obstacles':[]}
        r={'id':1,'position':[1,1],'phase':'idle','loaded':False,'task_id':None,'service_left':0}
        fs=[{'tick':0,'robots':[r],'tasks':[]},{'tick':1,'robots':[{**r,'position':[2,1]}],'tasks':[]}]
        assertion(not audit_trajectory(fs,m),'valid trace')
        variants=[]
        for pos in ([5,1],[0,0]):
            bad=copy.deepcopy(fs);bad[1]['robots'][0]['position']=pos;assertion(bool(audit_trajectory(bad,m)),'bad movement');variants.append(pos)
        bad=copy.deepcopy(fs);bad[1]['robots'][0]['loaded']=True;assertion(bool(audit_trajectory(bad,m)),'bad loading')
        bad=copy.deepcopy(fs);bad[1]['tick']=3;assertion('tick gap' in audit_trajectory(bad,m),'tick gap')
        collision=copy.deepcopy(fs)
        for frame in collision:frame['robots'].append({**r,'id':2,'position':[2,1]})
        assertion('vertex collision' in audit_trajectory(collision,m),'collision')
        swap=copy.deepcopy(collision);swap[1]['robots'][1]['position']=[1,1]
        assertion('edge swap' in audit_trajectory(swap,m),'edge swap')
        task={'id':1,'pickup':[1,1],'delivery':[3,1],'assignment_mode':'auto','assignment_robot_id':None}
        service=[{'tick':0,'robots':[{**r,'phase':'picking','task_id':1,'service_left':2}],'tasks':[task]},
                 {'tick':1,'robots':[{**r,'phase':'picking','task_id':1,'service_left':1}],'tasks':[task]}]
        assertion(not audit_trajectory(service,m),'valid service')
        bad=copy.deepcopy(service);bad[1]['robots'][0]['service_left']=2
        assertion('service interrupted' in audit_trajectory(bad,m),'service counter')
        bad=copy.deepcopy(service);bad[1]['robots'][0]['position']=[2,1]
        assertion('wrong service point' in audit_trajectory(bad,m),'wrong service location')
        return {'positive':True,'negative_detected':True,'variants':variants}
    def h20():
        from run_agent_suite import report
        d=root/'report_without_key';write(d/'manifest.json',{'source_hashes':sources(),'git_commit':'synthetic','plan_sha256':'synthetic'})
        write(d/'checkpoint.json',{'stages':{},'stop_reason':'SYNTHETIC_SELFTEST'})
        write(d/'fixtures/manifest.json',[])
        path,summary=report(d)
        from validate_driver import validate
        controls=validate(root/'case_driver_controls')
        from regression_v6 import run as regression_v6
        regression_controls=regression_v6(root/'summary_and_stop_controls')
        assertion(all(c['passed'] for c in regression_controls),'v6 summary/stop regression controls')
        return pair(path.exists() and summary['matrix_effective']=={'NOT_RUN':180} and summary['challenge']=={'NOT_RUN':24} and all(c['passed'] for c in controls),summary['acceptance']!='PASS','real report without key and correct/incorrect production-chain controls')
    funcs=[h01,h02,h03,h04,h05,h06,h07,h08,h09,h10,h11,h12,h13,h14,h15,h16,h17,h18,h19,h20]
    return [run_record(root,f'H{i:02}',fn,'synthetic harness regression; detailed coverage in source') for i,fn in enumerate(funcs,1)]

def extraction(pickup,block='b1',count=1,kind='unspecified',constraints=None):
    return {'source_ids':[block],'pickup_id':pickup,'delivery_id':'D2','priority':2,'count':count,
            'quantity_kind':kind,'quantity_text':'','issues':[],'constraints':constraints or [],'notes':[],'overrides':[]}

def offline(root,fixture):
    root=Path(root);root.mkdir(parents=True,exist_ok=True); scenario=fixture['scenario'];p=fixture['pickup'];other=fixture['other']
    def check(n):
        d=root/f'O{n:02}'
        provider=Scripted([])
        if n==25:provider=Scripted([reply(call('create_tasks',{'tasks':[{'pickup_id':p,'delivery_id':'D2'}]}),call('create_tasks',{'tasks':[{'pickup_id':p,'delivery_id':'D2'}]})),reply()])
        if n==30:provider=Scripted([reply(call('unknown_debug',{}),call('create_tasks','{bad')),reply()])
        if n==31:provider=Scripted([reply(*[call('get_status',{}) for _ in range(13)])])
        if n==35:provider=Scripted([reply(call('create_tasks',{'tasks':[{'pickup_id':p,'delivery_id':'D2'}]})),ProviderError('synthetic read timeout')])
        with Session(scenario,d,provider) as s:
            add=lambda items:s.business('create_tasks',{'tasks':items})
            task=lambda level=2: add([{'pickup_id':p,'delivery_id':'D2','priority':level}])['actions'][0]['task_id']
            total=lambda:len(s.snapshot()['tasks'])
            rejected=lambda result:all(a['outcome'] in ('not_executed','rejected') for a in result.get('actions',[])) and bool(result.get('error') or result.get('actions'))
            if n==1:
                a=s.business('get_locations',{});assertion(a['shelf'][0]['pickup_id']==p and total()==0,'locations');return a
            if n in (2,3,4):
                items=[{'pickup_id':p,'delivery_id':'D2',**({'priority':5} if n==4 else {})}]* (3 if n==3 else 1)
                r=add(items);assertion(total()==len(items) and all(x['outcome']=='applied' for x in r['actions']),'legal create')
                assertion(all(x['priority']==(5 if n==4 else 2) for x in s.snapshot()['tasks']),'default/urgent priority');return r
            if 5<=n<=10:
                bad={5:[{'pickup_id':'bad','delivery_id':'D2'}],6:[{'pickup_id':'P99999','delivery_id':'D2'}],
                     7:[{'pickup_id':p}],8:[{'pickup_id':p,'delivery_id':'D2','priority':True}],9:[],
                     10:[{'pickup_id':p,'delivery_id':'D2'},{'pickup_id':'P99999','delivery_id':'D2'}]}[n]
                try:r=add(bad);assertion(rejected(r),'reject invalid create')
                except ValueError:pass
                assertion(total()==0,'zero side effects')
                if n==7:must_reject(lambda:add([{'pickup_id':p,'delivery_id':'D2','extra':1}]))
                if n==8:
                    for v in (0,6):must_reject(lambda v=v:add([{'pickup_id':p,'delivery_id':'D2','priority':v}]))
                if n==9:must_reject(lambda:add([{'pickup_id':p,'delivery_id':'D2'}]*21))
                return {'zero_side_effects':True}
            if n in (25,30,31,35):
                ev=s.message('synthetic scripted provider check')
                assertion(total()==(1 if n in (25,35) else 0),'script effect bound')
                if n in (31,35):assertion(any(e['kind']=='error' for e in ev),'bounded error')
                if n==31:
                    s.observed.provider=Scripted([reply(call('get_status',{}))]*9)
                    count=len(s.observed.calls);again=s.message('synthetic round limit')
                    assertion(len(s.observed.calls)-count==8 and any(e['kind']=='error' for e in again),'8 model request bound')
                return {'events':ev,'new_tasks':total()}
            if n==34:
                with sse_server(False) as url:
                    s.observed.provider=DeepSeek();s.ai.save_settings({'base_url':url,'api_key':'synthetic-local-only','model':'synthetic'})
                    ev=s.message('synthetic incomplete SSE')
                    if not SSE_RECEIVED[int(url.rsplit(':',1)[1])]:raise EnvironmentBlocked('incomplete SSE fixture never received request; cannot score parser')
                assertion(total()==0 and any(e['kind']=='error' for e in ev),'incomplete SSE no write');return {'production_SSE':True,'events':ev}
            if n==36:
                checks=[]
                for status in (401,429,500):
                    with sse_server(True,status) as url:
                        cfg={**s.ai.configuration.snapshot(),'base_url':url}
                        must_reject(lambda:DeepSeek().chat(cfg,[],TOOLS,CancelToken()))
                        if not SSE_RECEIVED[int(url.rsplit(':',1)[1])]:raise EnvironmentBlocked('HTTP status fixture never received request')
                    checks.append(status)
                token=CancelToken();token.cancel();must_reject(token.check)
                assertion(total()==0,'network exceptions no write');return {'statuses':checks,'cancel':True}
            if n in (37,38,39,40):
                upload=s.ai.imports.upload('synthetic.md',f'将四号货架送到2号配送点，一次。'.encode(),s.controller.generation)['draft']
                from task_imports.documents import read_document
                blocks=read_document('synthetic.md',f'将四号货架送到2号配送点，一次。'.encode())['blocks']
                raw={'candidates':[extraction(p,blocks[0]['id'])],'excluded':[]}
                s.observed.provider=Scripted([reply(call('propose_import_draft',raw))])
                s.message('',kind='import_extract',document_id=upload['document_id'])
                draft=s.ai.imports.draft()['draft'];assertion(total()==0 and draft['state']=='ready','no writes while extracting')
                def payload(**kw):return {'draft_id':draft['draft_id'],'expected_revision':draft['revision'],'confirmation_id':uuid4().hex,'selections':[{'candidate_id':'c1','count':1}],**kw}
                if n==37:
                    s.ai.imports.edit({'draft_id':draft['draft_id'],'expected_revision':draft['revision'],'candidate_id':'c1','changes':{'reviewed':True}})
                    assertion(total()==0,'edit no effects');return {'stages':['upload','analysis','edit'],'new_tasks':0}
                if n==38:
                    data=payload();record=s.ai.imports.commit(data);s.wait(record['request_id']);retry=s.ai.imports.commit(data)
                    assertion(total()==1 and retry['submission_id']==record['submission_id'],'confirmation duplicate');return {'first':record,'retry':retry}
                if n==39:
                    data=payload();s.ai.imports.edit({'draft_id':draft['draft_id'],'expected_revision':draft['revision'],'candidate_id':'c1','changes':{'reviewed':True}})
                    must_reject(lambda:s.ai.imports.commit(data))
                    s.controller.submit('reset',{'robot_count':4}).result(timeout=40);s.ai.sync_scene()
                    must_reject(lambda:s.ai.imports.commit(payload()));return {'old_revision':True,'old_scene':True}
                must_reject(lambda:s.ai.imports.commit(payload(selections=[{'candidate_id':'c1','count':21}])))
                from task_imports.schema import validate_extraction
                loc=s.business('get_locations',{})
                for candidate in ({**raw['candidates'][0],'source_ids':[]},{**raw['candidates'][0],'pickup_id':'P99999'}):
                    must_reject(lambda candidate=candidate:validate_extraction({'candidates':[candidate],'excluded':[]},{'blocks':blocks},loc,''))
                for changes in ({'delivery_id':None},{'count':None}):
                    current=s.ai.imports.draft()['draft'];s.ai.imports.edit({'draft_id':current['draft_id'],'expected_revision':current['revision'],'candidate_id':'c1','changes':changes})
                    draft=s.ai.imports.draft()['draft'];must_reject(lambda:s.ai.imports.commit(payload()))
                s.ai.imports.discard({'draft_id':draft['draft_id']})
                content='四号货架送二号配送点，必须由R3执行，期限下午4点。'.encode()
                uploaded=s.ai.imports.upload('constraints.txt',content,s.controller.generation)['draft']
                constraint_blocks=read_document('constraints.txt',content)['blocks']
                row=extraction(p,constraint_blocks[0]['id'],constraints=['必须由R3执行','下午4点前'])
                row['issues']=['请核对执行约束']
                s.observed.provider=Scripted([reply(call('propose_import_draft',{'candidates':[row],'excluded':[]}))])
                s.message('',kind='import_extract',document_id=uploaded['document_id'])
                draft=s.ai.imports.draft()['draft'];must_reject(lambda:s.ai.imports.commit(payload()))
                s.ai.imports.edit({'draft_id':draft['draft_id'],'expected_revision':draft['revision'],'candidate_id':'c1','changes':{'reviewed':True}})
                draft=s.ai.imports.draft()['draft'];must_reject(lambda:s.ai.imports.commit(payload()))
                assertion(total()==0,'unready/constraints no effects');return {'over_limit':True,'missing_source':True,'unknown_location':True,'missing_count':True,'unreviewed_issues':True,'unsupported_constraints_after_review':True}
            tid=task(5 if n in (15,22) else (4 if n==14 else 2))
            if n in (12,20):
                frames=s.advance(lambda f:any(r['loaded'] for r in f['robots']))
                assertion(any(r['loaded'] for r in frames[-1]['robots']),'loaded fixture')
            if n in (11,12):
                r=s.business('cancel_tasks',{'task_ids':[tid]});assertion((r['actions'][0]['outcome']=='applied')==(n==11),'cancellation phase');return r
            if n in (13,14,15):
                change={'task_id':tid,'mode':'set','priority':2} if n==14 else {'task_id':tid,'mode':'increment'}
                r=s.business('raise_task_priorities',{'changes':[change]})
                assertion(r['actions'][0]['outcome']=={13:'applied',14:'not_executed',15:'no_change'}[n],'priority boundary');return r
            if n in (16,17,18,19,20):
                if n==17:
                    s.business('assign_task',{'task_id':tid,'robot_id':'R3'});s.advance(lambda f:any(r['id']==3 and r['loaded'] for r in f['robots']))
                    target=task();assertion(any(r['id']==3 and r['loaded'] for r in s.snapshot()['robots']),'R3 busy')
                    r=s.business('assign_task',{'task_id':target,'robot_id':'R3'});assertion(rejected(r),'busy rejected');return r
                name='set_task_preference' if n==18 else ('release_task_assignment' if n==19 else 'assign_task')
                if n==19:s.business('assign_task',{'task_id':tid,'robot_id':'R3'})
                r=s.business(name,{'task_id':tid,**({} if n==19 else {'robot_id':'R3'})})
                if n==20:assertion(rejected(r),'loaded assignment rejected')
                else:assertion(r['actions'][0]['assignment_mode']=={16:'forced',18:'preferred',19:'auto'}[n],'assignment semantics')
                return r
            if n in (21,22,23,24):
                if n==23:
                    for v in (0,21,True):must_reject(lambda v=v:s.business('copy_task',{'task_id':tid,'count':v}))
                    assertion(total()==1,'copy invalid no effects');return {'variants':[0,21,True]}
                if n==24:s.business('cancel_tasks',{'task_ids':[tid]})
                if n==22:s.business('assign_task',{'task_id':tid,'robot_id':'R3'})
                before=s.snapshot();r=s.business('copy_task',{'task_id':tid,'count':2})
                after=s.snapshot();assertion(total()==3 and all(t['assignment_mode']=='auto' for t in after['tasks'] if t['id']!=1),'copy defaults/count')
                assertion(before['tasks'][0]==after['tasks'][0],'copy leaves original unchanged')
                if n==22:
                    second=task(5);s.business('set_task_preference',{'task_id':second,'robot_id':'R3'})
                    r2=s.business('copy_task',{'task_id':second,'count':1})
                    assertion(r2['actions'][0]['assignment_mode']=='auto' and r2['actions'][0]['priority']==5,'preferred copy clears preference')
                if n==24:
                    second=task();frames=s.advance(lambda f:next(t for t in f['tasks'] if t['id']==int(second[1:]))['status']=='completed')
                    assertion(next(t for t in frames[-1]['tasks'] if t['id']==int(second[1:]))['status']=='completed','completed source fixture')
                    r2=s.business('copy_task',{'task_id':second,'count':1})
                    assertion(r2['actions'][0]['outcome']=='applied','completed source copied')
                return r
            if n in (26,27):
                identity=uuid4().hex;args={'tasks':[{'pickup_id':p,'delivery_id':'D2'}]}
                first=s.business('create_tasks',args,identity)
                if n==26:assertion(s.business('create_tasks',args,identity)==first,'ledger replay')
                else:must_reject(lambda:s.business('create_tasks',{'tasks':[{'pickup_id':other,'delivery_id':'D2'}]},identity))
                assertion(total()==2,'no duplicate effect');return first
            if n==28:
                r=s.business('create_tasks',{'tasks':[{'pickup_id':p,'delivery_id':'D2'}]},generation=-1)
                assertion(total()==1 and r.get('error'),'stale rejected');return r
            if n==29:
                evs=[]
                for reason in ('stop','clear','epoch'):
                    reached=threading.Event();release=threading.Event()
                    def delayed(cfg,msgs,tools,token,on_text):
                        reached.set();assertion(release.wait(5),'release handshake')
                        return reply(call('create_tasks',{'tasks':[{'pickup_id':p,'delivery_id':'D2'}]}))
                    s.observed.provider=Scripted([delayed]);rid=s.ai.launch('message',{'text':'synthetic lifecycle','generation':s.controller.generation})['request_id']
                    assertion(reached.wait(5),'provider in flight')
                    if reason=='stop':s.ai.stop(rid)
                    elif reason=='clear':s.ai.clear()
                    else:s.ai.save_settings({'timeout':301})
                    release.set();evs.append({'variant':reason,'events':s.wait(rid)})
                    assertion(total()==1,'stale lifecycle response cannot write')
                return {'lifecycle_handshake':evs}
            if n in (32,33):
                # Real executor, isolated pre-start Simulation. Inject failure exactly at planning yield.
                from ai.executor import BusinessExecutor
                class C:
                    generation=0
                    def __init__(self):self.sim=Simulation(initial_tasks=0,map_definition=read(scenario)['map_definition'],robot_count=4)
                    def _publish(self):pass
                c=C();executor=BusinessExecutor(c)
                iterator=executor.iterate({'name':'create_tasks','arguments':{'tasks':[{'pickup_id':p,'delivery_id':'D2'}]*(2 if n==33 else 1)},'generation':0,'operation_id':uuid4().hex})
                next(iterator)
                try:iterator.throw(RuntimeError('synthetic planning failure'))
                except StopIteration as finished:r=finished.value
                assertion(len(c.sim.tasks)==1 and r['actions'][0]['outcome']=='applied' and r['actions'][0]['planning']=='unavailable','applied retained')
                if n==33:assertion(r['actions'][1]['outcome']=='not_executed','remaining stopped')
                return {'fault_injection':'planning yield','receipt':r}
            raise AssertionError('unimplemented offline case')
    return [run_record(root,f'O{i:02}',lambda i=i:check(i),'production actor chain, except O32/O33 direct real executor with explicit planning fault') for i in range(1,41)]
