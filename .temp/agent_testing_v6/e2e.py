"""Six real-model-to-real-scheduler loops, with independent tick audit."""
from harness import *
from matrix import created,completed,inspect_protocol,document_run
from oracle import multiset,audit_trajectory,process_errors
from cases import document_case

def manifest():
    return [{'case_id':f'X{i:02}','map':('M01' if i in (1,3) else ('M02' if i in (2,4) else 'M03')),
             'robots':16 if i==6 else 4,'max_steps':2000,'seconds':180,'planning_seconds':3} for i in range(1,7)]

def execute(case,run,fixtures,values,budget):
    k=case['case_id'];i=int(k[1:]);f=next(f for f in fixtures if f['id']==case['map']);p=f['pickup'];q=f['other']
    directory=Path(run)/'e2e'/k;directory.mkdir(parents=True,exist_ok=False)
    spec=read(f['scenario']);spec['robot_count']=case['robots'];scenario=directory/'scenario.json';write(scenario,spec)
    result={'case_id':k,'execution_status':'RUNNING','raw_status':'INCONCLUSIVE','effective_status':'INCONCLUSIVE','evidence':str(directory),'review_status':'PENDING'}
    write(directory/'result.json',result)
    try:
        with Session(scenario,directory,DeepSeek(),values,budget,'e2e') as s:
            errors=[];assignment=[];expected=[];target=None
            if i==3:
                for r in range(1,5):
                    tid=created(s,p,'D2',2);s.business('assign_task',{'task_id':tid,'robot_id':f'R{r}'})
                before=s.snapshot()
                if not (len(before['tasks'])==4 and all(r['task_id'] is not None and not r['loaded'] and r['phase']=='to_pickup' for r in before['robots'])):
                    raise RuntimeError('FIXTURE_INVALID X03 four resources must be occupied before urgent order')
                write(directory/'competition_premise.json',before)
            if i==4:
                target=created(s,p);s.business('assign_task',{'task_id':target,'robot_id':'R1'})
                before=s.snapshot();r3=next(r for r in before['robots'] if r['id']==3)
                if r3['task_id'] is not None:raise RuntimeError('FIXTURE_INVALID X04 R3 not free')
            if i==5:
                busy=created(s,q,'D1');s.business('assign_task',{'task_id':busy,'robot_id':'R3'})
                fs=s.advance(lambda a:any(r['id']==3 and r['loaded'] for r in a['robots']))
                if not any(r['id']==3 and r['loaded'] for r in fs[-1]['robots']):raise RuntimeError('FIXTURE_INVALID X05 R3 not loaded')
                target=created(s,p)
            before=s.snapshot();old_ids={x['id'] for x in before['tasks']};write(directory/'premise.json',before)
            if i in (1,3):expected=[{'pickup_id':p,'delivery_id':'D2','priority':5 if i==3 else 2}]
            if i==2:expected=[{'pickup_id':p,'delivery_id':'D2','priority':2},{'pickup_id':q,'delivery_id':'D1','priority':5}]
            if i==6:expected=[{'pickup_id':p,'delivery_id':'D2','priority':2},{'pickup_id':q,'delivery_id':'D1','priority':2}]
            guard_errors=[];old={t['id']:t for t in before['tasks']}
            def guard(receipt,sim):
                actual=[task_view(t,sim.warehouse) for t in sim.tasks.values() if t.id not in old_ids]
                if any(n>multiset(expected)[key] for key,n in multiset(actual).items()):guard_errors.append('unexpected new task prefix')
                for tid,t in old.items():
                    current=asdict(sim.tasks[tid]);mutable=target is not None and tid==int(target[1:])
                    for field in ('pickup','delivery','priority')+(() if mutable else ('assignment_mode','assignment_robot_id')):
                        if current[field]!=t[field]:guard_errors.append('unexpected original task change')
                    if current['status']=='cancelled' and t['status']!='cancelled':guard_errors.append('unexpected cancellation')
                return not guard_errors
            s.controller.effect_guard=guard
            if i==6:
                document=document_case('F10',f)
                details=document_run(s,{'case_id':'F10','document':document},f)
                errors+=details['business_errors'];expected=[{'pickup_id':p,'delivery_id':'D2','priority':2},{'pickup_id':q,'delivery_id':'D1','priority':2}]
                if details.get('pending'):assignment.append('confirmation pending factual issues review')
            else:
                text={1:'把四号货架的货送二号配送点，创建一次。',
                      2:'蓝色货架送复核台，普通一次；登记货架2送一号配送点，紧急一次。',
                      3:'四号货架送二号配送点，创建一个紧急任务。原有任务的人工指定关系保留。',
                      4:'把这单指定给空闲的R3执行。',5:'这单尽量让R3做，忙碌时允许其他机器人执行。'}[i]
                s.message(text,target)
                if i in (1,3):expected=[{'pickup_id':p,'delivery_id':'D2','priority':5 if i==3 else 2}]
                if i==2:expected=[{'pickup_id':p,'delivery_id':'D2','priority':2},{'pickup_id':q,'delivery_id':'D1','priority':5}]
            after=s.snapshot();new=[x for x in after['task_views'] if int(x['task_id'][1:]) not in old_ids]
            errors+=guard_errors
            if multiset(new)!=multiset(expected):errors.append('agent business task multiset mismatch')
            if i in (4,5):
                t=next(t for t in after['task_views'] if t['task_id']==target)
                if t['assignment_mode']!=('forced' if i==4 else 'preferred') or t['requested_robot']!='R3':errors.append('wrong assignment mode/robot')
            if i==3:
                if after['metrics'].get('preemptions',0)<=before['metrics'].get('preemptions',0):assignment.append('no actual urgent preemption observed')
                if any(t['assignment_mode']!='forced' for t in after['task_views'] if int(t['task_id'][1:]) in old_ids):assignment.append('ordinary forced relation not retained')
            if i==5:
                t=next(t for t in after['task_views'] if t['task_id']==target)
                if t['assigned_robot'] in (None,'R3'):assignment.append('no actual preference fallback observed while R3 busy')
            protocol=inspect_protocol(s)
            process=[] if i==6 else process_errors(s.observed.calls,s.tool_trace,'normal')
            errors+=process
            if not errors and not protocol:
                frames=s.advance(completed);trace=audit_trajectory(frames,s.controller.state()['map'])
                complete=completed(frames[-1])
            else:frames=[after];trace=[];complete=False
            if i==4 and complete:
                target_num=int(target[1:]);executors={r['id'] for frame in frames for r in frame['robots'] if r['task_id']==target_num}
                if executors!={3}:assignment.append('X04 actual execution not exclusively R3')
            result.update(execution_status='COMPLETED',agent_business='FAIL' if errors or protocol else 'PASS',
                          assignment_rules='FAIL' if assignment else 'PASS',trajectory_safety='FAIL' if trace else ('PASS' if len(frames)>1 else 'INCONCLUSIVE'),
                          completion='PASS' if complete else 'INCONCLUSIVE',business_errors=errors,protocol_errors=protocol,
                          assignment_errors=assignment,trajectory_errors=trace,observed_steps=len(frames)-1,
                          response_verdict='PENDING',review_status='PENDING')
            if guard_errors:result['stop_batch']='UNEXPECTED_SIDE_EFFECT'
            if errors or protocol or assignment or trace:result.update(raw_status='FAIL',effective_status='FAIL')
    except Exception as exc:result.update(execution_status='INTERRUPTED',raw_status='TEST_INVALID',effective_status='TEST_INVALID',error=scrub(str(exc),values.get('api_key','')),error_type=type(exc).__name__)
    write(directory/'result.json',result)
    with (Path(run)/'results_raw.jsonl').open('a',encoding='utf-8') as out:out.write(json.dumps(result,ensure_ascii=False)+'\n')
    print(k,result['effective_status'],flush=True);return result
