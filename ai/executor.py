"""Executed exclusively on Controller's actor thread; never touches a network."""
from collections import OrderedDict
from copy import deepcopy
import json

from .tools import CANCELLABLE, WRITES, normalize, query, task_view


def business_fingerprint(envelope):
    return json.dumps([envelope['name'], envelope['arguments'], envelope.get('sources')],
                      sort_keys=True, ensure_ascii=False)


class BusinessExecutor:
    def __init__(self, controller):
        self.controller = controller
        self.ledger = OrderedDict()

    def validate(self, actions):
        sim = self.controller.sim
        # 预演批内任务等级和状态变化，提前发现“取消后再升级”等不合法组合。
        projected = {k: [t.priority, t.status] for k, t in sim.tasks.items()}
        for action in actions:
            if action["operation"] == "copy":
                if action["source_task_id"] not in sim.tasks:
                    raise ValueError("复制来源任务不存在")
                continue
            if action["operation"] == "add":
                if action["pickup"] > len(sim.warehouse.pickups) or action["delivery"] > len(sim.warehouse.deliveries):
                    raise ValueError("当前场景没有此取货点或配送点")
                continue
            task_id = action["task_id"]
            if task_id not in projected:
                raise ValueError(f"T{task_id:03}不存在")
            level, phase = projected[task_id]
            if action["operation"] == "assignment":
                sim.validate_assignment(task_id, action["mode"], action["robot_id"])
            elif action["operation"] == "cancel":
                if phase not in CANCELLABLE:
                    raise ValueError(f"T{task_id:03}已开始装货或已经结束，不能取消")
                projected[task_id][1] = "cancelled"
            else:
                if phase in ("completed", "cancelled"):
                    raise ValueError(f"T{task_id:03}已经结束，不能升级")
                target = min(5, level + 1) if action["mode"] == "increment" else action["priority"]
                if target < level:
                    raise ValueError(f"T{task_id:03}不支持降低等级")
                projected[task_id][0] = target

    def run(self, envelope):
        """Synchronous compatibility driver; the actor drives iterate asynchronously."""
        iterator = self.iterate(envelope)
        try:
            next(iterator)
            while True:
                try:
                    self.controller._plan()
                except Exception as exc:
                    iterator.throw(exc)
                else:
                    next(iterator)
        except StopIteration as finished:
            return finished.value

    def iterate(self, envelope):
        c = self.controller
        name, raw = envelope["name"], envelope["arguments"]
        key = envelope["operation_id"]
        fingerprint = business_fingerprint(envelope)
        # 当前运行内，同一操作标识须对应相同请求；重试返回已有结果，避免重复写入。
        if key in self.ledger:
            old = self.ledger[key]
            if old["fingerprint"] != fingerprint:
                raise ValueError("同一操作标识不能使用不同参数")
            return deepcopy(old["result"])
        valid = envelope.get("valid", lambda: True)
        def fresh():
            return envelope["generation"] == c.generation and valid()
        # 场景切换或请求失效后拒绝旧指令，避免旧地图的操作被写入新场景。
        if not fresh():
            actions = ([{'operation': 'add', 'outcome': 'not_executed', 'reason': '请求已停止或场景已变化'}
                        for _ in envelope['sources']] if 'sources' in envelope else [])
            return {"status": "finished", "actions": actions, "error": "请求已停止或工作场景已更新，未执行"}
        args = normalize(name, raw)
        sources = envelope.get('sources')
        if sources is not None:
            from task_imports.schema import validate_source
            if name != 'create_tasks' or not isinstance(sources, list) or len(sources) != len(args):
                raise ValueError('导入来源与创建项不一致')
            sources = [validate_source(source) for source in sources]
        if name not in WRITES:
            return query(c.sim, name, args)
        result = {"status": "running", "actions": []}
        self.ledger[key] = {"fingerprint": fingerprint, "result": result}
        try:
            # 整批先预检；执行时还会逐项校验，中途失败保留已生效项，不做事务回滚。
            self.validate(args)
        except ValueError as exc:
            result.update(status="finished", error=str(exc), actions=[{"operation": a["operation"], "outcome": "not_executed", "reason": "整批预检未通过"} for a in args])
            return deepcopy(result)
        stop_reason = None
        for action_index, action in enumerate(args):
            if stop_reason or not fresh():
                result["actions"].append({"operation": action["operation"], "outcome": "not_executed", "reason": stop_reason or "请求已停止或工作场景已更新"})
                continue
            try:
                self.validate([action])
            except ValueError as exc:
                stop_reason = str(exc)
                result["actions"].append({"operation": action["operation"], "outcome": "rejected", "reason": stop_reason})
                continue
            op = action["operation"]
            task_id = c.sim.next_id if op in ("add", "copy") else action["task_id"]
            target = None
            if op == "priority":
                current = c.sim.tasks[task_id].priority
                target = min(5, current + 1) if action["mode"] == "increment" else action["priority"]
                if current == target:
                    result["actions"].append({"operation": op, "outcome": "no_change", **task_view(c.sim.tasks[task_id], c.sim.warehouse), "reason": "任务已经达到此等级"})
                    continue
            if op == "assignment":
                task = c.sim.tasks[task_id]
                if (task.assignment_mode, task.assignment_robot_id) == (action["mode"], action["robot_id"]):
                    result["actions"].append({"operation": op, "outcome": "no_change", **task_view(task, c.sim.warehouse), "reason": "任务已经使用此分配方式"})
                    continue
            item = {"operation": op, "outcome": "not_executed", "task_id": f"T{task_id:03}"}
            result["actions"].append(item)
            try:
                if op == "add":
                    c.sim.command("add", pickup=c.sim.warehouse.pickups[action["pickup"]-1], delivery=c.sim.warehouse.deliveries[action["delivery"]-1], priority=action["priority"],
                                  source=sources[action_index] if sources is not None else None)
                elif op == "priority":
                    c.sim.command("priority", task_id=task_id, priority=target)
                elif op == "assignment":
                    c.sim.command("assignment", task_id=task_id, mode=action["mode"], robot_id=action["robot_id"])
                elif op == "copy":
                    c.sim.command("copy", source_task_id=action["source_task_id"], priority=action.get("priority"))
                else:
                    c.sim.command("cancel", task_id=task_id)
                task = c.sim.tasks.get(task_id)
                applied = self.applied(op, task, action, target)
                item.update(outcome="applied" if applied else "rejected")
                if task:
                    item.update(task_view(task, c.sim.warehouse))
                if not applied:
                    stop_reason = "业务条件已改变，操作未生效"
                    item["reason"] = stop_reason
                    continue
                # 先发布已生效的业务结果，再让出执行权等待规划；规划失败不撤销已创建任务。
                # Record committed domain outcome BEFORE planning can fail.
                c._publish()
                if envelope.get('on_progress'):
                    envelope['on_progress'](deepcopy(result))
                yield task_id
                if envelope['generation']!=c.generation:
                    item['planning'] = 'superseded'
                    item['reason'] = '原场景操作已生效，工作场景随后已更新'
                    stop_reason = item['reason']
                    continue
                c.sim.assert_invariants()
                item.update(task_view(c.sim.tasks[task_id], c.sim.warehouse))
                # 分别报告“业务已生效”和“路线可执行”，避免将规划失败误报成下单失败。
                item["planning"] = "unavailable" if c.sim.dirty else "available"
                if c.sim.dirty:
                    stop_reason = "任务操作已生效，当前预算内尚未形成可执行路线"
                    item["reason"] = stop_reason
            except Exception:
                task = c.sim.tasks.get(task_id)
                if self.applied(op, task, action, target):
                    item.update(outcome="applied", **task_view(task, c.sim.warehouse))
                stop_reason = "业务处理或路线生成异常，请查看已生效结果；未继续执行"
                item.update(planning="unavailable", reason=stop_reason)
                c.sim.paused = True
                c._publish()
        result["status"] = "finished"
        while len(self.ledger) > 2048:
            expired = next((k for k,v in self.ledger.items() if v['result']['status']=='finished'),None)
            if expired is None:
                break
            del self.ledger[expired]
        return deepcopy(result)

    @staticmethod
    def applied(op, task, action, target):
        if task is None:
            return False
        if op == "add":
            return True
        if op == "copy":
            return task.copied_from == action["source_task_id"]
        if op == "assignment":
            return (task.assignment_mode, task.assignment_robot_id) == (action["mode"], action["robot_id"])
        if op == "cancel":
            return task.status == "cancelled"
        return op == "priority" and task.priority == target
