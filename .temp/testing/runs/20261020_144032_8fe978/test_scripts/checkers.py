"""Independent reference algorithms. No imports from production planners/validators."""
from collections import deque
from itertools import product


def require(condition, message):
    if not condition:
        raise AssertionError(message)


class Grid:
    def __init__(self, rows):
        self.rows = rows
        self.height = len(rows)
        self.width = len(rows[0])

    def is_open(self, p):
        x, y = p
        return 0 <= x < self.width and 0 <= y < self.height and self.rows[y][x] == '.'

    def neighbors(self, p):
        x, y = p
        return [q for q in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)) if self.is_open(q)]

    def distance(self, a, b):
        todo = deque([(a, 0)])
        seen = {a}
        while todo:
            p, n = todo.popleft()
            if p == b:
                return n
            for q in self.neighbors(p):
                if q not in seen:
                    seen.add(q)
                    todo.append((q,n+1))
        return 10**6


def paths_check(rows, starts, paths, waypoints=None, partial=False):
    grid = Grid(rows)
    require(set(starts) == set(paths), 'robot set mismatch')
    for r, path in paths.items():
        require(bool(path) and tuple(path[0]) == tuple(starts[r]), f'R{r} wrong origin')
        for t, p in enumerate(path):
            require(grid.is_open(p), f'R{r} blocked/outside t={t} p={p}')
            if t:
                a = path[t-1]
                require(abs(a[0]-p[0])+abs(a[1]-p[1]) <= 1, f'R{r} jump t={t}')
    horizon = max((len(p) for p in paths.values()),default=0)
    ids = list(paths)
    for t in range(horizon):
        positions = [tuple(paths[r][min(t,len(paths[r])-1)]) for r in ids]
        require(len(set(positions)) == len(ids), f'vertex conflict t={t}: {positions}')
        if t:
            previous = [tuple(paths[r][min(t-1,len(paths[r])-1)]) for r in ids]
            for i in range(len(ids)):
                for j in range(i):
                    require(not (positions[i]==previous[j] and positions[j]==previous[i]),
                            f'edge conflict t={t}: R{ids[i]},R{ids[j]}')
    if waypoints is not None:
        for r, points in waypoints.items():
            itinerary_check(paths[r],points,partial)
    return sum(len(p) for p in paths.values())


def itinerary_check(path, points, partial=False):
    cursor = 0
    costs = [0,0]
    for w in points:
        dest = tuple(w.position)
        arrival = next((t for t in range(cursor,len(path)) if tuple(path[t])==dest),None)
        if arrival is None:
            require(partial, 'missing service waypoint')
            return None
        finish = arrival+w.hold
        end = min(finish,len(path)-1)
        require(all(tuple(path[t])==dest for t in range(arrival,end+1)), 'interrupted service')
        if finish >= len(path):
            require(partial, 'truncated service')
            return None
        if w.delivery:
            costs[0] += finish if w.urgent else 0
            costs[1] += finish
        cursor = finish
    if points:
        require(all(tuple(p)==tuple(points[-1].position) for p in path[cursor:]), 'left persistent endpoint')
    return tuple(costs+[len(path)-1])


def assignment_oracle(slots, tasks, costs, prefs=None):
    dimensions = 8 if prefs is not None else 7
    best = None
    def visit(i, used, values):
        nonlocal best
        if i == len(slots):
            score = tuple(values)
            if best is None or score < best:
                best = score
            return
        visit(i+1,used,values)
        for task in tasks:
            if task.id in used:
                continue
            eta = costs[slots[i].robot_id,task.id]
            if eta is None or eta>=10**6:
                continue
            v = list(values)
            v[5-task.priority] -= 1
            if prefs is not None:
                v[5] += prefs[slots[i].robot_id,task.id]
            v[-2] += eta
            v[-1] += task.created_at
            visit(i+1,used|{task.id},v)
    visit(0,set(),[0]*dimensions)
    return best


def assignment_score(pairs, slots, tasks, costs, prefs=None):
    require(len(set(pairs.values()))==len(pairs), 'duplicate task owner')
    robots = {s.robot_id for s in slots}
    indexed = {t.id:t for t in tasks}
    values = [0]*(8 if prefs is not None else 7)
    for r,t in pairs.items():
        require(r in robots and t in indexed, 'unknown pair')
        eta = costs[r,t]
        require(eta is not None and eta<10**6, 'forbidden edge')
        values[5-indexed[t].priority] -= 1
        if prefs is not None:
            values[5] += prefs[r,t]
        values[-2] += eta
        values[-1] += indexed[t].created_at
    return tuple(values)


def single_oracle(grid, start, points, vertices, edges, horizon):
    """Time-expanded DP. State records actual time and service progress.

    Each layer keeps all distinct delivery-cost labels, not merely earliest arrival.
    Occupancy and edges are explicit sets generated independently of Reservations.
    """
    def progress(p,t,k,left,urgent,total):
        # left>0 means this tick must remain at the currently active service cell.
        while k<len(points) and left==0 and tuple(points[k].position)==p:
            w=points[k]
            if w.hold:
                return k,w.hold,urgent,total
            urgent += t if w.delivery and w.urgent else 0
            total += t if w.delivery else 0
            k+=1
        return k,left,urgent,total
    if (start,0) in vertices:
        return None
    k,left,u,total = progress(start,0,0,0,0,0)
    states={(start,k,left,u,total)}
    best=None
    for t in range(horizon+1):
        following=set()
        for p,k,left,u,total in states:
            if k==len(points):
                if all((p,s) not in vertices for s in range(t,horizon+1)):
                    score=(u,total,t)
                    if best is None or score<best:
                        best=score
                continue
            options=[p] if left else [p]+grid.neighbors(p)
            if t==horizon:
                continue
            for q in options:
                if (q,t+1) in vertices or (p,q,t+1) in edges:
                    continue
                nk,nleft,nu,ntotal=k,left,u,total
                if left:
                    nleft-=1
                    if nleft==0:
                        w=points[k]
                        nu += t+1 if w.delivery and w.urgent else 0
                        ntotal += t+1 if w.delivery else 0
                        nk+=1
                nk,nleft,nu,ntotal=progress(q,t+1,nk,nleft,nu,ntotal)
                following.add((q,nk,nleft,nu,ntotal))
        states=following
    return best


def joint_oracle(grid, starts, goals, horizon):
    """Tiny synchronous joint BFS with persistent goals (no production helpers)."""
    target=tuple(goals)
    initial=tuple(starts)
    states={initial}
    for tick in range(horizon+1):
        if target in states:
            return tick
        following=set()
        for state in states:
            opts=[[p] if p==goals[i] else [p]+grid.neighbors(p) for i,p in enumerate(state)]
            for step in product(*opts):
                if len(set(step))!=len(step):
                    continue
                if any(step[i]==state[j] and step[j]==state[i] for i in range(len(step)) for j in range(i)):
                    continue
                following.add(step)
        states=following
    return None


def business_check(sim, previous=None):
    owners=[]
    for r in sim.robots:
        require(sim.warehouse.is_open(r.position), 'actual robot on blocked cell')
        require(r.loaded==(r.phase in ('to_delivery','unloading')), 'cargo/phase mismatch')
        for task_id in (r.task_id,r.next_task_id):
            if task_id is not None:
                owners.append(task_id)
                require(task_id in sim.tasks, 'unknown owned task')
        if r.task_id is not None:
            task=sim.tasks[r.task_id]
            require(task.robot_id==r.id and task.status==r.phase, 'task/robot disagreement')
        if r.next_task_id is not None:
            task=sim.tasks[r.next_task_id]
            require(task.robot_id==r.id and task.status=='reserved','reservation disagreement')
    require(len(set(owners))==len(owners),'duplicate actual ownership')
    require(len({r.position for r in sim.robots})==len(sim.robots),'actual overlap')
    for t in sim.tasks.values():
        if t.assignment_mode=='forced' and t.robot_id is not None:
            require(t.robot_id==t.assignment_robot_id,'forced owner violated')
    if previous:
        oldrobots,oldtasks=previous
        for r in sim.robots:
            old=oldrobots[r.id]
            if old['phase'] in ('picking','unloading'):
                require(r.position==tuple(old['position']), 'moved during service')
            if old['loaded'] and r.loaded:
                require(r.task_id==old['task_id'], 'cargo migrated')
        for tid,old in oldtasks.items():
            t=sim.tasks[tid]
            if old['status'] in ('completed','cancelled'):
                require(t.status==old['status'],'terminal task changed')
            if old['status'] in ('picking','to_delivery','unloading') and t.status!='completed':
                require(t.robot_id==old['robot_id'],'atomic owner changed')