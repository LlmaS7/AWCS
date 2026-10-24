from pathlib import Path
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import json, random, time, traceback, itertools
from copy import deepcopy
from dataclasses import asdict, replace
from types import SimpleNamespace
from checkers import (require, Grid, paths_check, itinerary_check, assignment_oracle,
                      assignment_score, single_oracle, joint_oracle, business_check)
from models import Task, Waypoint
from scheduler import Slot, minimum_assignment, completion_cost
from coordination.assignment import match
from planning.reservations import Reservations
from planning.sipp import search
from planning.scalable import plan
from simulation import Simulation
from coordination.contracts import PlanningProfile, Proposal, RequestKey


def fixture():
    return dict(format='sditadc-map',version=1,name='Independent fixture',
        grid=dict(width=9,height=9,rows=['#########']+['#.......#']*7+['#########']),
        points=dict(starts=[[1,1],[2,1],[3,1],[4,1]],
                    parking=[[1,1],[2,1],[3,1],[4,1],[7,1],[7,7],[1,7]],
                    pickups=[[2,4],[4,4]],deliveries=[[6,4],[6,6]]),
        robots=dict(default_count=2,max_count=4),random_obstacles=dict(count=0))


def new_sim(n=2):
    return Simulation(20261020,initial_tasks=0,map_id='independent-fixture',
        map_definition=fixture(),robot_count=n,profile=PlanningProfile(seconds=2))


def add(sim,priority=2,pickup=0,delivery=0):
    return sim.add_task(sim.warehouse.pickups[pickup],sim.warehouse.deliveries[delivery],priority)


def physical(sim):
    return sim.tick,[(r.position,r.loaded,r.service_left,r.task_id,r.phase) for r in sim.robots],{
        t.id:(t.status,t.robot_id,t.priority,t.picked_at,t.completed_at) for t in sim.tasks.values()}


def advance(sim, predicate, limit=150):
    for _ in range(limit):
        if predicate(): return
        require(sim.ensure_plan(),'fixture could not plan')
        paths_check(sim.warehouse.export_map()['grid']['rows'],{r.id:r.position for r in sim.robots},
            {r.id:r.path for r in sim.robots},{r.id:sim.itinerary(r) for r in sim.robots})
        require(sim.step(),'fixture could not step')
        business_check(sim)
    raise AssertionError('fixture phase not reached')


class Recorder:
    def __init__(self,out):
        self.out=Path(out)
        self.rows=[]
        self.file=(self.out/'results.jsonl').open('a',encoding='utf-8')
    def case(self,case_id,stage,fn,inputs=None):
        start=time.monotonic()
        row=dict(case_id=case_id,stage=stage,inputs=inputs)
        try:
            details=fn() or {}
            row.update(status='PASS',details=details)
        except Exception as exc:
            row.update(status='FAIL',error=f'{type(exc).__name__}: {exc}',traceback=traceback.format_exc())
            counter=self.out/'counterexamples'/f'{case_id}.json'
            counter.write_text(json.dumps(row,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
        row['elapsed']=time.monotonic()-start
        self.file.write(json.dumps(row,ensure_ascii=False,default=str)+'\n');self.file.flush()
        self.rows.append(row)
        if row['status']!='PASS': print(case_id,row['status'],row['error'],flush=True)
        return row


def core(out):
    rec=Recorder(out)
    openrows=['....']*4
    def valid_checker():
        count=paths_check(openrows,{1:(0,0),2:(3,3)},
            {1:[(0,0),(1,0),(2,0)],2:[(3,3),(2,3),(1,3)]})
        require(count==6,'checker count')
    rec.case('P0-valid','P0',valid_checker)
    invalids={
        'origin':({1:(1,0)},{1:[(0,0)]},None),
        'vertex':({1:(0,0),2:(2,0)},{1:[(0,0),(1,0)],2:[(2,0),(1,0)]},None),
        'swap':({1:(0,0),2:(1,0)},{1:[(0,0),(1,0)],2:[(1,0),(0,0)]},None),
        'jump':({1:(0,0)},{1:[(0,0),(2,0)]},None),
        'outside':({1:(0,0)},{1:[(0,0),(-1,0)]},None),
        'persistent':({1:(0,0),2:(2,0)},{1:[(0,0),(1,0)],2:[(2,0),(2,1),(1,1),(1,0)]},None),
        'service':({1:(0,0)},{1:[(0,0),(1,0),(2,0)]},{1:[Waypoint((1,0),2),Waypoint((2,0))]}),
    }
    for name,args in invalids.items():
        def reject(args=args):
            try: paths_check(openrows,*args)
            except AssertionError:return
            raise AssertionError('independent checker accepted injected violation')
        rec.case('P0-reject-'+name,'P0',reject,inputs=args)
    def blocked_checker():
        try: paths_check(['.#'],{1:(0,0)},{1:[(0,0),(1,0)]})
        except AssertionError:return
        raise AssertionError('wall accepted')
    rec.case('P0-reject-wall','P0',blocked_checker)
    def unique_checker():
        sim=new_sim();tid=add(sim);sim.dispatch()
        next(r for r in sim.robots if r.id!=sim.tasks[tid].robot_id).task_id=tid
        try:business_check(sim)
        except AssertionError:return
        raise AssertionError('duplicate ownership accepted')
    rec.case('P0-reject-owner','P0',unique_checker)

    for n in range(5):
        for m in range(6):
            for seed in range(40):
                rng=random.Random(100000+n*10000+m*100+seed)
                slots=[Slot(i+1,(0,0)) for i in range(n)]
                tasks=[Task(j+1,(0,0),(1,0),rng.randint(1,5),rng.choice([0,1,100,10**12])) for j in range(m)]
                costs={(s.robot_id,t.id):rng.choice([0,1,2,5,100,999999,1000000,None]) for s in slots for t in tasks}
                prefs={(s.robot_id,t.id):rng.randint(0,1) for s in slots for t in tasks} if seed%2 else None
                def run(slots=slots,tasks=tasks,costs=costs,prefs=prefs):
                    cost=lambda s,t:costs[s.robot_id,t.id]
                    pref=(lambda s,t:prefs[s.robot_id,t.id]) if prefs is not None else None
                    pairs,score=match(slots,tasks,cost,pref)
                    expected=assignment_oracle(slots,tasks,costs,prefs)
                    actual=assignment_score(pairs,slots,tasks,costs,prefs)
                    require(score==actual==expected,f'oracle={expected} actual={actual} reported={score}')
                    rp,rs=match(list(reversed(slots)),list(reversed(tasks)),cost,pref)
                    require(rs==expected,'permutation changed objective')
                    return dict(score=score,pairs=pairs)
                rec.case(f'A-random-{n}-{m}-{seed:02}','P1',run,
                    dict(slots=[asdict(s) for s in slots],tasks=[asdict(t) for t in tasks],
                         costs=[[r,t,c] for (r,t),c in costs.items()],preferences=None if prefs is None else [[r,t,p] for (r,t),p in prefs.items()]))
    def greedy():
        slots=[Slot(1,(0,0)),Slot(2,(0,0))]
        tasks=[Task(1,(0,0),(1,0),2,0),Task(2,(0,0),(1,0),2,0)]
        table={(1,1):1,(1,2):2,(2,1):3,(2,2):100}
        pairs,score=match(slots,tasks,lambda s,t:table[s.robot_id,t.id])
        require(score[-2]==5 and pairs=={1:2,2:1},'greedy trap failed')
        return dict(pairs=pairs,eta=score[-2],greedy_eta=101)
    rec.case('A03-greedy-trap','P1',greedy)
    def priority():
        slots=[Slot(1,(0,0))];tasks=[Task(1,(0,0),(1,0),5,10**15),Task(2,(0,0),(1,0),4,0)]
        p,s=match(slots,tasks,lambda slot,t:999999 if t.id==1 else 0,lambda slot,t:1 if t.id==1 else 0)
        require(p=={1:1},'distance/preference overrode grade')
    rec.case('A04-priority-dominates','P1',priority)
    for n in range(5):
        for m in range(max(1,n),7):
            for seed in range(5):
                rng=random.Random(n*1000+m*100+seed)
                matrix=[[rng.choice([0,1,10,10**15]) for _ in range(m)] for _ in range(n)]
                def hungarian(matrix=matrix,n=n,m=m):
                    columns=minimum_assignment(matrix)
                    require(len(columns)==n and len(set(columns))==n,'invalid columns')
                    actual=sum(matrix[i][j] for i,j in enumerate(columns))
                    best=min(sum(matrix[i][j] for i,j in enumerate(cols)) for cols in itertools.permutations(range(m),n))
                    require(actual==best,f'{actual} != {best}')
                rec.case(f'H-{n}-{m}-{seed}','P1',hungarian,matrix)
    for name,matrix in [('short',[[1],[2]]),('ragged',[[1,2],[1]])]:
        def invalid(matrix=matrix):
            try:minimum_assignment(matrix)
            except ValueError:return
            raise AssertionError('invalid shape accepted')
        rec.case('H-invalid-'+name,'P1',invalid,matrix)
    def eta():
        sim=new_sim(1);tid=add(sim);task=sim.tasks[tid];slot=Slot(1,(1,1),release=7)
        g=Grid(sim.warehouse.export_map()['grid']['rows'])
        expected=7+g.distance(slot.origin,task.pickup)+2+g.distance(task.pickup,task.delivery)+2
        require(completion_cost(sim.warehouse,slot,task)==expected,'ETA terms wrong')
        for a in [(1,1),(2,4),(6,6)]:
            for b in [(7,7),(4,4),(1,1)]:require(g.distance(a,b)==sim.warehouse.distance(a,b),'BFS distance mismatch')
    rec.case('A-eta-static-bfs','P1',eta)

    for seed in range(150):
        def reservation(seed=seed):
            rng=random.Random(seed);table=Reservations();occupied=set();h=12;p=(1,1)
            for _ in range(8):
                a=rng.randrange(18);b=a+rng.randrange(5)
                table.block(p,a,b);occupied.update(range(a,b+1))
                expanded={t for a,b in table.safe_intervals(p,h) for t in range(a,b+1)}
                require(expanded==set(range(h+1))-occupied,'interval complement/cache')
            clone=table.clone();clone.block((2,2),0,12)
            require(table.safe_intervals((2,2),h)==[(0,h)],'clone leaked')
        rec.case(f'R-interval-{seed:03}','P3',reservation,dict(seed=seed))
    def edge_and_tail():
        table=Reservations();table.add_path([(0,0),(1,0),(1,0),(2,0)])
        require(table.next_edge_time((1,0),(0,0),1)==2,'reverse edge not blocked')
        require(table.safe_intervals((1,0),6)==[(0,0),(3,6)],'hold merged incorrectly')
        require(table.safe_intervals((2,0),6)==[(0,2)],'parking not persistent')
        only=Reservations();only.add_path([(0,0)])
        require(only.safe_intervals((0,0),12)==[],'single endpoint vanished')
    rec.case('R-edge-parking','P3',edge_and_tail)

    for seed in range(200):
        rng=random.Random(300000+seed);h=12
        rows=['....']*4;grid=Grid(rows)
        start=(0,0)
        goals=rng.sample([(x,y) for y in range(4) for x in range(4) if (x,y)!=start],2)
        points=[Waypoint(goals[0],rng.randrange(3),True,bool(seed%2)),Waypoint(goals[1])]
        vertices=set();edges=set();table=Reservations()
        for _ in range(5):
            p=(rng.randrange(4),rng.randrange(4));t=rng.randrange(h+1)
            vertices.add((p,t));table.block(p,t,t)
        for _ in range(3):
            p=(rng.randrange(4),rng.randrange(4));q=rng.choice(grid.neighbors(p));t=rng.randrange(1,h+1)
            edges.add((p,q,t));table.block_edge(p,q,t,t)
        def sipp(rows=rows,grid=grid,points=points,vertices=vertices,edges=edges,table=table,h=h):
            expected=single_oracle(grid,start,points,vertices,edges,h)
            result=search(grid,start,points,table,time.monotonic()+2,h)
            require((result is None)==(expected is None),f'feasibility oracle={expected}, result={result}')
            if result is not None:
                path,cost=result
                paths_check(rows,{1:start},{1:path},{1:points})
                require(cost==expected,f'cost oracle={expected}, result={cost}')
                require(itinerary_check(path,points)==cost,'cost/actual path mismatch')
                for t,p in enumerate(path):
                    require((p,t) not in vertices,'reserved vertex used')
                    if t:require((path[t-1],p,t) not in edges,'reserved edge used')
                require(all((path[-1],t) not in vertices for t in range(len(path)-1,h+1)),'parked over reservation')
            return dict(oracle=expected,actual=None if result is None else result[1])
        rec.case(f'SIPP-oracle-{seed:03}','P3',sipp,dict(rows=rows,start=start,points=[asdict(w) for w in points],
            vertices=[(p,t) for p,t in sorted(vertices)],edges=sorted(edges),horizon=h))
    fixed=[('cross',['....']*3,[(0,1),(3,1)],[(3,1),(0,1)],8),
           ('impossible',['....'],[(0,0),(3,0)],[(3,0),(0,0)],8),
           ('three',['...']*3,[(0,0),(1,0),(2,0)],[(2,2),(1,2),(0,2)],8)]
    for name,rows,starts,goals,h in fixed:
        def joint(rows=rows,starts=starts,goals=goals,h=h):
            grid=Grid(rows);expected=joint_oracle(grid,starts,goals,h)
            itineraries={i+1:[Waypoint(g)] for i,g in enumerate(goals)}
            origins={i+1:p for i,p in enumerate(starts)}
            result=plan(grid,origins,itineraries,seconds=2,horizon=h)
            if expected is not None:
                require(result.status=='success',f'known feasible fixture unsolved: {result.status}')
            if result.status=='success':
                require(expected is not None,'claimed solution in exhaustive impossible horizon')
                paths_check(rows,origins,result.paths,itineraries)
            return dict(oracle_makespan=expected,actual_status=result.status)
        rec.case('JOINT-'+name,'P3',joint,dict(rows=rows,starts=starts,goals=goals,horizon=h))

    def normal():
        sim=new_sim();tid=add(sim);sim.dispatch();business_check(sim)
        require(sim.tasks[tid].robot_id is not None,'task unassigned')
    rec.case('B01-normal','P2',normal)
    def preempt():
        sim=new_sim(1);normal_id=add(sim);sim.dispatch();urgent=add(sim,5,1,1);sim.dispatch();business_check(sim)
        require(sim.tasks[normal_id].status=='pending','old task lost')
        require(sim.robots[0].task_id==urgent and sim.metrics['preemptions']==1,'urgent not preempted')
    rec.case('B02-emergency-preemption','P2',preempt)
    for phase in ('picking','to_delivery','unloading'):
        def atomic(phase=phase):
            sim=new_sim(1);tid=add(sim)
            advance(sim,lambda:sim.robots[0].phase==phase)
            r=sim.robots[0];before=(r.position,r.task_id,r.loaded,r.service_left)
            urgent=add(sim,5,1,1);sim.dispatch();business_check(sim)
            require((r.position,r.task_id,r.loaded,r.service_left)==before,'atomic job altered')
            require(r.next_task_id==urgent and sim.tasks[urgent].status=='reserved','no emergency reservation')
            sim.cancel_task(tid);require(sim.tasks[tid].status==phase,'cancelled loaded/service task')
            try:sim.set_assignment(tid,'auto')
            except ValueError:pass
            else:raise AssertionError('changed assignment after loading began')
        rec.case('B03-atomic-'+phase,'P2',atomic)
    def multi_emergency():
        sim=new_sim(2);a=add(sim,5);b=add(sim,5,1,1);add(sim,1);sim.dispatch();business_check(sim)
        require({r.task_id for r in sim.robots}=={a,b},'urgent jobs displaced')
    rec.case('B04-two-emergencies','P2',multi_emergency)
    def forced():
        sim=new_sim();tid=add(sim);sim.set_assignment(tid,'forced',2);sim.dispatch();business_check(sim)
        require(sim.tasks[tid].robot_id==2,'forced owner changed')
        sim.set_assignment(tid,'auto');sim.dispatch();business_check(sim)
        require(sim.tasks[tid].assignment_robot_id is None,'requested owner retained')
    rec.case('B05-forced-release','P2',forced)
    def busy():
        sim=new_sim(1);first=add(sim);sim.dispatch();second=add(sim)
        before=physical(sim)
        try:sim.set_assignment(second,'forced',1)
        except ValueError:pass
        else:raise AssertionError('busy forced assignment accepted')
        require(physical(sim)==before,'rejection modified other task')
    rec.case('B06-busy-reject','P2',busy)
    def preference():
        sim=new_sim();tid=add(sim);sim.set_assignment(tid,'preferred',2);sim.dispatch();business_check(sim)
        require(sim.tasks[tid].robot_id==2,'available preference not satisfied')
        sim.set_assignment(tid,'auto');sim.dispatch();business_check(sim)
    rec.case('B07-preferred','P2',preference)
    def priority_forced():
        sim=new_sim(1);add(sim,5);low=add(sim,1)
        try:sim.set_assignment(low,'forced',1)
        except ValueError:return
        raise AssertionError('forced assignment bypassed urgent')
    rec.case('B05-forced-priority-reject','P2',priority_forced)
    def cancel():
        sim=new_sim();tid=add(sim);sim.dispatch();sim.cancel_task(tid);sim.dispatch();business_check(sim)
        require(sim.tasks[tid].status=='cancelled','cancel did not apply')
        require(all(r.task_id!=tid and r.next_task_id!=tid for r in sim.robots),'cancel retained owner')
    rec.case('B09-cancel-before-load','P2',cancel)
    def repeated():
        sim=new_sim();add(sim);add(sim,3,1,1);sim.dispatch()
        for _ in range(10):sim.dispatch();business_check(sim)
    rec.case('B10-repeated-dispatch','P2',repeated)

    def failure():
        sim=new_sim();tid=add(sim);before=physical(sim)
        result=sim.apply_proposal(Proposal(None,False,status='timeout'))
        require(not result and sim.paused and physical(sim)==before,'unsafe failed plan handling')
        sim.paused=False;require(sim.ensure_plan(),'retry did not recover');business_check(sim)
        require(len(sim.tasks)==1,'retry duplicated task')
    rec.case('F04-F05-timeout-retry','P5',failure)
    for kind in ('jump','wall','priority','fake_completed','collision'):
        def forged(kind=kind):
            from coordination.coordinator import solve
            sim=new_sim();tid=add(sim)
            proposal=solve(sim)
            require(proposal.success,'fixture solve failed')
            if kind=='jump':proposal.robots[0].path.insert(1,(7,7))
            elif kind=='wall':proposal.robots[0].path.insert(1,(0,0))
            elif kind=='priority':proposal.tasks[tid].priority=5
            elif kind=='fake_completed':proposal.tasks[tid].status='completed'
            else:proposal.robots[1].path=deepcopy(proposal.robots[0].path)
            before=physical(sim)
            try:sim.apply_proposal(proposal)
            except (ValueError,AssertionError):pass
            else:raise AssertionError('forged plan accepted')
            require(physical(sim)==before,'forged plan changed physical state')
        rec.case('F-forged-'+kind,'P5',forged)
    def unsafe_step():
        sim=new_sim(2);sim.dirty=False
        a,b=sim.robots;a.path=[a.position,b.position];b.path=[b.position,a.position]
        before=physical(sim)
        try:sim.step()
        except RuntimeError:pass
        else:raise AssertionError('unsafe step executed')
        require(physical(sim)==before,'unsafe step advanced physical state')
    rec.case('F-execution-swap-guard','P5',unsafe_step)
    for field in ('run_id','generation','domain_revision','tick','request_id','geometry'):
        def stale(field=field):
            from controller import Controller
            key=RequestKey('run',0,0,0,1,'map')
            old=replace(key,**{field:('old' if field in ('run_id','geometry') else 9)})
            c=Controller.__new__(Controller)
            c.sim=SimpleNamespace(tick=0,metrics={})
            c.generation=0;c._requested=key
            c.worker=SimpleNamespace(poll=lambda:(old,None,None))
            Controller._poll_plan(c)
            require(c.sim.metrics.get('stale_plans')==1 and c._requested==key,'stale result accepted')
        rec.case('F-stale-'+field,'P5',stale)
    def worker_error():
        from controller import Controller
        key=RequestKey('run',0,0,0,1,'map');sim=new_sim();before=physical(sim)
        c=Controller.__new__(Controller);c.sim=sim;c.generation=0;c._requested=key
        c.worker=SimpleNamespace(poll=lambda:(key,None,'injected error'))
        c._publish=lambda:None;c._finish_waiters=lambda:None;c._resume_jobs=lambda:None
        Controller._poll_plan(c)
        require(sim.paused and physical(sim)==before and sim.metrics['planning_status']=='worker_error','worker error unsafe')
    rec.case('F-worker-error','P5',worker_error)
    rec.file.close()
    counts={s:sum(r['status']==s for r in rec.rows) for s in ('PASS','FAIL','INCONCLUSIVE')}
    print(json.dumps(dict(stage='core',counts=counts),ensure_ascii=False),flush=True)
    return rec.rows

if __name__=='__main__':
    core(sys.argv[1])