"""Space-time A* through ordered service waypoints, then persistent parking.

Costs are lexicographic: urgent deliveries' completion-time sum, all delivery
completion-time sum, final parking time. BFS distances give admissible bounds.
Service holds are atomic: once started, the robot must stay until completion.
"""
from heapq import heappop, heappush
from itertools import count
from time import monotonic


class PlanningTimeout(Exception):
    pass


def search(warehouse, start, waypoints, constraints, deadline, horizon):
    vertices = {(c[1], c[2]) for c in constraints if c[0] == "v"}
    edges = {(c[1], c[2], c[3]) for c in constraints if c[0] == "e"}
    if (0, start) in vertices:
        return None
    final = waypoints[-1].position
    last_final_block = max((t for t, p in vertices if p == final), default=-1)

    def normalize(p, k, remaining, tick, done):
        while k < len(waypoints):
            waypoint = waypoints[k]
            if remaining == -1:
                if p != waypoint.position:
                    break
                remaining = waypoint.hold
            if remaining:
                break
            if waypoint.delivery:
                done = (done[0] + (tick if waypoint.urgent else 0), done[1] + tick)
            k += 1
            remaining = -1
        return k, remaining, done

    def bound(state, done):
        p, tick, k, remaining = state
        urgent, total = done
        elapsed = tick
        for index in range(k, len(waypoints)):
            waypoint = waypoints[index]
            if index == k and remaining >= 0:
                elapsed += remaining
            else:
                elapsed += warehouse.distance(p, waypoint.position) + waypoint.hold
            if waypoint.delivery:
                total += elapsed
                urgent += elapsed if waypoint.urgent else 0
            p = waypoint.position
        return urgent, total, elapsed

    k, remaining, done = normalize(start, 0, -1, 0, (0, 0))
    initial = (start, 0, k, remaining)
    serial = count()
    # Labels preserve completed waypoint costs: different histories can reach
    # the same space-time-progress state, and only the best label dominates.
    best = {initial: done}
    records = [(initial, None, done)]
    frontier = [(bound(initial, done), next(serial), 0)]
    expanded = 0
    while frontier:
        _, _, record_id = heappop(frontier)
        state, parent, done = records[record_id]
        if best.get(state) != done:
            continue
        expanded += 1
        if expanded % 64 == 0 and monotonic() >= deadline:
            raise PlanningTimeout
        p, tick, k, remaining = state
        if k == len(waypoints) and tick > last_final_block:
            path = []
            index = record_id
            while index is not None:
                item, index, _ = records[index]
                path.append(item[0])
            return list(reversed(path)), (done[0], done[1], tick)
        if tick >= horizon:
            continue
        choices = [p] if remaining > 0 or k == len(waypoints) else warehouse.neighbors(p) + [p]
        for q in choices:
            time = tick + 1
            if (time, q) in vertices or (time, p, q) in edges:
                continue
            rest = remaining - 1 if remaining > 0 else remaining
            nk, nr, nd = normalize(q, k, rest, time, done)
            nxt = (q, time, nk, nr)
            if nxt in best and best[nxt] <= nd:
                continue
            best[nxt] = nd
            records.append((nxt, record_id, nd))
            heappush(frontier, (bound(nxt, nd), next(serial), len(records) - 1))
    return None
