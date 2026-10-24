from pathlib import Path
import sys,time,json
sys.dont_write_bytecode=True
from copy import copy
from collections import Counter
from unittest.mock import patch
from followup64 import restore,dump
from coordination.contracts import snapshot_for_planning,PlanningProfile
from coordination.coordinator import solve
from checkers import paths_check


def run(out):
    out=Path(out);original=out.parent/'20261020_144032_8fe978'/'cases';records=[]
    for folder in sorted(original.glob('EXPERIMENT64-*')):
        if 'experimental_128x96' in folder.name:continue
        sim,_,_,reconstruction=restore(folder)
        sim.profile=PlanningProfile(seconds=10)
        rows=sim.warehouse.export_map()['grid']['rows'];origins={r.id:r.position for r in sim.robots}
        suffix_points=paths_check(rows,origins,{r.id:r.path for r in sim.robots},{r.id:sim.itinerary(r) for r in sim.robots})
        candidate=snapshot_for_planning(sim);candidate.dispatch()
        changed=[dict(robot_id=a.id,old=a.parking,new=b.parking,phase=a.phase,position=a.position) for a,b in zip(sim.robots,candidate.robots) if a.parking!=b.parking]
        task_changes=[tid for tid in sim.tasks if (sim.tasks[tid].robot_id,sim.tasks[tid].status)!=(candidate.tasks[tid].robot_id,candidate.tasks[tid].status)]
        warm=time.monotonic()
        goals=set(sim.warehouse.parking+sim.warehouse.pickups+sim.warehouse.deliveries+[r.position for r in sim.robots])
        for p in goals:sim.warehouse.distance(p,p)
        warm_time=time.monotonic()-warm
        comparisons=[]
        for variant in ('normal_parking','keep_previous_parking'):
            began=time.monotonic()
            if variant=='keep_previous_parking':
                with patch('simulation.optimal_parking',side_effect=lambda warehouse,positions,current=None:list(current)):
                    proposal=solve(sim)
            else:proposal=solve(sim)
            result=dict(variant=variant,status=proposal.status,success=proposal.success,elapsed=time.monotonic()-began,diagnostics=proposal.diagnostics)
            if proposal.success:
                check=copy(sim);check.robots=proposal.robots;check.tasks=proposal.tasks
                result['checked_points']=paths_check(rows,origins,{r.id:r.path for r in check.robots},{r.id:check.itinerary(r) for r in check.robots})
                result['changed_parking_goals']=sum(a.parking!=b.parking for a,b in zip(sim.robots,check.robots))
            comparisons.append(result)
        rec=dict(case_id=folder.name,tick=sim.tick,completed=sum(t.status=='completed' for t in sim.tasks.values()),
            task_status_counts=dict(Counter(t.status for t in sim.tasks.values())),task_assignment_changes_on_dispatch=task_changes,
            parking_changes_on_dispatch=changed,current_suffix_independently_valid=True,suffix_points=suffix_points,
            distance_cache_prewarm_seconds=warm_time,comparisons=comparisons,
            note='Diagnostic A/B only. Both use original solver and 10-second budget on the identical frozen domain state. Parking function overridden only inside one test call and immediately restored.')
        records.append(rec);dump(out/'parking_diagnosis.json',records)
        print(json.dumps(dict(case=folder.name,status_counts=rec['task_status_counts'],task_changes=len(task_changes),parking_changes=len(changed),comparisons=comparisons),ensure_ascii=False),flush=True)
if __name__=='__main__':run(sys.argv[1])