"""Exercise genuine owner thread and spawned planner on a frozen 64-robot stall."""
from pathlib import Path
import sys,json,time,gzip,traceback
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];sys.path.insert(0,str(ROOT))
from dataclasses import asdict
from unittest.mock import patch
from copy import deepcopy
from types import SimpleNamespace
from followup64 import restore,state
from run_suite import dump,record,summarize
from checkers import paths_check,business_check,require
from controller import Controller

def main(out, name='rectangle-20262018'):
    out=Path(out).resolve();folder=out/'cases'/('FIX-ACTOR64-'+name);folder.mkdir(exist_ok=True)
    source=HERE/'runs/20261020_144032_8fe978/cases'/('EXPERIMENT64-'+name)
    row=dict(case_id=folder.name,stage='FIX-actor64',status='INCONCLUSIVE',source_case=str(source),actual_steps_checked=0,plan_checks=0,path_points_checked=0)
    started=time.monotonic();c=None
    try:
        sim,_,_,reconstruction=restore(source);sim.dirty=True
        row.update(initial_tick=sim.tick,initial_completed=sum(t.status=='completed' for t in sim.tasks.values()),reconstruction=reconstruction)
        dump(folder/'initial_state.json',state(sim));dump(folder/'actual_map.json',sim.warehouse.export_map())
        dump(folder/'input.json',dict(source_case=str(source),mode='genuine Controller thread and PlannerWorker; no solver injection',wall_seconds=300))
        rows=sim.warehouse.export_map()['grid']['rows']
        with patch('controller.Simulation',return_value=sim):c=Controller(paused=True)
        c.start();previous={r.id:r.position for r in sim.robots};last_tick=sim.tick
        with gzip.open(folder/'trace.jsonl.gz','wt',encoding='utf-8') as trace:
            for _ in range(2000):
                view=c.submit('step').result(timeout=25)
                origins=previous;current={r['id']:tuple(r['position']) for r in view['robots']}
                row['path_points_checked']+=paths_check(rows,origins,{rid:[origins[rid],p] for rid,p in current.items()})
                # The actor remains paused between commands. Capture a consistent public state.
                require(view['tick']==sim.tick,'actor advanced while paused')
                require(view['tick']==last_tick+1,'actor did not execute exactly one step')
                last_tick=view['tick']
                business_check(sim)
                row['actual_steps_checked']+=1
                trace.write(json.dumps(dict(tick=view['tick'],robots=[[r['id'],*r['position'],r['phase'],r['loaded'],r['task_id'],r['next_task_id'],r['service_left']] for r in view['robots']],tasks=[[t['id'],t['status'],t['robot_id'],t['picked_at'],t['completed_at']] for t in view['tasks']]))+'\n');trace.flush()
                previous=current
                if sim.plan_valid_until is not None:row['lease_steps_checked']=row.get('lease_steps_checked',0)+1
                if all(t['status']=='completed' for t in view['tasks']):row['status']='PASS';row['terminal']='all_128_tasks_completed';break
                if time.monotonic()-started>300:row['terminal']='wall_limit';break
            row.update(completed=sum(t.status=='completed' for t in sim.tasks.values()),total=len(sim.tasks),tick=sim.tick,metrics=deepcopy(sim.snapshot().metrics))
            require(row['metrics'].get('retained_plans',0)>0,'test never exercised production recovery')
    except Exception as exc:row.update(status='FAIL',error=f'{type(exc).__name__}: {exc}',traceback=traceback.format_exc())
    finally:
        if c is not None:c.stop(save_on_exit=False)
        if 'sim' in locals():dump(folder/'final_state.json',state(sim))
        row['elapsed']=time.monotonic()-started;dump(folder/'result.json',row);record(out,row);summarize(out)
    print(json.dumps(row,ensure_ascii=False),flush=True)
if __name__=='__main__':main(sys.argv[1],sys.argv[2] if len(sys.argv)>2 else 'rectangle-20262018')
