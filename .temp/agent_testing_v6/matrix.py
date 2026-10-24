from harness import *
from oracle import *
from checks import docx
from cases import document_case

def completed(f):return bool(f['tasks']) and all(t['status'] in ('completed','cancelled') for t in f['tasks'])
def created(s,p,d='D2',priority=2):
    r=s.business('create_tasks',{'tasks':[{'pickup_id':p,'delivery_id':d,'priority':priority}]})
    if len(r['actions'])!=1 or r['actions'][0]['outcome']!='applied':raise RuntimeError('FIXTURE_INVALID preparation create')
    return r['actions'][0]['task_id']
def target_view(s,tid):return next(t for t in s.snapshot()['task_views'] if int(t['task_id'][1:])==int(tid[1:]))
def expected_new(case,f):
    p=f['pickup'];q=f['other'];k=case['case_id']
    a=lambda pickup=p,d='D2',v=2:{'pickup_id':pickup,'delivery_id':d,'priority':v}
    if k.startswith('A'):
        if k=='A06':return [a(),a(q,'D1')]
        if k=='A07':return [a()]*3
        if k=='A10':return [a(q,'D1')]
        return [a(v=5 if k=='A04' else (3 if k=='A05' else 2))]
    if k in ('C07',):return [a(v=5)]
    if k in ('C08','D05'):return [a()]*2
    if k=='C09':return [a()]
    if k=='C10':return [a(v=5)]
    if k in ('D01','D08','D09'):return [a()]
    if k=='D04':return [a(q,'D1')]
    v=case.get('variant')
    if v=='clarify_alias':return [a(q)]
    if v in ('create','clarify_destination','dont_repeat','stop_after_write','planning_fault'):return [a()]
    if v=='second_new':return [a()]*2
    if v=='two_levels':return [a(),a(v=4)]
    if v in ('copy_completed','copy_cancel_loaded'):return [a()]
    if v=='long_context':return [a()]
    return []

def inspect_protocol(s):
    errors=[]
    from task_imports.prompts import OUTPUT_TOOL
    schemas={t['function']['name']:t['function']['parameters'] for t in TOOLS+[OUTPUT_TOOL]}
    for c in s.observed.calls:
        for tc in c.get('response',{}).get('tool_calls',[]):
            name=tc.get('function',{}).get('name')
            if name not in schemas:errors.append('unknown tool '+str(name));continue
            try:raw=json.loads(tc['function']['arguments'])
            except (ValueError,KeyError,TypeError):errors.append('invalid arguments JSON');continue
            errors.extend(name+':'+e for e in schema_errors(raw,schemas[name]))
    return errors

def document_run(s,case,f):
    spec=case['document'];name=spec['filename']
    content=docx(spec['lines']) if name.endswith('.docx') else spec['text'].encode()
    (s.directory/name).write_bytes(content)
    from task_imports.documents import read_document
    parsed=read_document(name,content);write(s.directory/'source_truth.json',{'document':parsed,'truth':spec['truth'],'excluded':spec['excluded']})
    upload=s.ai.imports.upload(name,content,s.controller.generation)['draft']
    s.message('',kind='import_extract',document_id=upload['document_id'],**({'instruction':spec['instruction']} if spec.get('instruction') else {}))
    draft=s.ai.imports.draft()['draft'];write(s.directory/'draft_first.json',draft)
    if draft['state']!='ready':return {'business_errors':['extraction did not produce ready draft'],'pending':[]}
    errors=[];pending=[];rows=draft['candidates'];truth=spec['truth'];blocks={b['id']:b['text'] for b in parsed['blocks']}
    errors+=inspect_protocol(s)
    raw_rows=[]
    for observed in s.observed.calls:
        for tc in observed.get('response',{}).get('tool_calls',[]):
            if tc['function']['name']=='propose_import_draft':
                try:raw_rows=json.loads(tc['function']['arguments'])['candidates']
                except (ValueError,KeyError,TypeError):errors.append('invalid raw extraction')
    for t in truth:
        raw_matches=[r for r in raw_rows if any(t['marker'] in blocks.get(b,'') for b in r.get('source_ids',[]))]
        if len(raw_matches)==1:
            for field in ('pickup_id','delivery_id','priority','count','quantity_kind'):
                if raw_matches[0].get(field)!=t[field]:errors.append(t['marker']+':raw model field wrong '+field)
    if len(rows)!=len(truth):errors.append('candidate count does not equal source requirement count')
    matched={}
    for t in truth:
        matches=[r for r in rows if any(t['marker'] in blocks.get(b,'') for b in r['source_ids'])]
        if len(matches)!=1:errors.append('source alignment '+t['marker']);continue
        row=matches[0];matched[t['marker']]=row
        for k in ('pickup_id','delivery_id','priority','count','quantity_kind'):
            if row[k]!=t[k]:errors.append(t['marker']+':wrong '+k+f' {row[k]!r} expected {t[k]!r}')
        for phrase in t.get('constraints',[]):
            if phrase not in ''.join(row['constraints']):errors.append(t['marker']+':missing constraint '+phrase)
        if not t.get('constraints') and row['constraints']:errors.append(t['marker']+':spurious unsupported constraint')
    excluded_text='\n'.join(blocks.get(b,'') for e in draft['excluded'] for b in e['source_ids'])
    for line in spec['excluded']:
        if line.split('：')[0] not in excluded_text:errors.append('missing excluded source '+line.split('：')[0])
    if s.snapshot()['tasks']:errors.append('tasks created before confirmation')
    if errors:return {'business_errors':errors,'pending':pending}
    policy=spec['confirmation']
    if policy=='extract_only':return {'business_errors':[],'pending':[],'semantic_fields':'deterministic source alignment','confirmation':'intentionally not requested'}
    def payload(counts=None):
        d=s.ai.imports.draft()['draft']
        return {'draft_id':d['draft_id'],'expected_revision':d['revision'],'confirmation_id':uuid4().hex,
                'selections':[{'candidate_id':r['candidate_id'],'count':(counts or {}).get(r['candidate_id'],1)} for r in d['candidates']]}
    def rejected(data):
        try:s.ai.imports.commit(data)
        except ValueError:return True
        return False
    if policy=='block_constraints':
        if not rejected(payload()):errors.append('unsupported constraints were not blocked')
        return {'business_errors':errors,'pending':[],'confirmation':'intentionally blocked until explicit acceptance'}
    if isinstance(policy,dict):
        if not rejected(payload()):errors.append('incomplete draft confirmation unexpectedly accepted')
        d=s.ai.imports.draft()['draft'];r=d['candidates'][0]
        changes={**policy,'reviewed':True}
        s.ai.imports.edit({'draft_id':d['draft_id'],'expected_revision':d['revision'],'candidate_id':r['candidate_id'],'changes':changes})
        write(s.directory/'confirmation_edit.json',{'actor':'test_harness_confirmation','frozen_changes':changes})
    # Only an evidence-checked, factual reminder is auto-reviewable. Other issues get a concrete review item.
    for row in s.ai.imports.draft()['draft']['candidates']:
        if row['issues'] and not row['reviewed']:
            safe=all(re.fullmatch(r'.*(?:请核对|请确认|重复|同一路线|相同取送).*',x) and not any(w in x for w in ('未知','不明','歧义','缺少','无法','不确定')) for x in row['issues'])
            if not safe:pending.append({'candidate_id':row['candidate_id'],'issues':row['issues'],'action':'review factual issues against source before confirming'});continue
            d=s.ai.imports.draft()['draft'];s.ai.imports.edit({'draft_id':d['draft_id'],'expected_revision':d['revision'],'candidate_id':row['candidate_id'],'changes':{'reviewed':True}})
    if pending:return {'business_errors':errors,'pending':pending,'confirmation':'requires evidence review'}
    counts={}
    if case['case_id']=='F06':counts={r['candidate_id']:2 for r in s.ai.imports.draft()['draft']['candidates']}
    data=payload(counts);first=s.ai.imports.commit(data);s.wait(first['request_id']);before=s.snapshot()
    if policy=='each_one_retry_original':
        retry=s.ai.imports.commit(data)
        if retry['submission_id']!=first['submission_id'] or s.snapshot()['tasks']!=before['tasks']:errors.append('confirmation replay duplicated/changed tasks')
    planned=sum(x['count'] for x in data['selections'])
    if len(before['tasks'])!=planned:errors.append('wrong confirmed task count')
    if any(not x.get('source') or x['source'].get('kind')!='file_import' for x in before['tasks']):errors.append('missing task provenance')
    write(s.directory/'confirmation.json',{'actor':'test_harness_confirmation','payload':data,'operation':s.ai.imports.operation(first['submission_id'])})
    return {'business_errors':errors,'pending':pending,'confirmation_count':planned}

def run_chat(s,case,f,fixtures):
    k=case['case_id'];variant=case.get('variant');p=f['pickup'];q=f['other'];ids={};association=None;expected_changes={}
    if k.startswith(('B','C')) and k not in ('B09','B10') or k in ('A09','A10','D02','D03','D04','D05','D06','D07','E05','E09') or variant in ('forced_explain','copy_completed','raise4','query_cancelled','copy_cancel_loaded','separate_objects'):
        level=3 if k=='B03' else (4 if k=='B06' or variant=='raise4' else (5 if k in ('B05','C10') else 2))
        ids['first']=created(s,p,priority=level);association=ids['first']
    if k in ('D02','D03') or variant=='separate_objects':ids['target']=created(s,q,'D1',3)
    if k=='B07':created(s,q,'D1')
    if k in ('C03','C07','C10') or variant=='forced_explain':s.business('assign_task',{'task_id':ids['first'],'robot_id':'R3'})
    if k=='C05':s.business('assign_task',{'task_id':ids['first'],'robot_id':'R1'})
    if k in ('B08','C06') or variant=='copy_cancel_loaded':
        fs=s.advance(lambda a:any(r['loaded'] for r in a['robots']))
        if not any(r['loaded'] for r in fs[-1]['robots']):raise RuntimeError('FIXTURE_INVALID loaded premise')
    if k=='C04':
        s.business('assign_task',{'task_id':ids['first'],'robot_id':'R3'})
        fs=s.advance(lambda a:any(r['id']==3 and r['loaded'] for r in a['robots']))
        if not any(r['id']==3 and r['loaded'] for r in fs[-1]['robots']):raise RuntimeError('FIXTURE_INVALID busy R3')
        ids['target']=created(s,q,'D1');association=ids['target']
    if k=='C09' or variant=='query_cancelled':s.business('cancel_tasks',{'task_ids':[ids['first']]})
    if k=='D06' or variant=='copy_completed':
        fs=s.advance(completed)
        if not completed(fs[-1]):raise RuntimeError('FIXTURE_INVALID completed premise')
    if k in ('C01','C05'):
        r3=next(r for r in s.snapshot()['robots'] if r['id']==3)
        if r3['task_id'] is not None and r3['task_id']!=int(ids['first'][1:]):raise RuntimeError('FIXTURE_INVALID R3 busy')
    before=s.snapshot();write(s.directory/'case_initial.json',before)
    expected=expected_new(case,f);guard_errors=[];fixture_errors=[]
    allowed_target=ids.get('target') if k=='D03' else ids.get('first')
    before_by_id={r['id']:r for r in before['tasks']}
    allowed_mutation=k in ('B03','B04','B05','B07','C01','C02','C03','C05','D01','D03') or variant=='raise4'
    def guard(result,sim):
        current=[task_view(t,sim.warehouse) for t in sim.tasks.values() if t.id not in before_by_id]
        if any(n>multiset(expected)[key] for key,n in multiset(current).items()):guard_errors.append('unauthorized new task prefix')
        for tid,old in before_by_id.items():
            actual=asdict(sim.tasks[tid]);allowed=allowed_mutation and allowed_target is not None and tid==int(allowed_target[1:])
            protected=('pickup','delivery')
            if any(actual[x]!=old[x] for x in protected):guard_errors.append('unauthorized original task route modification')
            priority_goals={'B03':4,'B04':5,'B05':5}
            if variant=='raise4':priority_goals[k]=5
            expected_priority=priority_goals.get(k) if allowed else None
            if actual['priority']!=old['priority'] and actual['priority']!=expected_priority:guard_errors.append('unauthorized original priority modification')
            modes={'C01':('forced',3),'C02':('preferred',3),'C03':('auto',None),'C05':('forced',3)}
            desired=modes.get(k) if allowed else None
            if (actual['assignment_mode'],actual['assignment_robot_id'])!=(old['assignment_mode'],old['assignment_robot_id']) and (actual['assignment_mode'],actual['assignment_robot_id'])!=desired:guard_errors.append('unauthorized assignment modification')
            if not allowed and actual['status']=='cancelled' and old['status']!='cancelled':guard_errors.append('unauthorized cancellation')
        return not guard_errors
    s.controller.effect_guard=guard
    call_start=len(s.observed.calls);trace_start=len(s.tool_trace)
    text=case['text'].format(pickup=p,first=ids.get('first',''),target=ids.get('target',''))
    events=[]
    def message(text,association=association):
        ev=s.message(text,association);events.extend(ev);return ev
    if variant in ('inflight_reset','planning_fault','stop_after_write'):
        # Separate challenge executor handles precisely synchronized fault cases.
        return run_race(s,case,f,fixtures,before,events,expected,call_start,trace_start)
    message(text)
    if k=='D01':
        new=[x for x in s.snapshot()['task_views'] if int(x['task_id'][1:]) not in before_by_id]
        if len(new)==1:
            association=new[0]['task_id'];allowed_target=association
            expected[0]['priority']=3
            message('把这单提升一级。',association)
    if k=='D02':message('取消那个。',None)
    if k=='D05':message('查询当前全部任务。',None)
    if k=='D07':s.ai.clear();message('刚才那个，取消掉。',None)
    if k=='D08':
        # Use actual production load lifecycle with the isolated persistence output directory.
        alternate=next(x for x in fixtures if x['id']!=f['id'] and x['pickup']!=p)
        import persistence
        write(persistence.OUTPUTS/'last_scenario.json',read(alternate['scenario']))
        s.controller.submit('load').result(timeout=40);s.ai.sync_scene();s.barrier()
        before=s.snapshot();before_by_id={}
        call_start=len(s.observed.calls);trace_start=len(s.tool_trace)
        expected[:]=[{'pickup_id':alternate['pickup'],'delivery_id':'D2','priority':2}]
        s.controller.effect_guard=guard
        message(text,None)
    if k=='D09' or variant=='long_context':
        new=s.snapshot()['task_views']
        if not new:raise RuntimeError('no task for long-context premise')
        tid=new[0]['task_id']
        spec=case.get('long_context')
        if not spec:raise RuntimeError('FIXTURE_INVALID: long-context input was not frozen')
        note=spec['note']
        if len(note)!=spec['page_chars']:raise RuntimeError('FIXTURE_INVALID: long-context page length')
        for n in range(spec['pages']):message(spec['prefix'].format(page=n+1)+note,None)
        fs=s.advance(completed);message('任务'+tid+'现在完成了吗？请查实时状态。',None)
        summary_calls=sum(c['kind']=='summary' for c in s.observed.calls)
        write(s.directory/'summary_coverage.json',{'required':spec['required_summary_calls'],'actual':summary_calls,
              'pages':spec['pages'],'page_chars':len(note),'production_threshold_changed':False})
        if summary_calls<spec['required_summary_calls']:fixture_errors.append('production summary threshold not exercised')
    if k=='D10':message('刚才那单创建了吗？',None)
    if variant=='clarify_destination':
        write(s.directory/'clarification_first.json',s.snapshot());message('送到二号配送点。',None)
    if variant=='clarify_alias':
        write(s.directory/'clarification_first.json',s.snapshot());message('我指的是登记货架2。',None)
        expected[:]=[{'pickup_id':q,'delivery_id':'D2','priority':2}]
    if variant=='second_new':message('现在明确再下第二个相同新单，四号货架到二号配送点，一次。',None)
    if variant=='dont_repeat':message('别再做了，不要重做，也不要取消已经创建的任务。',None)
    after=s.snapshot();write(s.directory/'case_final.json',after)
    new=[x for x in after['task_views'] if int(x['task_id'][1:]) not in before_by_id]
    errors=list(guard_errors)
    if multiset(new)!=multiset(expected):errors.append('new task multiset differs from frozen intent')
    views={t['task_id']:t for t in after['task_views']}
    t=views.get(allowed_target)
    goals={'B03':('priority',4),'B04':('priority',5),'B05':('priority',5),'B07':('business_phase','cancelled'),
           'C01':('assignment_mode','forced'),'C02':('assignment_mode','preferred'),'C03':('assignment_mode','auto'),
           'C05':('assignment_mode','forced'),'D03':('business_phase','cancelled')}
    if variant=='raise4':goals[k]=('priority',5)
    if k in goals:
        field,value=goals[k]
        if not t or t[field]!=value:errors.append('wrong target '+field)
        if k in ('C01','C02','C05') and (not t or t['requested_robot']!='R3'):errors.append('wrong requested robot')
    relevant=s.observed.calls[call_start:];trace=s.tool_trace[trace_start:]
    process=process_errors(relevant,trace,'direct_ids' if k=='A08' else ('missing' if k=='B10' else 'normal'))
    must_query={'B01':'get_status','B02':'get_status','B08':'get_status','B09':'get_metrics','B10':'get_status','D06':'get_status'}
    if k in must_query and not any(x['name']==must_query[k] for x in trace):process.append('missing required real-time query')
    if k=='B10' and not query_satisfied(trace,'get_status',{'task_id':'T999999999'},'任务不存在'):process.append('missing exact nonexistent target query')
    no_write=k.startswith('E') or k in ('B06','B08','C04','C06','D02','D07','D10') or variant in ('no_write','forced_explain','query_cancelled','separate_objects')
    proposals=[tc for c in relevant for tc in c.get('response',{}).get('tool_calls',[])]
    if no_write and any(x['function']['name'] in WRITES for x in proposals):errors.append('write proposal without authorization')
    return {'business_errors':errors,'process_errors':process,'before':before,'after':after,'expected_new':expected,
            'events':events,'pending':[{'claim':'Chinese response correctness and required clarification','evidence':'provider_calls.json, events.json, tool_trace.json'}],
            'early_stop':bool(guard_errors),'guard_errors':guard_errors,'fixture_errors':fixture_errors}

def run_race(s,case,f,fixtures,before,events,expected,call_start,trace_start):
    variant=case['variant'];real=s.observed.provider
    if variant=='inflight_reset':
        from contextlib import contextmanager
        import ai.provider as provider_module
        entered=threading.Event();release=threading.Event()
        original_client=provider_module.httpx.Client
        def observed_client(*args,**kwargs):
            client=original_client(*args,**kwargs);original_stream=client.stream
            @contextmanager
            def stream(*a,**kw):
                with original_stream(*a,**kw) as response:
                    entered.set()
                    if not release.wait(50):raise RuntimeError('HTTP header handshake release missing')
                    yield response
            client.stream=stream;return client
        provider_module.httpx.Client=observed_client
        try:
            rid=s.ai.launch('message',{'text':case['text'],'generation':s.controller.generation})['request_id']
            if not entered.wait(90):
                s.ai.stop(rid);release.set();events.extend(s.wait(rid))
                return {'business_errors':[],'process_errors':[],'pending':[{'claim':'no response-header handshake; network interruption'}]}
            write(s.directory/'inflight_handshake.json',{'response_headers_received':True,'generation_before':s.controller.generation})
            s.controller.effect_guard=None
            s.controller.submit('reset',{'robot_count':4}).result(timeout=40);s.ai.sync_scene()
            new_scene=s.snapshot();release.set();events.extend(s.wait(rid));after=s.snapshot()
            errors=[] if after['tasks']==new_scene['tasks'] else ['old request wrote into new scene']
            return {'business_errors':errors,'process_errors':[],'pending':[],'response_headers_received':True,'events':events}
        finally:release.set();provider_module.httpx.Client=original_client
    if variant=='stop_after_write':
        class StopOnFollowup:
            def __init__(self):self.n=0
            def chat(self,cfg,msg,tools,token,on_text=None):
                self.n+=1
                if any(m.get('role')=='tool' and '"outcome": "applied"' in m.get('content','') for m in msg):
                    token.event.set();token.check()
                return real.chat(cfg,msg,tools,token,on_text)
        s.observed.provider=StopOnFollowup();events.extend(s.message(case['text']))
        s.observed.provider=real;events.extend(s.message('刚才的创建是否实际生效了？请核对真实任务，不要再创建。'))
        new=s.snapshot()['task_views'];errors=[] if multiset(new)==multiset(expected) else ['write after stop was lost or duplicated']
        return {'business_errors':errors,'process_errors':[],'events':events,'pending':[{'claim':'stop response agrees with ledger','evidence':'provider_calls.json'}]}
    # Inject planning failure at the real Controller planning boundary after model-generated write.
    original=s.controller._plan
    def unavailable():raise RuntimeError('test-only injected planning unavailability')
    s.controller._plan=unavailable
    try:events.extend(s.message(case['text']))
    finally:s.controller._plan=original
    after=s.snapshot();errors=[] if multiset(after['task_views'])==multiset(expected) else ['mixed fault task intent mismatch']
    return {'business_errors':errors,'process_errors':[],'events':events,'pending':[{'claim':'mixed fault explanation','evidence':'events.json'}],'fault_injection':'planning','scope':'mixed'}

def execute(case,repeat,run,fixtures,values,budget,phase):
    k=case['case_id'];directory=Path(run)/'cases'/k/f'repeat_{repeat}'
    directory.mkdir(parents=True,exist_ok=False)
    write(directory/'input.json',case)
    record={'case_id':k,'repeat':repeat,'layer':phase,'execution_status':'RUNNING','raw_status':'INCONCLUSIVE','effective_status':'INCONCLUSIVE','review_status':'PENDING','human_signoff':None,'evidence':str(directory)}
    write(directory/'result.json',record)
    try:
        f=next(f for f in fixtures if f['id']==case['map'])
        with Session(f['scenario'],directory,DeepSeek(),values,budget,phase) as s:
            if case.get('variant')=='doc_corrupt':
                errors=[]
                for filename,content in [('unsupported.pdf',b'%PDF-1.7 fake'),('broken.docx',b'not a zip')]:
                    try:s.ai.imports.upload(filename,content,s.controller.generation);errors.append('corrupt/unsupported file accepted')
                    except ValueError:pass
                details={'business_errors':errors,'pending':[],'local_only':True}
            else:
                details=document_run(s,case,f) if case.get('kind')=='document' else run_chat(s,case,f,fixtures)
                if case.get('kind')=='document' and not details['business_errors'] and not details.get('pending'):
                    from challenges import extra_document_check
                    details['business_errors']+=extra_document_check(s,case)
            protocol=inspect_protocol(s)
            expected_stop=case.get('variant') in ('inflight_reset','stop_after_write')
            network=network_failed(s.observed.calls,expected_stop)
            business=details.get('business_errors',[]);process=details.get('process_errors',[])
            # Absent side effects caused by a failed connection are not established model failures.
            status,stop_reason=evidence_verdict(protocol,business,process,network,details.get('pending'),
                       details.get('fixture_errors',[]),details.get('guard_errors',[]))
            record.update(raw_status=status,effective_status=status,execution_status='COMPLETED',fixture_valid=True,
                          protocol_verdict='FAIL' if protocol else ('INCONCLUSIVE' if network else 'PASS'),
                          business_verdict='INCONCLUSIVE' if network else ('FAIL' if business else 'PASS'),
                          required_process_verdict='INCONCLUSIVE' if network else ('FAIL' if process else 'PASS'),
                          response_verdict='PENDING' if details.get('pending') else 'PASS',network_error=network,
                          details=details,protocol_errors=protocol,review_status='PENDING' if details.get('pending') else 'COMPLETED')
            if details.get('fixture_errors'):record['fixture_valid']=False
            if stop_reason:record['stop_batch']=stop_reason
    except TimeoutError as exc:
        record.update(execution_status='INTERRUPTED',raw_status='INCONCLUSIVE',effective_status='INCONCLUSIVE',error_type=type(exc).__name__,error=str(exc),stop_batch='SESSION_TIME_LIMIT')
    except Exception as exc:
        record.update(execution_status='INTERRUPTED',raw_status='TEST_INVALID',effective_status='TEST_INVALID',error_type=type(exc).__name__,error=scrub(str(exc),values.get('api_key','')))
    write(directory/'result.json',record)
    with (Path(run)/'results_raw.jsonl').open('a',encoding='utf-8') as out:out.write(json.dumps(record,ensure_ascii=False)+'\n')
    print(k,repeat,record['effective_status'],flush=True);return record
