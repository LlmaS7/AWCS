"""Budgeted safe-interval reservations and conflict-directed ordering repair."""
from time import monotonic
from planning.astar import PlanningTimeout
from planning.cbs import PlanResult
from planning.sipp import search
from planning.reservations import Reservations
from planning.validation import validate_paths, validate_itineraries
from planning.cbs import plan as joint_cbs


def plan(warehouse, starts, itineraries, seconds=3, horizon=260, cancel=None,
         partial=False):
    begin = monotonic()
    deadline = begin+seconds
    urgent = lambda r: any(w.urgent for w in itineraries[r])
    idle = [r for r in starts if not any(w.delivery for w in itineraries[r])]
    active = [r for r in starts if r not in idle]
    def length(r):
        p,total = starts[r],0
        for w in itineraries[r]:
            total += warehouse.distance(p,w.position)+w.hold
            p = w.position
        return total
    # 依次规划的先后顺序会影响可行性，因此在同一预算内尝试多种候选顺序。
    orders = []
    for robots in (sorted(active,key=length,reverse=True), active,
                   list(reversed(active)), sorted(active,key=length)):
        for prefix in (idle,[]):
            order = tuple(prefix+sorted(robots,key=lambda r:not urgent(r))+([] if prefix else idle))
            if order not in orders:
                orders.append(order)
    for shift in range(1,min(len(active),4)):
        order = tuple(idle+sorted(active[shift:]+active[:shift],key=lambda r:not urgent(r)))
        if order not in orders:
            orders.append(order)
    attempts, conflicts = 0, []
    def repair(robot, paths):
        if partial or not paths or attempts<6 or monotonic()>=deadline:
            return None
        # Select peers whose spatial routes intersect the blocked robot's
        # independent shortest itinerary, then solve ONLY that small group.
        p = starts[robot]
        cells = {p}
        for w in itineraries[robot]:
            while p!=w.position:
                distance = warehouse.distance(p,w.position)
                q = next((q for q in warehouse.neighbors(p)
                          if warehouse.distance(q,w.position)<distance),None)
                if q is None:break
                cells.add(q);p=q
        # 最多选3台与阻塞路线相交较多的机器人，与受阻机器人组成小组修复。
        peers = sorted(paths,key=lambda r:len(cells.intersection(paths[r])),reverse=True)[:3]
        group = set(peers+[robot])
        # 组外已规划路线保持固定，以顶点和反向边约束保护其通行安全。
        external = []
        for r,path in paths.items():
            if r in group:continue
            for tick in range(horizon+1):
                p = path[min(tick,len(path)-1)]
                external.append(('v',tick,p))
                if tick:
                    previous = path[min(tick-1,len(path)-1)]
                    if p!=previous:external.append(('e',tick,p,previous))
        for r in starts:
            if r in group or r in paths:continue
            first = itineraries[r][0]
            if first.position==starts[r]:
                external.extend(('v',t,starts[r]) for t in range(first.hold+1))
        def low_level(w,s,points,constraints,end,h):
            return search(w,s,points,Reservations.from_constraints(constraints),end,h,cancel)
        remaining = deadline-monotonic()
        if remaining<=.02:return None
        result = joint_cbs(warehouse,{r:starts[r] for r in group},
                           {r:itineraries[r] for r in group},min(.3,remaining),horizon,
                           external,low_level)
        return result if result.status=='success' else None
    index = 0
    while index<len(orders) and monotonic()<deadline:
        if cancel and cancel.is_set():
            return PlanResult({},'cancelled',monotonic()-begin,attempts,method='SIPP')
        order = orders[index]
        index += 1
        attempts += 1
        # A large fleet needs a useful first pass, especially when most terminal
        # slots are back in the shared spawn area. Splitting a 3-second budget
        # into thirds repeatedly abandoned otherwise feasible complete plans.
        # Keep 20% for ordering repair, within the SAME total deadline.
        share = .8 if attempts==1 and len(starts)>=24 and not partial else 1/min(3,len(orders)-index+1)
        attempt_end = min(deadline,monotonic()+max(.08,(deadline-monotonic())*share))
        table, paths, values = Reservations(), {}, {}
        failed = None
        try:
            for r in order:
                # 后车基于前车累计预约搜索；还须锁住尚未规划机器人的当前装卸区间。
                query = table.clone()
                # Initial atomic service locks of UNPLANNED peers are immutable.
                for peer in starts:
                    if peer==r or peer in paths:
                        continue
                    first = itineraries[peer][0]
                    if first.position==starts[peer] and first.hold:
                        query.block(starts[peer],0,first.hold)
                try:
                    result = search(warehouse,starts[r],itineraries[r],query,attempt_end,
                                    horizon,cancel,partial)
                except PlanningTimeout:
                    result = None
                if result is None:
                    repaired = repair(r,paths)
                    if repaired is not None:
                        paths.update(repaired.paths)
                        values.update(validate_itineraries(warehouse,
                            {p:starts[p] for p in repaired.paths},repaired.paths,
                            {p:itineraries[p] for p in repaired.paths}))
                        table = Reservations()
                        for path in paths.values():table.add_path(path)
                        attempt_end = min(deadline,max(attempt_end,monotonic()+.15))
                        continue
                    failed = r
                    break
                path,cost = result
                paths[r],values[r] = path,cost
                # 将成功路线写入共享预约表，下一台机器人据此避让。
                table.add_path(path)
        except PlanningTimeout:
            failed = r
        if failed is None and len(paths)==len(starts):
            # 整组路线齐全后仍独立检查冲突，避免仅凭各次搜索成功就提交执行。
            validate_paths(warehouse,starts,paths)
            total = tuple(sum(c[i] for c in values.values()) for i in range(3))
            return PlanResult(paths,'success',monotonic()-begin,attempts,total,'SIPP-window' if partial else 'SIPP')
        # Repair a failed priority ordering by moving the blocked agent before
        # those whose reservations prevented it. This never changes task grades.
        # 受阻机器人提前后重新规划整组路线；改变搜索顺序，不改变业务任务等级。
        if failed is not None and failed in order and len(orders)<16:
            repaired = (failed,)+tuple(r for r in order if r!=failed)
            if repaired not in orders:
                orders.insert(index,repaired)
            conflicts.append(failed)
    return PlanResult({},'timeout' if monotonic()>=deadline else 'ordering_exhausted',
                      monotonic()-begin,attempts,method='SIPP')
