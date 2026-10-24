"""Follow-up experiments on six frozen 64-robot cases; production files read only."""
from pathlib import Path
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT))
import json,time,hashlib,gzip,datetime,uuid,subprocess,os,csv,argparse,traceback,pickle
from copy import deepcopy,copy
from dataclasses import asdict
from collections import Counter
from simulation import Simulation
from models import Robot,Task
from coordination.contracts import PlanningProfile,Proposal,snapshot_for_planning
from coordination.coordinator import solve
from planning.scalable import plan as lowlevel
from checkers import require,paths_check,business_check
from run_suite import hashes


def dump(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=str),encoding='utf-8')


def canonical(obj):return json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=False)

def state(sim):
    return dict(tick=sim.tick,robots=[asdict(r) for r in sim.robots],tasks=[asdict(t) for t in sim.tasks.values()],
        dirty=sim.dirty,paused=sim.paused,last_progress=sim.last_progress,failed_attempts=sim.failed_attempts,
        assignment=sim.assignment,metrics=sim.metrics,profile=asdict(sim.profile),plan_valid_until=sim.plan_valid_until)


def restore(original,from_start=False):
    folder=Path(original);spec=json.loads((folder/'input.json').read_text(encoding='utf-8'))
    definition=json.loads((folder/'actual_map.json').read_text(encoding='utf-8'))
    result=json.loads((folder/'result.json').read_text(encoding='utf-8'))
    sim=Simulation(spec['seed'],initial_tasks=0,map_id='followup64',map_definition=definition,robot_count=64,profile=PlanningProfile(seconds=8))
    if from_start:
        for t in spec['tasks']:sim.add_task(sim.warehouse.pickups[t['pickup']],sim.warehouse.deliveries[t['delivery']],t['priority'])
        return sim,spec,result,dict(from_start=True,source_case=str(folder))
    saved=json.loads((folder/'final_state.json').read_text(encoding='utf-8'))
    sim.tick=saved['tick']
    sim.robots=[]
    for raw in saved['robots']:
        data=deepcopy(raw)
        for key in ('position','previous','parking'):data[key]=tuple(data[key])
        data['path']=list(map(tuple,data['path']))
        sim.robots.append(Robot(**data))
    sim.tasks={}
    for raw in saved['tasks']:
        data=deepcopy(raw);data['pickup']=tuple(data['pickup']);data['delivery']=tuple(data['delivery'])
        task=Task(**data);sim.tasks[task.id]=task
    sim.next_id=max(sim.tasks,default=0)+1
    sim.metrics=deepcopy(result['metrics']);sim.failed_attempts=0
    sim.paused=False
    sim.dirty=result['terminal']!='wall_limit' or any(t.completed_at==sim.tick for t in sim.tasks.values())
    sim.last_progress=sim.tick
    previous=None;last_progress=0
    with gzip.open(folder/'trace.jsonl.gz','rt',encoding='utf-8') as f:
        for line in f:
            frame=json.loads(line);current=frame['robots']
            if previous is None or any(a[1:3]!=b[1:3] or a[3] in ('picking','unloading') for a,b in zip(previous,current)):
                last_progress=frame['tick']
            previous=current
    sim.last_progress=last_progress
    last_plan=None
    with gzip.open(folder/'plans.jsonl.gz','rt',encoding='utf-8') as f:
        for line in f:last_plan=json.loads(line)
    if last_plan:sim.assignment=last_plan['assignment']
    sim.assert_invariants();business_check(sim)
    require(canonical([asdict(r) for r in sim.robots])==canonical(saved['robots']),'robot checkpoint reconstruction mismatch')
    require(canonical([asdict(t) for t in sim.tasks.values()])==canonical(saved['tasks']),'task checkpoint reconstruction mismatch')
    rows=definition['grid']['rows']
    # Existing suffix safety checked independently even when it needs redispatch.
    paths_check(rows,{r.id:r.position for r in sim.robots},{r.id:r.path for r in sim.robots})
    return sim,spec,result,dict(from_start=False,source_case=str(folder),domain_fields_exact=True,
        initial_tick=sim.tick,initial_completed=sum(t.status=='completed' for t in sim.tasks.values()),
        restored_dirty=sim.dirty,restored_last_progress=last_progress,
        note='Physical robot/task fields verified exactly. Pause cleared as an explicit retry; event/frame history is not used by planning. Full-mode dirty flag reconstructed from terminal reason and final-tick completions.')


def config(mode='scalable_full',coupling='off',seconds=8,window=32,execute=4,candidates=4,external=False):
    return dict(mode=mode,coupling=coupling,seconds=seconds,window=window,execute=execute,candidates=candidates,external=external)

CONFIGS=[config(seconds=8),config(seconds=10),config(coupling='estimated',seconds=10),
    config(coupling='candidate',seconds=10,candidates=8),
    config(mode='rolling',seconds=10,window=64,execute=8),
    config(mode='rolling',seconds=10,window=128,execute=16),
    config(seconds=10,external=True)]


def propose(sim,cfg):
    sim.profile=PlanningProfile(**{k:v for k,v in cfg.items() if k!='external'})
    if not cfg['external']:return solve(sim)
    # Explicitly outside the UI's 10-second profile limit; same low-level solver.
    began=time.monotonic();candidate=snapshot_for_planning(sim);candidate.dispatch()
    starts={r.id:r.position for r in candidate.robots};routes={r.id:candidate.itinerary(r) for r in candidate.robots}
    lower=0
    for rid,points in routes.items():
        p=starts[rid];distance=0
        for w in points:distance+=candidate.warehouse.distance(p,w.position)+w.hold;p=w.position
        lower=max(lower,distance)
    horizon=max(260,lower+max(40,len(starts)*4))
    result=lowlevel(candidate.warehouse,starts,routes,seconds=40,horizon=horizon)
    diagnostics=dict(external=True,status=result.status,expanded=result.expanded,horizon=horizon,budget_seconds=40)
    if result.status!='success':return Proposal(None,False,status=result.status,diagnostics=diagnostics)
    for r in candidate.robots:r.path=result.paths[r.id]
    metrics=deepcopy(sim.metrics);metrics.update(plans=sim.metrics['plans']+1,
        planning_seconds=sim.metrics['planning_seconds']+time.monotonic()-began,last_plan_ms=(time.monotonic()-began)*1000,
        planner=result.method,preemptions=candidate.metrics['preemptions'])
    return Proposal(None,True,candidate.robots,candidate.tasks,candidate.assignment,metrics,'success',diagnostics)


def run_trial(spec,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    started=time.monotonic();sim=None
    row=dict(case_id=spec['case_id'],source_case=spec['source_case'],strategy=spec['strategy'],status='INCONCLUSIVE',
        plan_checks=0,path_points_checked=0,actual_steps_checked=0,failures=0,path_safe=True,profiles_used=[],inputs=spec)
    try:
        sim,oldspec,oldresult,reconstruction=restore(spec['source_case'],spec.get('from_start',False))
        row.update(reconstruction=reconstruction,initial_completed=sum(t.status=='completed' for t in sim.tasks.values()),initial_tick=sim.tick)
        rows=sim.warehouse.export_map()['grid']['rows'];dump(out/'actual_map.json',sim.warehouse.export_map());dump(out/'initial_state.json',state(sim))
        strategy=spec['strategy']
        choices=CONFIGS if strategy=='adaptive' else [spec.get('profile',CONFIGS[0])]
        favorite=choices[0]
        if strategy!='baseline8':sim.dirty=True
        terminal='step_limit'
        with (out/'attempts.jsonl').open('w',encoding='utf-8') as attempts,gzip.open(out/'plans.jsonl.gz','wt',encoding='utf-8',compresslevel=3) as plans,gzip.open(out/'trace.jsonl.gz','wt',encoding='utf-8',compresslevel=3) as trace:
            for _ in range(spec.get('ticks',30000)):
                if time.monotonic()-started>spec.get('wall_seconds',600):terminal='wall_limit';break
                if sim.dirty:
                    success=False
                    configs=[favorite]+[c for c in choices if c!=favorite]
                    for cfg in configs:
                        tick=sim.tick;before=time.monotonic()
                        proposal=propose(sim,cfg)
                        attempt=dict(tick=tick,profile=cfg,success=proposal.success,status=proposal.status,
                                     diagnostics=proposal.diagnostics,elapsed=time.monotonic()-before)
                        attempts.write(json.dumps(attempt,ensure_ascii=False)+'\n');attempts.flush()
                        if not proposal.success:
                            row['failures']+=1
                            name=f'failed_tick_{tick}_attempt_{row["failures"]}'
                            dump(out/(name+'.json'),dict(state=state(sim),attempt=attempt))
                            if time.monotonic()-started>spec.get('wall_seconds',600):break
                            continue
                        candidate=copy(sim);candidate.robots=proposal.robots;candidate.tasks=proposal.tasks
                        origins={r.id:r.position for r in sim.robots};paths={r.id:r.path for r in candidate.robots};points={r.id:candidate.itinerary(r) for r in candidate.robots}
                        row['path_points_checked']+=paths_check(rows,origins,paths,points,proposal.safe_steps is not None)
                        require(sim.apply_proposal(proposal),'successful proposal refused')
                        sim.paused=False;business_check(sim)
                        row['plan_checks']+=1
                        if cfg not in row['profiles_used']:row['profiles_used'].append(cfg)
                        plans.write(json.dumps(dict(tick=tick,profile=cfg,paths=paths,waypoints={rid:[asdict(w) for w in p] for rid,p in points.items()},valid_until=sim.plan_valid_until),ensure_ascii=False)+'\n');plans.flush()
                        favorite=cfg;success=True;break
                    if not success:
                        terminal='all_configurations_unsolved';sim.paused=True;break
                before_robots={r.id:dict(position=r.position,phase=r.phase,task_id=r.task_id,loaded=r.loaded) for r in sim.robots}
                before_tasks={t.id:dict(status=t.status,robot_id=t.robot_id) for t in sim.tasks.values()}
                origins={r.id:r.position for r in sim.robots}
                if sim.plan_valid_until is not None:require(sim.tick<sim.plan_valid_until,'execution beyond rolling certificate')
                require(sim.step(),'step refused despite checked plan')
                row['path_points_checked']+=paths_check(rows,origins,{r.id:[origins[r.id],r.position] for r in sim.robots})
                business_check(sim,(before_robots,before_tasks));row['actual_steps_checked']+=1
                trace.write(json.dumps(dict(tick=sim.tick,robots=[[r.id,*r.position,r.phase,r.loaded,r.task_id,r.next_task_id,r.service_left] for r in sim.robots],tasks=[[t.id,t.status,t.robot_id,t.picked_at,t.completed_at] for t in sim.tasks.values()]),ensure_ascii=False)+'\n')
                if spec.get('respect_progress_watchdog') and sim.paused:
                    terminal='progress_watchdog_pause';break
                if sim.tick%20==0:
                    trace.flush();dump(out/'checkpoint.json',dict(tick=sim.tick,completed=sum(t.status=='completed' for t in sim.tasks.values()),plans=row['plan_checks'],failures=row['failures'],elapsed=time.monotonic()-started,profile=favorite))
                if all(t.status=='completed' for t in sim.tasks.values()):
                    row['status']='PASS';terminal='all_128_tasks_completed';break
        row.update(terminal=terminal,completed=sum(t.status=='completed' for t in sim.tasks.values()),total=len(sim.tasks),tick=sim.tick)
        row['new_completed']=row['completed']-row['initial_completed']
    except Exception as exc:
        row.update(status='FAIL',error=f'{type(exc).__name__}: {exc}',traceback=traceback.format_exc())
        if isinstance(exc,AssertionError):row['path_safe']=False
    finally:
        row['elapsed']=time.monotonic()-started
        if sim is not None:dump(out/'final_state.json',state(sim))
        dump(out/'result.json',row)
    return row


def summarize(out):
    rows=[json.loads(p.read_text(encoding='utf-8')) for p in sorted((out/'cases').glob('*/result.json'))]
    fields=['case_id','source_case','strategy','status','initial_completed','completed','total','initial_tick','tick','elapsed','plan_checks','failures','actual_steps_checked','terminal','error']
    with (out/'summary.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    dump(out/'results.json',rows)
    text=['# 64 台追加测试进度','','| 用例 | 策略 | 状态 | 原完成数 | 最终完成数 | 用时秒 |','| --- | --- | --- | ---: | ---: | ---: |']
    text += [f'| {r["case_id"]} | {r["strategy"]} | {r["status"]} | {r.get("initial_completed", "-")} | {r.get("completed", "-")} | {r["elapsed"]:.2f} |' for r in rows]
    (out/'summary.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    return rows


def execute_child(out,spec):
    folder=out/'cases'/spec['case_id'];folder.mkdir(parents=True,exist_ok=True);dump(folder/'input.json',spec)
    started=time.monotonic()
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONIOENCODING':'utf-8'}
    try:
        p=subprocess.run([sys.executable,'-B',str(__file__),'--child',str(folder/'input.json'),str(folder)],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=spec.get('wall_seconds',600)+90)
        (folder/'stdout.txt').write_text(p.stdout,encoding='utf-8');(folder/'stderr.txt').write_text(p.stderr,encoding='utf-8')
        if not (folder/'result.json').exists():dump(folder/'result.json',dict(case_id=spec['case_id'],source_case=spec['source_case'],strategy=spec['strategy'],status='FAIL',error=p.stderr,elapsed=time.monotonic()-started))
    except subprocess.TimeoutExpired:
        dump(folder/'result.json',dict(case_id=spec['case_id'],source_case=spec['source_case'],strategy=spec['strategy'],status='INCONCLUSIVE',terminal='hard_timeout',elapsed=time.monotonic()-started))
    row=json.loads((folder/'result.json').read_text(encoding='utf-8'));summarize(out)
    print(json.dumps({k:row.get(k) for k in ('case_id','status','completed','total','tick','elapsed','failures','error','terminal')},ensure_ascii=False),flush=True)
    return row


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-dir');parser.add_argument('--phase',choices=['baseline','adaptive','rolling','all'],default='all');parser.add_argument('--only');parser.add_argument('--from-start',action='store_true');args=parser.parse_args()
    original=HERE/'runs/20261020_144032_8fe978'
    out=Path(args.run_dir).resolve() if args.run_dir else HERE/'runs'/('followup64_'+datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y%m%d_%H%M%S'))
    out.mkdir(parents=True,exist_ok=True)
    print('RUN_DIR='+str(out),flush=True)
    if not (out/'source_hashes.json').exists():dump(out/'source_hashes.json',hashes());dump(out/'environment.json',dict(python=sys.version,started=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),original_run=str(original)))
    sources=sorted((original/'cases').glob('EXPERIMENT64-*'))
    dump(out/'source_cases.json',[dict(case_id=p.name,source=str(p),input_sha256=hashlib.sha256((p/'input.json').read_bytes()).hexdigest(),final_state_sha256=hashlib.sha256((p/'final_state.json').read_bytes()).hexdigest()) for p in sources])
    for folder in sources:
        if args.only and args.only not in folder.name:continue
        for strategy in (['baseline8','adaptive'] if args.phase=='all' else ['baseline8'] if args.phase=='baseline' else [args.phase]):
            cid=folder.name+'-'+strategy+('-from-start' if args.from_start else '-resume')
            if (out/'cases'/cid/'result.json').exists():continue
            spec=dict(case_id=cid,source_case=str(folder),strategy=strategy,wall_seconds=600,ticks=30000,from_start=args.from_start)
            if strategy=='rolling':spec['profile']=config(mode='rolling',seconds=10,window=128,execute=16)
            result=execute_child(out,spec)
            if result['status']=='PASS':break
    end=hashes();baseline=json.loads((out/'source_hashes.json').read_text(encoding='utf-8'))
    dump(out/'source_integrity.json',dict(unchanged=baseline==end,changed=[p for p in baseline if baseline[p]!=end.get(p)]))
    summarize(out)

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--child':
        row=run_trial(json.loads(Path(sys.argv[2]).read_text(encoding='utf-8')),sys.argv[3]);print(json.dumps(dict(case_id=row['case_id'],status=row['status']),ensure_ascii=False))
    else:main()