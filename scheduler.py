"""Polynomial matching for fleets; legacy exponential DP is a test oracle.

Lexicographic objective: maximize assigned priority-5 count, then priority-4,
etc.; then satisfy optional available-robot preferences, then minimize total ETA.
Arrival order breaks remaining ties. Forced owners are excluded by the cost matrix.
This is exact under supplied constraints, not global lifelong optimality.
"""
from dataclasses import dataclass
from config import LOAD_TICKS, UNLOAD_TICKS


@dataclass(frozen=True)
class Slot:
    robot_id: int
    origin: tuple[int, int]
    release: int = 0
    deferred: bool = False


def completion_cost(warehouse, slot, task):
    # 从槽位可释放时刻起，累计去取货、装货、配送和卸货的预计时间步。
    # 网格最短路估计不包含后续多机器人协调产生的全部避让等待。
    return (slot.release + warehouse.distance(slot.origin, task.pickup) + LOAD_TICKS
            + warehouse.distance(task.pickup, task.delivery) + UNLOAD_TICKS)


def legacy_matching(slots, tasks, cost, preference=None):
    """Dynamic programming over used robot masks; each task is used at most once."""
    # score = priority counts, optional preference penalty, ETA sum, arrival tie-break.
    empty = (0,) * (8 if preference else 7)
    eta_index = 6 if preference else 5
    states = {0: (empty, {})}
    for task in sorted(tasks, key=lambda t: t.id):
        estimates = [cost(slot, task) for slot in slots]
        following = dict(states)
        for mask, (score, pairs) in states.items():
            for index, slot in enumerate(slots):
                if mask & (1 << index):
                    continue
                eta = estimates[index]
                if eta >= 10**6:
                    continue
                updated = list(score)
                updated[5 - task.priority] -= 1
                if preference:
                    updated[5] += preference(slot, task)
                updated[eta_index] += eta
                updated[eta_index + 1] += task.created_at
                new_mask = mask | (1 << index)
                value = (tuple(updated), {**pairs, slot.robot_id: task.id})
                if new_mask not in following or value[0] < following[new_mask][0]:
                    following[new_mask] = value
        states = following
    score, pairs = min(states.values(), key=lambda item: item[0])
    return pairs, score


def exact_matching(slots, tasks, cost, preference=None):
    from coordination.assignment import match
    return match(slots, tasks, cost, preference)


def minimum_assignment(costs):
    """Rectangular Hungarian algorithm: assign every row to a distinct column."""
    n = len(costs)
    if n == 0:
        return []
    m = len(costs[0])
    if m < n or any(len(row) != m for row in costs):
        raise ValueError("停车位不足或代价矩阵尺寸错误")
    # u/v 为行列势，matched 记录列对应的行，previous 回溯增广路径。
    # 下标0是辅助入口；业务矩阵下标在取值时减一。
    u, v, matched, previous = [0]*(n+1), [0]*(m+1), [0]*(m+1), [0]*(m+1)
    for row in range(1, n+1):
        matched[0] = row
        column = 0
        # slack 维护当前交替树到各未访问列的最小约化代价。
        slack, used = [float("inf")]*(m+1), [False]*(m+1)
        while True:
            used[column] = True
            current = matched[column]
            delta, following = float("inf"), 0
            for j in range(1, m+1):
                if used[j]:
                    continue
                reduced = costs[current-1][j-1]-u[current]-v[j]
                if reduced < slack[j]:
                    slack[j], previous[j] = reduced, column
                if slack[j] < delta:
                    delta, following = slack[j], j
            # 调整势与松弛量，使交替树能沿新的零约化代价边继续扩展。
            for j in range(m+1):
                if used[j]:
                    u[matched[j]] += delta; v[j] -= delta
                else:
                    slack[j] -= delta
            column = following
            if matched[column] == 0:
                break
        # 找到未匹配列后，沿前驱反转匹配，使当前行加入整体分配。
        while column:
            following = previous[column]
            matched[column] = matched[following]
            column = following
    result = [0]*n
    for j in range(1, m+1):
        if matched[j]:
            result[matched[j]-1] = j-1
    return result


def optimal_parking(warehouse, origins, current=None):
    """Minimize total distance, then parking indices in robot order, exactly."""
    parks = warehouse.parking
    base = len(parks)+1
    # The lower digits encode deterministic ties without changing distance optimality.
    scale = base**len(origins)
    penalty = warehouse.width*warehouse.height*len(origins)+1 if current is not None else 0
    # Undirected distances are symmetric. Cache one BFS per origin, not one per
    # parking column: otherwise large parking pools thrash the bounded cache.
    costs = [[((warehouse.distance(park, origin) if current is not None else warehouse.distance(origin, park)) + (penalty*warehouse.topology.parking_risk(park) if current is not None else 0))*scale + j*base**(len(origins)-1-i)
              for j, park in enumerate(parks)] for i, origin in enumerate(origins)]
    return [parks[j] for j in minimum_assignment(costs)]

