"""Bounded reservation planning after CBS exceeds its budget.

Every route reserves vertices, reverse edges and its final parking occupancy.
Different priority orders may find a feasible solution, but do not prove joint
path optimality or completeness. Never execute a partial set of routes.
"""
from time import monotonic

from planning.astar import search, PlanningTimeout
from planning.cbs import PlanResult
from planning.validation import validate_paths


def plan_reserved(warehouse, starts, itineraries, seconds, horizon):
    begin = monotonic()
    deadline = begin+seconds
    idle = [r for r in starts if not any(w.delivery for w in itineraries[r])]
    active = [r for r in starts if r not in idle]
    urgent = lambda r: any(w.urgent for w in itineraries[r])

    def length(r):
        p, total = starts[r], 0
        for waypoint in itineraries[r]:
            total += warehouse.distance(p, waypoint.position)+waypoint.hold
            p = waypoint.position
        return total

    orders = []
    for order in (active, list(reversed(active)), sorted(active,key=length),
                  sorted(active,key=length,reverse=True)):
        candidate = tuple(idle+sorted(order,key=lambda r:not urgent(r)))
        if candidate not in orders:
            orders.append(candidate)
    # Rotations break equal-cost symmetries in a densely occupied starting area.
    for i in range(1,len(active)):
        candidate = tuple(idle+sorted(active[i:]+active[:i],key=lambda r:not urgent(r)))
        if candidate not in orders:
            orders.append(candidate)
    try:
        for index, order in enumerate(orders):
            if monotonic() >= deadline:
                break
            # A difficult ordering must leave time for other candidate orderings.
            attempt_deadline = min(deadline,monotonic()+max(.08,(deadline-monotonic())/min(4,len(orders)-index)))
            restrictions, paths, costs = set(), {}, {}
            complete = True
            try:
                for robot in order:
                    result = search(warehouse,starts[robot],itineraries[robot],
                                    restrictions,attempt_deadline,horizon)
                    if result is None:
                        complete = False
                        break
                    path, cost = result
                    paths[robot], costs[robot] = path, cost
                    for tick in range(horizon+1):
                        p = path[min(tick,len(path)-1)]
                        restrictions.add(("v",tick,p))
                        if tick:
                            previous = path[min(tick-1,len(path)-1)]
                            restrictions.add(("e",tick,p,previous))
            except PlanningTimeout:
                complete = False
            if complete:
                validate_paths(warehouse,starts,paths)
                total = tuple(sum(cost[i] for cost in costs.values()) for i in range(3))
                return PlanResult(paths,"success",monotonic()-begin,0,total,"reservations")
    except PlanningTimeout:
        pass
    return PlanResult({},"timeout",monotonic()-begin,0,method="reservations")
