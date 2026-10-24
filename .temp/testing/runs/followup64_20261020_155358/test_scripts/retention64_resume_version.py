"""Experimental execution-policy variant; production code remains unchanged."""
from pathlib import Path
import sys,time,json,gzip,traceback,subprocess,os,datetime
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE))
from followup64 import restore,state,dump,propose,config,summarize
from checkers import require,paths_check,business_check
from coordination.contracts import PlanningProfile,snapshot_for_planning,Proposal
from scheduler import minimum_assignment
from planning.scalable import plan as coordinated


def keep_idle_parking(sim,seconds=20):
    began=time.monotonic();candidate=snapshot_for_planning(sim);candidate.dispatch()
    locked={r.id:r.position for r in candidate.robots if r.task_id is None and r.next_task_id is None and r.position in candidate.warehouse.parking}
    used=set(locked.values());parks=[p for p in candidate.warehouse.parking if p not in used]
    other=[r for r in candidate.robots if r.id not in locked]
    penalty=candidate.warehouse.width*candidate.warehouse.height*64+1
    costs=[]
    for r in other:
        future=candidate.tasks.get(r.next_task_id or r.task_id)
        origin=future.delivery if future else r.position
        costs.append([candidate.warehouse.distance(p,origin)+penalty*candidate.warehouse.topology.parking_risk(p) for p in parks])
    chosen=minimum_assignment(costs)
    for r in candidate.robots:
        if r.id in locked:r.parking=locked[r.id]
    for r,col in zip(other,chosen):r.parking=parks[col]
    starts={r.id:r.position for r in candidate.robots};routes={r.id:candidate.itinerary(r) for r in candidate.robots}
    lower=0
    for rid,points in routes.items():
        p=starts[rid];length=0
        for w in points:length+=candidate.warehouse.distance(p,w.position)+w.hold;p=w.position
        lower=max(lower,length)
    result=coordinated(candidate.warehouse,starts,routes,seconds=seconds,horizon=max(260,lower+256))
    diag=dict(status=result.status,locked_idle_parks=len(locked),expanded=result.expanded,budget_seconds=seconds)
    if result.status!='success':return Proposal(None,False,status=result.status,diagnostics=diag)
    for r in candidate.robots:r.path=result.paths[r.id]
    metrics=dict(sim.metrics);metrics.update(plans=sim.metrics['plans']+1,planning_seconds=sim.metrics['planning_seconds']+time.monotonic()-began,last_plan_ms=(time.monotonic()-began)*1000,planner='SIPP-stable-idle-parking')
    return Proposal(None,True,candidate.robots,candidate.tasks,candidate.assignment,metrics,'success',diag)


def trial(spec,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);started=time.monotonic();sim=None
    row=dict(case_id=spec['case_id'],source_case=spec['source_case'],strategy='retain_safe_suffix',status='INCONCLUSIVE',
        plan_checks=0,path_points_checked=0,actual_steps_checked=0,failures=0,retentions=0,stable_parking_attempts=0,path_safe=True)
    try:
        sim,oldspec,oldresult,reconstruction=restore(spec['source_case'])
        row.update(initial_tick=sim.tick,initial_completed=sum(t.status=='completed' for t in sim.tasks.values()),reconstruction=reconstruction,inputs=spec)
        rows=sim.warehouse.export_map()['grid']['rows'];dump(out/'actual_map.json',sim.warehouse.export_map());dump(out/'initial_state.json',state(sim))
        sim.dirty=True;retain_until=0;terminal='step_limit'
        with gzip.open(out/'trace.jsonl.gz','wt',encoding='utf-8',compresslevel=3) as trace,gzip.open(out/'plans.jsonl.gz','wt',encoding='utf-8',compresslevel=3) as plans,(out/'attempts.jsonl').open('w',encoding='utf-8') as attempts:
            def check_current(label):
                origins={r.id:r.position for r in sim.robots};paths={r.id:r.path for r in sim.robots};points={r.id:sim.itinerary(r) for r in sim.robots}
                row['path_points_checked']+=paths_check(rows,origins,paths,points)
                row['plan_checks']+=1
                plans.write(json.dumps(dict(tick=sim.tick,method=label,paths=paths,waypoints={rid:[dict(position=w.position,hold=w.hold,delivery=w.delivery,urgent=w.urgent) for w in ws] for rid,ws in points.items()}),ensure_ascii=False)+'\n');plans.flush()
            for _ in range(30000):
                if time.monotonic()-started>spec.get('wall_seconds',600):terminal='wall_limit';break
                if retain_until and sim.tick>=retain_until:sim.dirty=True;retain_until=0
                if sim.dirty:
                    if retain_until>sim.tick:
                        check_current('certified suffix after service completion');sim.dirty=False;sim.paused=False
                    else:
                        began=time.monotonic();proposal=propose(sim,config(seconds=10))
                        attempts.write(json.dumps(dict(tick=sim.tick,method='stock_full_10s',status=proposal.status,success=proposal.success,diagnostics=proposal.diagnostics,elapsed=time.monotonic()-began))+'\n');attempts.flush()
                        if proposal.success:
                            require(sim.apply_proposal(proposal),'proposal refused');sim.paused=False;check_current('stock_full_10s')
                        else:
                            row['failures']+=1
                            try:
                                check_current('retained certified remaining full routes')
                                mobile=any(r.service_left>0 or any(p!=r.position for p in r.path[1:]) for r in sim.robots)
                                require(mobile,'no further progress on retained suffix')
                            except AssertionError as suffix_error:
                                row['stable_parking_attempts']+=1
                                began=time.monotonic();proposal=keep_idle_parking(sim,20)
                                attempts.write(json.dumps(dict(tick=sim.tick,method='experimental_stable_idle_parking_20s',status=proposal.status,success=proposal.success,diagnostics=proposal.diagnostics,elapsed=time.monotonic()-began,suffix_error=str(suffix_error)))+'\n');attempts.flush()
                                if not proposal.success:terminal='no_safe_recovery';break
                                require(sim.apply_proposal(proposal),'parking variant refused');sim.paused=False;check_current('experimental stable idle parking')
                            else:
                                row['retentions']+=1;retain_until=sim.tick+32;sim.dirty=False;sim.paused=False
                oldrobots={r.id:dict(position=r.position,phase=r.phase,task_id=r.task_id,loaded=r.loaded) for r in sim.robots}
                oldtasks={t.id:dict(status=t.status,robot_id=t.robot_id) for t in sim.tasks.values()};origins={r.id:r.position for r in sim.robots}
                require(sim.step(),'step refused');row['actual_steps_checked']+=1
                row['path_points_checked']+=paths_check(rows,origins,{r.id:[origins[r.id],r.position] for r in sim.robots});business_check(sim,(oldrobots,oldtasks))
                trace.write(json.dumps(dict(tick=sim.tick,robots=[[r.id,*r.position,r.phase,r.loaded,r.task_id,r.next_task_id,r.service_left] for r in sim.robots],tasks=[[t.id,t.status,t.robot_id,t.picked_at,t.completed_at] for t in sim.tasks.values()]),ensure_ascii=False)+'\n')
                if sim.tick%20==0:trace.flush();dump(out/'checkpoint.json',dict(tick=sim.tick,completed=sum(t.status=='completed' for t in sim.tasks.values()),retentions=row['retentions'],elapsed=time.monotonic()-started))
                if all(t.status=='completed' for t in sim.tasks.values()):row['status']='PASS';terminal='all_128_tasks_completed';break
        row.update(terminal=terminal,completed=sum(t.status=='completed' for t in sim.tasks.values()),total=len(sim.tasks),tick=sim.tick)
        row['new_completed']=row['completed']-row['initial_completed']
    except Exception as exc:
        row.update(status='FAIL',error=f'{type(exc).__name__}: {exc}',traceback=traceback.format_exc())
    finally:
        row['elapsed']=time.monotonic()-started
        if sim is not None:dump(out/'final_state.json',state(sim))
        dump(out/'result.json',row)
    return row


def main(out):
    out=Path(out);original=HERE/'runs/20261020_144032_8fe978/cases'
    for folder in sorted(original.glob('EXPERIMENT64-*')):
        if 'experimental_128x96' in folder.name:continue
        cid=folder.name+'-retention-resume';target=out/'cases'/cid;target.mkdir(parents=True,exist_ok=True)
        spec=dict(case_id=cid,source_case=str(folder),wall_seconds=600);dump(target/'input.json',spec)
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONIOENCODING':'utf-8'}
        try:
            p=subprocess.run([sys.executable,'-B',str(__file__),'--child',str(target/'input.json'),str(target)],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=660)
            (target/'stdout.txt').write_text(p.stdout,encoding='utf-8');(target/'stderr.txt').write_text(p.stderr,encoding='utf-8')
        except subprocess.TimeoutExpired:dump(target/'result.json',dict(case_id=cid,source_case=str(folder),strategy='retain_safe_suffix',status='INCONCLUSIVE',terminal='hard_timeout',elapsed=660))
        row=json.loads((target/'result.json').read_text(encoding='utf-8'));summarize(out)
        print(json.dumps({k:row.get(k) for k in ('case_id','status','completed','total','elapsed','retentions','stable_parking_attempts','terminal','error')},ensure_ascii=False),flush=True)

if __name__=='__main__':
    if sys.argv[1]=='--child':trial(json.loads(Path(sys.argv[2]).read_text(encoding='utf-8')),sys.argv[3])
    else:main(sys.argv[1])