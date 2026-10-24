from pathlib import Path
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import json, time, traceback, gzip, statistics
from dataclasses import asdict
from copy import deepcopy
from checkers import require, paths_check, business_check
from simulation import Simulation
from coordination.contracts import PlanningProfile, RequestKey, snapshot_for_planning


def dump(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding='utf-8')


def execute(spec,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    start=time.monotonic()
    row=dict(case_id=spec['case_id'],stage=spec.get('stage','P4'),status='INCONCLUSIVE',
             assignment_correct=None,path_safe=True,tasks_completed=False,plan_checks=0,path_points_checked=0,
             actual_steps_checked=0,planning_times=[],inputs=spec)
    sim=None
    try:
        if spec.get('kind')=='probe':
            from map_studio.bridge import inspect_map,probe
            definition=json.loads(Path(spec['map_file']).read_text(encoding='utf-8'))
            analysis=inspect_map(definition);value=probe(definition,spec['robots'],spec['seed'])
            row.update(status='PASS' if value['status']=='passed' else 'INCONCLUSIVE',details=dict(analysis=analysis,probe=value),path_safe=None)
            return row
        if spec.get('kind')=='worker':
            from coordination.worker import PlannerWorker
            sim=Simulation(7,initial_tasks=0,map_id='worker-test',map_definition=json.loads(Path(spec['map_file']).read_text()),robot_count=2)
            sim.add_task(sim.warehouse.pickups[0],sim.warehouse.deliveries[0],2)
            worker=PlannerWorker()
            try:
                key=RequestKey('test',0,0,sim.tick,1,sim.warehouse.topology.map_hash)
                worker.submit(key,snapshot_for_planning(sim))
                result=None
                while result is None and time.monotonic()-start<20:
                    result=worker.poll()
                    time.sleep(.02)
                require(result is not None,'worker did not respond')
                returned,proposal,error=result
                require(returned==key and not error and proposal.success,f'worker error: {error}')
                require(sim.apply_proposal(proposal),'worker proposal rejected')
                row['path_points_checked']+=paths_check(sim.warehouse.export_map()['grid']['rows'],{r.id:r.position for r in sim.robots},
                    {r.id:r.path for r in sim.robots},{r.id:sim.itinerary(r) for r in sim.robots})
                row['plan_checks']=1;row['status']='PASS'
            finally:worker.close()
            return row
        definition=json.loads(Path(spec['map_file']).read_text(encoding='utf-8'))
        profile=PlanningProfile(mode=spec.get('mode','scalable_full'),coupling=spec.get('coupling','off'),
            seconds=spec.get('plan_seconds',3),window=32,execute=4)
        sim=Simulation(spec['seed'],initial_tasks=0,map_id=spec['case_id'],map_definition=definition,robot_count=spec['robots'],profile=profile)
        frozen=sim.warehouse.export_map();rows=frozen['grid']['rows'];dump(out/'actual_map.json',frozen)
        import hashlib
        row['actual_map_sha256']=hashlib.sha256(json.dumps(frozen,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        workload=spec['tasks'];cursor=0
        terminal='step_limit'
        with gzip.open(out/'trace.jsonl.gz','wt',encoding='utf-8') as trace, gzip.open(out/'plans.jsonl.gz','wt',encoding='utf-8') as plans:
            for _ in range(spec.get('ticks',6000)):
                while cursor<len(workload) and workload[cursor]['tick']<=sim.tick:
                    task=workload[cursor]
                    sim.add_task(sim.warehouse.pickups[task['pickup']],sim.warehouse.deliveries[task['delivery']],task['priority'])
                    cursor+=1
                if sim.dirty:
                    began=time.monotonic()
                    success=sim.ensure_plan()
                    row['planning_times'].append(time.monotonic()-began)
                    if not success:
                        terminal='no_safe_plan_within_budget';row['failure_handled_safely']=bool(sim.paused)
                        break
                    origins={r.id:r.position for r in sim.robots};paths={r.id:r.path for r in sim.robots};points={r.id:sim.itinerary(r) for r in sim.robots}
                    row['path_points_checked']+=paths_check(rows,origins,paths,points,sim.profile.mode=='rolling')
                    row['plan_checks']+=1
                    plans.write(json.dumps(dict(tick=sim.tick,origins=origins,paths=paths,waypoints={r:[asdict(w) for w in v] for r,v in points.items()},assignment=sim.assignment,valid_until=sim.plan_valid_until),ensure_ascii=False)+'\n');plans.flush()
                before_robots={r.id:dict(position=r.position,phase=r.phase,task_id=r.task_id,loaded=r.loaded) for r in sim.robots}
                before_tasks={t.id:dict(status=t.status,robot_id=t.robot_id) for t in sim.tasks.values()}
                origins={r.id:r.position for r in sim.robots}
                if not sim.step():
                    terminal='paused_or_step_refused';break
                row['path_points_checked']+=paths_check(rows,origins,{r.id:[origins[r.id],r.position] for r in sim.robots})
                business_check(sim,(before_robots,before_tasks));row['actual_steps_checked']+=1
                trace.write(json.dumps(dict(tick=sim.tick,robots=[[r.id,*r.position,r.phase,r.loaded,r.task_id,r.next_task_id,r.service_left] for r in sim.robots],tasks=[[t.id,t.status,t.robot_id,t.picked_at,t.completed_at] for t in sim.tasks.values()]),ensure_ascii=False)+'\n')
                if sim.tick%20==0:
                    trace.flush();dump(out/'checkpoint.json',dict(tick=sim.tick,completed=sum(t.status=='completed' for t in sim.tasks.values()),plans=row['plan_checks']))
                if cursor==len(workload) and all(t.status=='completed' for t in sim.tasks.values()):
                    terminal='all_tasks_completed';row.update(status='PASS',tasks_completed=True);break
                if time.monotonic()-start>spec.get('wall_seconds',85):
                    terminal='wall_limit';break
        m=sim.snapshot().metrics
        row.update(tick=sim.tick,completed=m['completed'],total=m['total'],submitted=cursor,scheduled=len(workload),
                   remaining=m['total']-m['completed'],terminal=terminal,message=sim.message,
                   metrics=m,all_parked=all(r.position==r.parking for r in sim.robots),
                   final_tasks=[asdict(t) for t in sim.tasks.values()])
    except Exception as exc:
        row.update(status='FAIL',error=f'{type(exc).__name__}: {exc}',traceback=traceback.format_exc())
        if isinstance(exc,AssertionError):row['path_safe']=False
    finally:
        row['elapsed']=time.monotonic()-start
        times=row['planning_times']
        if times:
            row['planning_p50']=statistics.median(times);row['planning_p95']=sorted(times)[min(len(times)-1,int(.95*len(times)))];row['planning_max']=max(times)
        if sim is not None:
            dump(out/'final_state.json',dict(tick=sim.tick,message=sim.message,robots=[asdict(r) for r in sim.robots],tasks=[asdict(t) for t in sim.tasks.values()]))
        dump(out/'result.json',row)
    return row

if __name__=='__main__':
    spec=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    result=execute(spec,sys.argv[2])
    print(json.dumps({k:result.get(k) for k in ('case_id','status','completed','total','tick','elapsed','error','terminal')},ensure_ascii=False),flush=True)