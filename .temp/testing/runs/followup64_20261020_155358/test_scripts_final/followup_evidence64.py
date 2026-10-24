"""Post-run evidence checks; no production files are modified."""
from pathlib import Path
import sys,json,gzip
sys.dont_write_bytecode=True
from followup64 import restore,dump
from checkers import require,paths_check
from planning.validation import validate_itineraries

def witness(out):
    records=[]
    original=out.parent/'20261020_144032_8fe978'/'cases'
    for folder in sorted(original.glob('EXPERIMENT64-*')):
        if 'experimental_128x96' in folder.name:continue
        sim,_,_,_=restore(folder)
        starts={r.id:r.position for r in sim.robots};paths={r.id:r.path for r in sim.robots};points={r.id:sim.itinerary(r) for r in sim.robots}
        n=paths_check(sim.warehouse.export_map()['grid']['rows'],starts,paths,points)
        costs=validate_itineraries(sim.warehouse,starts,paths,points)
        lower=0
        for rid,ws in points.items():
            p=starts[rid];length=0
            for w in ws:length+=sim.warehouse.distance(p,w.position)+w.hold;p=w.position
            lower=max(lower,length)
        horizon=max(260,lower+max(40,len(starts)*4));maximum=max(len(p)-1 for p in paths.values())
        require(maximum<=horizon,'witness outside production search horizon')
        records.append(dict(case_id=folder.name,independent_validation='PASS',production_validation='PASS',path_points=n,max_path_steps=maximum,production_horizon=horizon,within_horizon=True,robot_count=len(costs)))
    dump(out/'feasibility_witness.json',records)
    print(json.dumps(records),flush=True)

def audit(out):
    records=[]
    for rf in sorted((out/'cases').glob('*/result.json')):
        folder=rf.parent;result=json.loads(rf.read_text(encoding='utf-8'))
        if not (folder/'trace.jsonl.gz').exists():continue
        initial=json.loads((folder/'initial_state.json').read_text(encoding='utf-8'))
        previous={r['id']:[r['id'],*r['position'],r['phase'],r['loaded'],r['task_id'],r['next_task_id'],r['service_left']] for r in initial['robots']}
        tick=initial['tick'];count=0;transitions=0;positions=0
        rows=json.loads((folder/'actual_map.json').read_text(encoding='utf-8'))['grid']['rows']
        with gzip.open(folder/'trace.jsonl.gz','rt',encoding='utf-8') as stream:
            for line in stream:
                frame=json.loads(line);require(frame['tick']==tick+1,'nonconsecutive tick');tick=frame['tick']
                robots={r[0]:r for r in frame['robots']};tasks={t[0]:t for t in frame['tasks']}
                positions+=paths_check(rows,{rid:tuple(r[1:3]) for rid,r in previous.items()}, {rid:[tuple(previous[rid][1:3]),tuple(r[1:3])] for rid,r in robots.items()})
                for rid,r in robots.items():
                    old=previous[rid]
                    require(r[4]==(r[3] in ('to_delivery','unloading')),'cargo/phase mismatch')
                    if r[3] in ('picking','unloading') and r[3]!=old[3]:require(r[7]==2,'incorrect service duration')
                    if old[3] in ('picking','unloading'):
                        require(r[1:3]==old[1:3],'motion during service')
                        require(r[7]==max(0,old[7]-1) or (old[3]=='unloading' and r[3]=='picking'),'countdown mismatch')
                        if r[3]!=old[3]:
                            task=tasks[old[5]]
                            if old[3]=='picking':require(task[3]==tick and r[4],'pickup timestamp/cargo')
                            else:require(task[4]==tick and task[1]=='completed','delivery timestamp')
                            transitions+=1
                previous=robots;count+=1
        require(count==result['actual_steps_checked'],'trace length mismatch')
        require(tick==result['tick'],'final tick mismatch')
        if result['status']=='PASS':
            final=json.loads((folder/'final_state.json').read_text(encoding='utf-8'))
            require(len(final['tasks'])==128 and all(t['status']=='completed' and t['picked_at'] is not None and t['completed_at'] is not None and t['picked_at']<=t['completed_at'] for t in final['tasks']),'incomplete final tasks')
        records.append(dict(case_id=result['case_id'],status='PASS',trace_ticks=count,service_transitions=transitions,position_samples=positions))
    dump(out/'trace_audit.json',records)
    print(json.dumps(dict(traces=len(records),ticks=sum(r['trace_ticks'] for r in records),service_transitions=sum(r['service_transitions'] for r in records))),flush=True)

if __name__=='__main__':
    out=Path(sys.argv[2])
    (witness if sys.argv[1]=='witness' else audit)(out)
