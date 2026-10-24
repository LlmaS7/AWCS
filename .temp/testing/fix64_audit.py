"""Audit all recorded fixed-code traces and execution certificates independently."""
from pathlib import Path
import sys,json,gzip
sys.dont_write_bytecode=True
from checkers import require,paths_check
from run_suite import dump
from types import SimpleNamespace

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def main(out):
    out=Path(out);records=[]
    for rf in sorted((out/'cases').glob('*/result.json')):
        folder=rf.parent;result=read(rf);trace=folder/'trace.jsonl.gz'
        if not trace.exists():continue
        actual=read(folder/'actual_map.json');rows=actual['grid']['rows']
        if (folder/'initial_state.json').exists():
            initial=read(folder/'initial_state.json');tick=initial['tick'];previous={r['id']:[r['id'],*r['position'],r['phase'],r['loaded'],r['task_id'],r['next_task_id'],r['service_left']] for r in initial['robots']}
        else:
            tick=0;previous={i+1:[i+1,*p,'idle',False,None,None,0] for i,p in enumerate(actual['points']['starts'][:result['inputs']['robots']])}
        plans=[]
        if (folder/'plans.jsonl.gz').exists():
            with gzip.open(folder/'plans.jsonl.gz','rt',encoding='utf-8') as f:
                plans=[json.loads(l) for l in f]
            for p in plans:
                points={int(r):[SimpleNamespace(**w) for w in ws] for r,ws in p['waypoints'].items()}
                paths_check(rows,{int(r):tuple(pos) for r,pos in p['origins'].items()},{int(r):list(map(tuple,path)) for r,path in p['paths'].items()},points,result['inputs'].get('mode')=='rolling')
        count=0;transitions=0;plan_index=0;positions=0
        with gzip.open(trace,'rt',encoding='utf-8') as f:
            for line in f:
                frame=json.loads(line);require(frame['tick']==tick+1,'nonconsecutive tick');tick=frame['tick']
                robots={r[0]:r for r in frame['robots']};tasks={t[0]:t for t in frame['tasks']}
                positions+=paths_check(rows,{rid:tuple(r[1:3]) for rid,r in previous.items()},{rid:[tuple(previous[rid][1:3]),tuple(r[1:3])] for rid,r in robots.items()})
                if plans:
                    while plan_index+1<len(plans) and plans[plan_index+1]['tick']<tick:plan_index+=1
                    lease=plans[plan_index].get('valid_until')
                    if lease is not None:require(tick<=lease,'execution beyond certified lease')
                for rid,r in robots.items():
                    old=previous[rid]
                    require(r[4]==(r[3] in ('to_delivery','unloading')),'cargo phase')
                    if r[3] in ('picking','unloading') and old[3]!=r[3]:require(r[7]==2,'service duration')
                    if old[3] in ('picking','unloading'):
                        require(r[1:3]==old[1:3],'motion during service')
                        require(r[7]==max(0,old[7]-1) or (old[3]=='unloading' and r[3]=='picking'),'service countdown')
                        if r[3]!=old[3]:
                            t=tasks[old[5]]
                            require((t[3]==tick and r[4]) if old[3]=='picking' else (t[4]==tick and t[1]=='completed'),'service timestamp')
                            transitions+=1
                previous=robots;count+=1
        require(count==result['actual_steps_checked'],'incomplete trace')
        require(tick==result['tick'],'final tick mismatch')
        if result['status']=='PASS':
            final=read(folder/'final_state.json');require(all(t['status']=='completed' and t['picked_at'] is not None and t['completed_at'] is not None and t['picked_at']<=t['completed_at'] for t in final['tasks']),'final workload not completed')
        records.append(dict(case_id=result['case_id'],status='PASS',plans=len(plans),ticks=count,service_transitions=transitions,position_samples=positions))
        dump(out/'trace_audit_progress.json',dict(traces=len(records),last_case=result['case_id'],ticks=sum(r['ticks'] for r in records)))
        if len(records)%10==0:print(json.dumps(dict(audited_traces=len(records),last_case=result['case_id'])),flush=True)
    dump(out/'trace_audit.json',records)
    print(json.dumps(dict(traces=len(records),ticks=sum(r['ticks'] for r in records),plans=sum(r['plans'] for r in records),transitions=sum(r['service_transitions'] for r in records))),flush=True)
if __name__=='__main__':main(sys.argv[1])
