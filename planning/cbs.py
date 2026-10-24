"""Conflict-Based Search for ordered pickup/delivery itineraries of a fleet.

High-level constraints branch on both robots; ordinary restrictions are
inserted first on ties. A budget exhaustion is reported as timeout, not no-solution.
"""
from dataclasses import dataclass
from heapq import heappop, heappush
from itertools import count
from time import monotonic
from config import PLAN_SECONDS, PLAN_HORIZON, CBS_NODE_LIMIT
from planning.astar import search, PlanningTimeout
from planning.validation import first_conflict, validate_paths


@dataclass
class PlanResult:
    paths: dict
    status: str
    seconds: float
    expanded: int
    cost: tuple = ()
    method: str = "CBS"


def plan(warehouse, starts, itineraries, seconds=PLAN_SECONDS, horizon=PLAN_HORIZON,
         base_constraints=(), searcher=None):
    begin = monotonic()
    deadline = begin + seconds
    constraints = {robot: frozenset(base_constraints) for robot in starts}
    low_level = searcher or search
    paths, costs = {}, {}
    serial = count()
    expanded = 0

    def total(values):
        return tuple(sum(cost[i] for cost in values.values()) for i in range(3))

    try:
        for robot in starts:
            result = low_level(warehouse, starts[robot], itineraries[robot], constraints[robot], deadline, horizon)
            if result is None:
                return PlanResult({}, "horizon_exhausted", monotonic() - begin, 0)
            paths[robot], costs[robot] = result
        frontier = [(total(costs), next(serial), constraints, paths, costs)]
        seen = set()
        while frontier:
            if monotonic() >= deadline or expanded >= CBS_NODE_LIMIT:
                raise PlanningTimeout
            score, _, restrictions, routes, values = heappop(frontier)
            key = tuple((r, restrictions[r]) for r in sorted(starts))
            if key in seen:
                continue
            seen.add(key)
            expanded += 1
            conflict = first_conflict(routes)
            if conflict is None:
                validate_paths(warehouse, starts, routes)
                return PlanResult(routes, "success", monotonic() - begin, expanded, score)
            order = sorted((conflict.a, conflict.b), key=lambda r:
                           any(w.urgent for w in itineraries[r]))
            for robot in order:
                if conflict.position is not None:
                    addition = ("v", conflict.time, conflict.position)
                else:
                    edge = conflict.edge_a if robot == conflict.a else conflict.edge_b
                    addition = ("e", conflict.time, *edge)
                changed = {**restrictions, robot: restrictions[robot] | {addition}}
                result = low_level(warehouse, starts[robot], itineraries[robot],
                                changed[robot], deadline, horizon)
                if result is None:
                    continue
                new_path, cost = result
                new_routes = {**routes, robot: new_path}
                new_costs = {**values, robot: cost}
                heappush(frontier, (total(new_costs), next(serial), changed, new_routes, new_costs))
    except PlanningTimeout:
        return PlanResult({}, "timeout", monotonic() - begin, expanded)
    return PlanResult({}, "horizon_exhausted", monotonic() - begin, expanded)

