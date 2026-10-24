"""Check padded paths, including occupancy after final arrival."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Conflict:
    a: int
    b: int
    time: int
    position: tuple[int, int] | None = None
    edge_a: tuple | None = None
    edge_b: tuple | None = None


def at(path, tick):
    # 短路线结束后继续视为停在终点，仍须参与后续时刻的冲突检查。
    return path[min(tick, len(path) - 1)]


def first_conflict(paths):
    ids = sorted(paths)
    for tick in range(max(map(len, paths.values()),default=0)):
        occupied, moves = {}, {}
        for robot in ids:
            p = at(paths[robot],tick)
            # 顶点冲突：同一时间步，两台机器人占据同一个格子。
            if p in occupied:
                return Conflict(occupied[p],robot,tick,position=p)
            occupied[p] = robot
            if tick:
                previous = at(paths[robot],tick-1)
                # 边冲突：本车 previous→p 与另一台的 p→previous 同步发生。
                peer = moves.get((p,previous))
                if peer is not None:
                    return Conflict(peer,robot,tick,edge_a=(p,previous),edge_b=(previous,p))
                moves[previous,p] = robot
    return None


def validate_paths(warehouse, starts, paths):
    for robot, path in paths.items():
        if not path or path[0] != starts[robot]:
            raise ValueError("Path does not start at the robot position")
        if any(not warehouse.is_open(p) for p in path):
            raise ValueError("Path enters an obstacle")
        if any(abs(a[0] - b[0]) + abs(a[1] - b[1]) > 1 for a, b in zip(path, path[1:])):
            raise ValueError("Path contains an invalid move")
    if first_conflict(paths):
        raise ValueError("Paths contain a collision")


def validate_itineraries(warehouse, starts, paths, itineraries, partial=False):
    """Independent geometry AND atomic-service check, replaying ordered waypoints."""
    if set(paths)!=set(starts) or set(itineraries)!=set(starts):
        raise ValueError('Plan must cover every robot')
    validate_paths(warehouse,starts,paths)
    costs = {}
    for robot,path in paths.items():
        k,remaining = 0,None
        urgent,total = 0,0
        points = itineraries[robot]
        for tick,p in enumerate(path):
            if k==len(points) and points and p!=points[-1].position:
                raise ValueError('Robot departed after persistent parking')
            while k<len(points):
                w = points[k]
                if remaining is None:
                    if p!=w.position:
                        break
                    remaining = w.hold
                if p!=w.position:
                    raise ValueError('Robot moved during atomic service')
                if remaining==0:
                    if w.delivery:
                        urgent += tick if w.urgent else 0
                        total += tick
                    k += 1
                    remaining = None
                    continue
                remaining -= 1
                break
        if not partial and k!=len(points):
            raise ValueError('Plan did not complete every service waypoint and parking')
        if not partial and points and path[-1]!=points[-1].position:
            raise ValueError('Plan must finish at its assigned parking point')
        costs[robot] = urgent,total,len(path)-1
    return costs

