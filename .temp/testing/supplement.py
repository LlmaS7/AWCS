"""Supplemental boundary, rule and independent trace audits. Run after main batch."""
from pathlib import Path
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import json,random,time,gzip,traceback,hashlib,itertools
from copy import deepcopy
from dataclasses import asdict
from core import Recorder,new_sim,add,advance,physical
from checkers import Grid,require,paths_check,single_oracle,joint_oracle,business_check
from models import Waypoint
from planning.reservations import Reservations
from planning.sipp import search
from planning.scalable import plan
from coordination.contracts import PlanningProfile,Proposal


class SupplementRecorder(Recorder):
    def case(self,case_id,stage,fn,inputs=None):
        began=time.monotonic()
        row=dict(case_id=case_id,stage=stage,inputs=inputs)
        try:
            details=fn() or {}
            row.update(status=details.pop('_status','PASS'),details=details)
        except Exception as exc:
            row.update(status='FAIL',error=f'{type(exc).__name__}: {exc}',traceback=traceback.format_exc())
            (self.out/'counterexamples'/(case_id+'.json')).write_text(json.dumps(row,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
        row['elapsed']=time.monotonic()-began
        self.file.write(json.dumps(row,ensure_ascii=False,default=str)+'\n');self.file.flush();self.rows.append(row)
        if row['status']!='PASS':print(case_id,row['status'],row.get('error',row.get('details')),flush=True)
        return row

def run(out):
    out=Path(out);rec=SupplementRecorder(out)
    from map_studio.generator import generate
    from map_format import validate_map
    invalids=[('width',47),('width',129),('height',39),('height',97),('robots',0),('robots',65),
        ('seed',-1),('seed',2147483648),('aisle',1),('aisle',7),('density',24),('density',86),
        ('obstacles',-1),('obstacles',81),('shape','unknown'),('robots',True),('seed',1.5)]
    for field,value in invalids:
        def reject(field=field,value=value):
            try:generate(**{field:value})
            except ValueError:return
            raise AssertionError('invalid generator parameter accepted')
        rec.case(f'G-invalid-{field}-{value}','P4-boundary',reject,dict(field=field,value=value))
    for field,value in [('width',48),('width',128),('height',40),('height',96),('robots',1),('robots',64),
                         ('aisle',2),('aisle',6),('density',25),('density',85),('obstacles',0),('obstacles',80),('seed',0),('seed',2147483647)]:
        def accepted(field=field,value=value):
            params=dict(width=96,height=64,robots=16,seed=20261018,shape='rectangle',aisle=3,density=65,obstacles=20)
            params[field]=value
            d=generate(**params);validate_map(d)
            require(d['metadata']['parameters']==params,'parameters not preserved')
        rec.case(f'G-boundary-{field}-{value}','P4-boundary',accepted,dict(field=field,value=value))
    for path in sorted((out.parent.parent/'datasets/maps').glob('*.json')):
        def static(path=path):
            d=json.loads(path.read_text(encoding='utf-8'));starts=list(map(tuple,d['points']['starts']));parking=set(map(tuple,d['points']['parking']))
            require(set(starts)<=parking,'start not parking')
            require(len(starts)>=d['robots']['max_count'] and len(parking)>=d['robots']['max_count'],'capacity exceeds endpoints')
            connected=set()
            for p in starts:
                if connected:require(any(abs(p[0]-q[0])+abs(p[1]-q[1])==1 for q in connected),'start prefix disconnected')
                connected.add(p)
            groups=[set(map(tuple,d['points'][k])) for k in ('parking','pickups','deliveries')]
            require(all(not groups[i]&groups[j] for i in range(3) for j in range(i)),'business point groups overlap')
        rec.case('G-independent-'+path.stem,'P4-static-audit',static)

    def busy_preference():
        sim=new_sim(2);first=add(sim,3);sim.set_assignment(first,'forced',1);sim.dispatch()
        second=add(sim,2,1,1);sim.set_assignment(second,'preferred',1);sim.dispatch();business_check(sim)
        require(sim.tasks[first].robot_id==1 and sim.tasks[second].robot_id==2,'busy preference blocked free executor')
    rec.case('B07-busy-soft-fallback','P2-supplement',busy_preference)
    def reservation_completion():
        sim=new_sim(1);first=add(sim);advance(sim,lambda:sim.robots[0].phase=='picking')
        second=add(sim,5,1,1);sim.dispatch();require(sim.robots[0].next_task_id==second,'no reservation')
        advance(sim,lambda:all(t.status=='completed' for t in sim.tasks.values()))
        require(sim.tasks[first].completed_at<=sim.tasks[second].picked_at,'reservation violated custody order')
    rec.case('B04-reserved-task-completes','P2-supplement',reservation_completion)
    def forced_kept():
        sim=new_sim(1);first=add(sim);sim.set_assignment(first,'forced',1);sim.dispatch()
        urgent=add(sim,5,1,1);sim.dispatch()
        require(sim.tasks[first].assignment_robot_id==1 and sim.tasks[first].status=='pending','forced relation lost on preemption')
        advance(sim,lambda:all(t.status=='completed' for t in sim.tasks.values()))
        require(sim.tasks[first].robot_id==1 and sim.tasks[urgent].completed_at<=sim.tasks[first].completed_at,'forced recovery failed')
    rec.case('B-forced-preemption-recovery','P2-supplement',forced_kept)
    def duplicate_endpoints():
        sim=new_sim(4)
        for _ in range(6):add(sim,2)
        advance(sim,lambda:all(t.status=='completed' for t in sim.tasks.values()),limit=300)
        return dict(completed=6,tick=sim.tick)
    rec.case('F03-shared-business-endpoints','P5-supplement',duplicate_endpoints)
    def owner_mutation():
        from coordination.coordinator import solve
        sim=new_sim(2);tid=add(sim);advance(sim,lambda:sim.tasks[tid].status=='to_delivery')
        proposal=solve(sim);require(proposal.success,'fixture solve failed')
        task=proposal.tasks[tid];task.robot_id=1 if task.robot_id==2 else 2
        before=physical(sim)
        try:sim.apply_proposal(proposal)
        except (AssertionError,ValueError):pass
        else:raise AssertionError('loaded custody mutation accepted')
        require(physical(sim)==before,'mutation rejection changed state')
    rec.case('F-forged-loaded-custody','P5-supplement',owner_mutation)

    for seed in range(100):
        rng=random.Random(600000+seed);size=rng.choice([3,4,5]);h=16
        rows=[list('.'*size) for _ in range(size)]
        cells=[(x,y) for y in range(size) for x in range(size)]
        start=cells[0];goals=rng.sample(cells[1:],3)
        for p in rng.sample([p for p in cells if p not in goals+[start]],min(2,len(cells)-4)):rows[p[1]][p[0]]='#'
        rows=[''.join(r) for r in rows];grid=Grid(rows)
        points=[Waypoint(goals[0],rng.randrange(3),True,True),Waypoint(goals[1],rng.randrange(3),True,False),Waypoint(goals[2])]
        vertices=set();edges=set();reservations=Reservations()
        for _ in range(4):
            p=rng.choice(cells);t=rng.randrange(h+1);vertices.add((p,t));reservations.block(p,t,t)
        def compare(rows=rows,grid=grid,points=points,vertices=vertices,edges=edges,reservations=reservations,start=start,h=h):
            expected=single_oracle(grid,start,points,vertices,edges,h)
            result=search(grid,start,points,reservations,time.monotonic()+3,h)
            require((expected is None)==(result is None),f'feasibility {expected}, {result}')
            if result:
                require(result[1]==expected,f'cost {expected} != {result[1]}')
                paths_check(rows,{1:start},{1:result[0]},{1:points})
            return dict(expected=expected,actual=None if result is None else result[1])
        rec.case(f'SIPP-obstacles-{seed:03}','P3-supplement',compare,dict(rows=rows,start=start,points=[asdict(w) for w in points],vertices=sorted(vertices),horizon=h))

    for seed in range(20):
        rng=random.Random(700000+seed);grid=Grid(['....']*4);selected=rng.sample([(x,y) for y in range(4) for x in range(4)],4)
        starts,goals=selected[:2],selected[2:];h=10
        def joint(starts=starts,goals=goals,h=h,grid=grid):
            oracle=joint_oracle(grid,starts,goals,h)
            origins={i+1:p for i,p in enumerate(starts)};points={i+1:[Waypoint(p)] for i,p in enumerate(goals)}
            result=plan(grid,origins,points,seconds=1,horizon=h)
            if result.status=='success':
                require(oracle is not None,'claimed finite-horizon impossible solution')
                paths_check(grid.rows,origins,result.paths,points)
            return dict(oracle=oracle,status=result.status,coverage_gap=(oracle is not None and result.status!='success'),_status='INCONCLUSIVE' if oracle is not None and result.status!='success' else 'PASS')
        rec.case(f'JOINT-random-{seed:02}','P3-supplement',joint,dict(starts=starts,goals=goals,horizon=h))

    for mode in ('off','estimated','candidate'):
        def prefix(mode=mode):
            from coordination.contracts import snapshot_for_planning
            from coordination.coordinator import solve
            sim=new_sim(4)
            for p in (1,5,4,2,5,3):add(sim,p,pickup=p%2,delivery=(p+1)%2)
            baseline=snapshot_for_planning(sim);baseline.dispatch()
            sim.profile=PlanningProfile(coupling=mode,seconds=3)
            proposal=solve(sim);require(proposal.success,'coupling fixture not solved')
            require(proposal.assignment['priority_prefix']==baseline.assignment['priority_prefix'],'coupling degraded protected prefix')
            require(sim.apply_proposal(proposal),'coupling proposal rejected')
            paths_check(sim.warehouse.export_map()['grid']['rows'],{r.id:r.position for r in sim.robots},
                        {r.id:r.path for r in sim.robots},{r.id:sim.itinerary(r) for r in sim.robots})
        rec.case('COUPLING-protected-prefix-'+mode,'P6-coupling-contract',prefix)

    def rolling_certificate():
        folder=out/'cases'/'MODE-rolling'
        require((folder/'plans.jsonl.gz').exists(),'rolling evidence missing')
        with gzip.open(folder/'plans.jsonl.gz','rt',encoding='utf-8') as f:plans=[json.loads(line) for line in f]
        require(bool(plans),'no rolling plans')
        for p in plans:
            require(type(p['valid_until']) is int and p['tick']<p['valid_until']<=p['tick']+4,'invalid execution prefix')
        index=0;steps=0
        with gzip.open(folder/'trace.jsonl.gz','rt',encoding='utf-8') as f:
            for line in f:
                frame=json.loads(line)
                while index+1<len(plans) and plans[index+1]['tick']<frame['tick']:index+=1
                require(frame['tick']<=plans[index]['valid_until'],'executed beyond certified prefix')
                steps+=1
        return dict(plans=len(plans),steps=steps)
    rec.case('ROLLING-certified-prefix-audit','P6-mode-contract',rolling_certificate)
    # Re-read actual traces independently, verify continuous service and timestamp semantics.
    for result_file in sorted((out/'cases').glob('*/result.json')):
        result=json.loads(result_file.read_text(encoding='utf-8'))
        trace=result_file.parent/'trace.jsonl.gz'
        if not trace.exists() or 'actual_steps_checked' not in result:continue
        def audit(trace=trace,result=result):
            active={};previous=None;service_completions=0;ticks=0
            with gzip.open(trace,'rt',encoding='utf-8') as stream:
                for line in stream:
                    row=json.loads(line);tick=row['tick'];robots={r[0]:r for r in row['robots']};tasks={t[0]:t for t in row['tasks']}
                    if previous:
                        oldrobots=previous['robots']
                        for rid,r in robots.items():
                            old=oldrobots[rid]
                            if r[3] in ('picking','unloading') and r[3]!=old[3]:
                                require(r[7]==2, f'incorrect service duration on entry tick={tick}')
                            if old[3] in ('picking','unloading'):
                                require(r[1:3]==old[1:3],f'actual moved during service tick={tick}')
                                require(r[7]==max(0,old[7]-1) or (old[3]=='unloading' and r[3]=='picking'),f'service countdown changed tick={tick}')
                                if r[3]!=old[3]:
                                    task=tasks[old[5]]
                                    if old[3]=='picking':require(task[3]==tick and r[4],'load completion timestamp/cargo')
                                    else:require(task[4]==tick and task[1]=='completed','unload completion timestamp')
                                    service_completions+=1
                    previous=dict(robots=robots);ticks+=1
            require(ticks==result['actual_steps_checked'],'trace incomplete')
            return dict(trace_ticks=ticks,service_transitions_checked=service_completions,source_case=result['case_id'])
        rec.case('TRACE-'+result['case_id'],'TRACE-audit',audit)
    rec.file.close()
    print(json.dumps(dict(supplement=len(rec.rows),statuses={s:sum(r['status']==s for r in rec.rows) for s in ('PASS','FAIL')})),flush=True)

if __name__=='__main__':run(sys.argv[1])