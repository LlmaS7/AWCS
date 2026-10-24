"""Safe-interval search with ordered atomic service waypoints.

Original AWCS implementation inspired by Phillips & Likhachev (ICRA 2011).
Conservative Pareto labels retain arrival/completed-delivery tradeoffs. Returns
the same (path, lexicographic cost) contract as space-time A*.
"""
from heapq import heappop, heappush
from itertools import count
from time import monotonic
from planning.astar import PlanningTimeout


def search(warehouse, start, waypoints, reservations, deadline, horizon, cancel=None,
           partial=False):
    serial = count()
    # 搜索从相对时刻0开始，起点必须存在包含该时刻的安全区间。
    intervals = reservations.safe_intervals(start,horizon)
    initial_interval = next((i for i,(a,b) in enumerate(intervals) if a==0),None)
    if initial_interval is None:
        return None

    # 到达作业点后连续完成装卸；整个停留必须容纳在同一安全区间内。
    def normalize(p, tick, k, done, end):
        arrival = tick
        while k < len(waypoints) and waypoints[k].position == p:
            w = waypoints[k]
            if tick+w.hold > end:
                return None
            tick += w.hold
            if w.delivery:
                done = (done[0]+(tick if w.urgent else 0),done[1]+tick)
            k += 1
        return tick,k,done,arrival

    # 忽略其他机器人未来的避让，用静态距离和必要装卸构造剩余代价下界。
    def bound(p,tick,k,done):
        urgent,total = done
        for w in waypoints[k:]:
            tick += warehouse.distance(p,w.position)+w.hold
            if w.delivery:
                urgent += tick if w.urgent else 0
                total += tick
            p = w.position
        return urgent,total,tick

    normal = normalize(start,0,0,(0,0),intervals[initial_interval][1])
    if normal is None:
        return None
    tick,k,done,_ = normal
    # record = position, interval index, time AFTER service, next waypoint,
    # completed costs, parent, time of arrival before service.
    # 状态依次保存：位置、区间编号、作业后时刻、下一作业点、
    # 已完成交付代价、父状态、作业前到达时刻；代价区分紧急交付与全部交付。
    records = [(start,initial_interval,tick,k,done,None,0)]
    labels = {(start,initial_interval,k): [0]}
    alive = {0}
    # With exact static distances, many shortest-path prefixes have identical
    # bounds. Prefer deeper labels on ties instead of flooding the whole room.
    frontier = [(bound(start,tick,k,done), -tick, next(serial), 0)]
    boundary = None

    # 安全区间搜索可跳过多个等待时刻；回溯时补齐成逐时间步的位置序列。
    def path_to(rid):
        chain = []
        while rid is not None:
            chain.append(records[rid])
            rid = records[rid][5]
        chain.reverse()
        path = [start]
        for p,_,t,_,_,_,arrival in chain:
            if arrival:
                while len(path) < arrival:
                    path.append(path[-1])
                path.append(p)
            while len(path)<=t:
                path.append(p)
        return path

    expanded = 0
    while frontier:
        _,_,_,rid = heappop(frontier)
        if rid not in alive:
            continue
        expanded += 1
        if expanded%32==0 and (monotonic()>=deadline or (cancel and cancel.is_set())):
            raise PlanningTimeout
        p,interval,t,k,done,_,_ = records[rid]
        _,end = reservations.safe_intervals(p,horizon)[interval]
        # 全部作业完成后，终点还必须允许持续停车到规划范围末端。
        if k==len(waypoints) and end==horizon:
            return path_to(rid),(done[0],done[1],t)
        if k==len(waypoints):
            # Parking is persistent. A visit before a future reservation cannot
            # be counted as completion followed by escape to an unrelated cell.
            continue
        if partial and end==horizon:
            # A stopping certificate, not a claim of completing this itinerary.
            score = bound(p,horizon,k,done)
            if boundary is None or score < boundary[0]:
                boundary = score,rid
            if t==horizon:
                return path_to(rid),score
        for q in warehouse.neighbors(p):
            for j,(a,b) in enumerate(reservations.safe_intervals(q,horizon)):
                # 最早下一步到达邻格；若邻格尚不可用，则在当前格等待后再出发。
                arrival = max(t+1,a)
                if arrival>b or arrival-1>end:
                    continue
                # 前面的条件同时检查邻格到达时刻和当前格等待期限，再避开反向边冲突。
                arrival = reservations.next_edge_time(p,q,arrival)
                if arrival>b or arrival-1>end:
                    continue
                # 边冲突可能推迟到达，需再次检查区间，并确认装卸停留能否完整执行。
                normal = normalize(q,arrival,k,done,b)
                if normal is None:
                    continue
                nt,nk,nd,_ = normal
                if nk==len(waypoints) and b<horizon:
                    continue
                key = q,j,nk
                # 同位置、同区间、同作业进度下，只保留时间和交付代价不被支配的状态。
                previous = labels.get(key,[])
                if any(records[i][2]<=nt and records[i][4][0]<=nd[0]
                       and records[i][4][1]<=nd[1] for i in previous if i in alive):
                    continue
                for i in previous:
                    if nt<=records[i][2] and nd[0]<=records[i][4][0] and nd[1]<=records[i][4][1]:
                        alive.discard(i)
                nid = len(records)
                records.append((q,j,nt,nk,nd,rid,arrival))
                labels[key] = [i for i in previous if i in alive]+[nid]
                alive.add(nid)
                heappush(frontier,(bound(q,nt,nk,nd),-nt,next(serial),nid))
    if partial and boundary is not None:
        _,rid = boundary
        path = path_to(rid)
        path.extend([path[-1]] * (horizon+1-len(path)))
        return path,boundary[0]
    return None
