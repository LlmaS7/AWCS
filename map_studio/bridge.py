"""Read-only consumer validation/probing, executed in an isolated interpreter.

Never instantiate Controller/AIService or read local_settings/credentials. This
adapter deliberately uses v0.4's authoritative validator rather than a copy.
"""
import hashlib
from copy import deepcopy
import json
from pathlib import Path
import sys
from time import monotonic

APP = Path(__file__).resolve().parents[1]


def inspect_map(definition):
    from map_format import validate_map, robot_limits
    from warehouse import Warehouse
    value = validate_map(definition)
    default,maximum = robot_limits(value)
    static = deepcopy(value)
    static['random_obstacles'] = {'count':0}
    w = Warehouse(0,definition=static,robot_count=default)
    topology = w.topology.public()
    digest = hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    return dict(valid=True,width=w.width,height=w.height,default_robots=default,max_robots=maximum,
                floor_cells=w.width*w.height-len(w.voids),void_cells=len(w.voids),
                free_cells=topology['free_cells'],shelves=len(w.locations['shelves']),
                pickups=len(w.pickups),deliveries=len(w.deliveries),parking=len(w.parking),
                obstacles=len(w.obstacles),pending_obstacles=value.get('random_obstacles',{}).get('count',0),
                sha256=digest,topology=topology,
                warning='静态检查通过不代表任意任务流或机器人数量都能成功规划。')


def probe(definition, robots, seed):
    from simulation import Simulation
    from coordination.contracts import PlanningProfile
    from planning.validation import first_conflict
    started = monotonic()
    seconds = 8 if robots>32 else 3
    tasks = max(9,robots)
    sim = Simulation(seed,initial_tasks=tasks,map_id='studio-probe',map_definition=definition,
                     robot_count=robots,profile=PlanningProfile(seconds=seconds,coupling='off'))
    failure = None
    limit = max(1000,(sim.warehouse.width+sim.warehouse.height)*8)
    while sim.tick < limit and monotonic()-started < 70:
        if sim.dirty:
            if not sim.ensure_plan():
                failure = sim.message;break
            if first_conflict({r.id:r.path for r in sim.robots}):
                failure = '路线冲突检查未通过';break
        if not sim.step(): failure = sim.message;break
        if all(t.status == 'completed' for t in sim.tasks.values()): break
    metrics = sim.snapshot().metrics
    completed = metrics['completed'] == metrics['total']
    return dict(status='passed' if completed and failure is None else 'inconclusive',
                robots=robots,seed=seed,tasks=tasks,completed=metrics['completed'],tick=sim.tick,
                collisions=metrics['collisions'],elapsed=round(monotonic()-started,3),
                plan_seconds=seconds,failure=failure,
                note='仅此地图快照、数量、种子和有限随机任务批；不是无死锁证明。')


def main():
    sys.path.insert(0,str(APP))
    try:
        request = json.loads(sys.stdin.buffer.read(2*1024*1024+8192).decode('utf-8-sig'))
        value = request['definition']
        result = inspect_map(value)
        if request.get('probe'):
            from map_format import integer
            count = integer(request.get('robots',result['default_robots']),'试运行机器人数量',1,result['max_robots'])
            seed = integer(request.get('seed',0),'试运行种子',0,2147483647)
            result['probe'] = probe(value,count,seed)
        output = dict(ok=True,analysis=result)
    except Exception as exc:
        output = dict(ok=False,error=str(exc))
    sys.stdout.buffer.write(json.dumps(output,ensure_ascii=False).encode('utf-8'))


if __name__ == '__main__': main()
