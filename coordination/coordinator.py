"""Pure finite-candidate task/path coupling under one end-to-end budget."""
from copy import deepcopy
from time import monotonic
from coordination.contracts import Proposal, snapshot_for_planning
from planning.cbs import plan as cbs
from planning.scalable import plan as sipp
from planning.validation import validate_itineraries


def solve(snapshot, key=None, cancel=None):
    started = monotonic()
    profile = snapshot.profile
    # 候选匹配与路径协调共享本轮预算，不能为每个候选重置完整时长。
    deadline = started+profile.seconds
    baseline = None
    best, best_score = None, None
    attempted, expanded, cbs_nodes, reservation_orders = 0, 0, 0, 0
    statuses = []
    forbidden = [frozenset()]
    for index in range(profile.candidates if profile.coupling=='candidate' else 1):
        if index>=len(forbidden) or monotonic()>=deadline or (cancel and cancel.is_set()):
            break
        # 在独立快照上试算，最终通过校验的方案才交回仿真状态提交。
        candidate = snapshot_for_planning(snapshot)
        candidate._forbidden_edges = forbidden[index]
        if profile.coupling=='estimated':
            candidate._estimated_congestion = True
        candidate.dispatch()
        prefix = candidate.assignment['priority_prefix']
        if baseline is None:
            baseline = prefix
            eligible = {t.id for t in snapshot.tasks.values() if t.status=='pending'}
            # Bounded alternative matchings, never factorial enumeration. Only
            # uncommitted pending tasks may change owner in ordinary dispatch.
            for robot,task in candidate.assignment['pairs'].items():
                if task in eligible and len(forbidden)<profile.candidates:
                    forbidden.append(frozenset({(robot,task)}))
        # 联动评估须保留基线的两阶段等级目标与软偏好，不能用路线收益换取退让。
        elif prefix!=baseline:
            continue
        starts = {r.id:r.position for r in candidate.robots}
        routes = {r.id:candidate.itinerary(r) for r in candidate.robots}
        lower = 0
        independent = [0,0,0]
        for robot,points in routes.items():
            p,length = starts[robot],0
            for w in points:
                length += candidate.warehouse.distance(p,w.position)+w.hold
                if w.delivery:
                    independent[0] += length if w.urgent else 0
                    independent[1] += length
                p = w.position
            lower = max(lower,length)
            independent[2] += length
        partial = profile.mode=='rolling'
        horizon = profile.window if partial else max(260,lower+max(40,len(starts)*4))
        result = None
        # 小规模完整路径先尝试短预算CBS；未成功则用剩余预算做SIPP预约协调。
        if not partial and len(starts)<=8 and index==0:
            result = cbs(candidate.warehouse,starts,routes,
                         seconds=min(.25,max(.001,deadline-monotonic())),horizon=horizon)
            expanded += result.expanded
            cbs_nodes += result.expanded
        if result is None or result.status!='success':
            remaining = deadline-monotonic()
            if remaining<=0:
                break
            result = sipp(candidate.warehouse,starts,routes,remaining,horizon,cancel,partial)
            expanded += result.expanded
            reservation_orders += result.expanded
        attempted += 1
        statuses.append(result.status)
        if result.status!='success':
            continue
        validate_itineraries(candidate.warehouse,starts,result.paths,routes,partial)
        for r in candidate.robots:
            r.path = result.paths[r.id]
        candidate.assert_invariants()
        score = result.cost
        # 仅比较已校验可行的有限候选，不代表所有分配与路线的全局最优。
        if best is None or score<best_score:
            best, best_score = candidate,score
            best._selected_method = result.method
        if partial:
            break
        if index==0 and tuple(result.cost[:2])==tuple(independent[:2]):
            # No delivery was delayed relative to the matching lower bound.
            # Do not spend extra seconds merely improving final parking ties.
            break
    elapsed = monotonic()-started
    scope = {'off':'两阶段硬优先级 / 软偏好 / 静态ETA匹配＋协调可行路线',
             'estimated':'两阶段硬优先级 / 软偏好 / 冻结占用估计匹配＋协调路线',
             'candidate':'有限候选集 / 两阶段硬优先级 / 软偏好 / 路径完成时间'}[profile.coupling]
    diagnostics = {'candidates':attempted,'expanded':expanded,'statuses':statuses,
                   'scope':scope,
                   'global_optimal':False,'mode':profile.mode,'coupling':profile.coupling}
    if best is None:
        return Proposal(key,False,status='cancelled' if cancel and cancel.is_set() else
                        ('timeout' if monotonic()>=deadline else 'no_safe_plan'),
                        diagnostics=diagnostics,metrics={'last_plan_ms':elapsed*1000})
    assignment = best.assignment
    assignment['scope'] = diagnostics['scope']
    assignment['cost_model'] = '静态ETA匹配；'+('有限候选按联合路径完成时间改进' if profile.coupling=='candidate' else '静态/预约估计')
    assignment['path_cost'] = list(best_score)
    assignment['candidate_count'] = attempted
    metrics = {'planning_seconds':snapshot.metrics['planning_seconds']+elapsed,
               'plans':snapshot.metrics['plans']+1,'last_plan_ms':elapsed*1000,
               'cbs_nodes':cbs_nodes,'reservation_orders':reservation_orders,
               'planner':best._selected_method,
               'preemptions':best.metrics['preemptions'],
               'reservation_plans':snapshot.metrics['reservation_plans']+int(best._selected_method.startswith('SIPP')),
               'candidate_count':attempted,'planning_scope':diagnostics['scope']}
    return Proposal(key,True,best.robots,best.tasks,assignment,metrics,'success',diagnostics,
                    profile.execute if partial else None)
