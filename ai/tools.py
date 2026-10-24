"""Ten bounded tools and a deliberate business-only view of domain state."""
import re
from copy import deepcopy

PHASES = {
    "pending": "已创建，待分配", "reserved": "已预约，完成当前搬运后接手",
    "to_pickup": "已分配，处于取货阶段", "picking": "处于装货阶段",
    "to_delivery": "已载货，处于配送阶段", "unloading": "处于卸货阶段",
    "completed": "已完成", "cancelled": "已取消", "idle": "空闲", "parking": "前往停车位",
}
CANCELLABLE = {"pending", "reserved", "to_pickup"}
WRITES = {"create_tasks", "raise_task_priorities", "cancel_tasks", "assign_task",
          "release_task_assignment", "set_task_preference", "copy_task"}
MAX_BATCH = 20


def object_schema(properties=None, required=None):
    return {"type": "object", "properties": properties or {}, "required": required or [], "additionalProperties": False}


def array_schema(items):
    return {"type": "array", "items": items, "minItems": 1, "maxItems": MAX_BATCH}


ID = {"type": "string"}
# 向模型公开业务工具及参数结构；任务分配和机器人路线由本地程序计算。
TOOLS = [
    {"type": "function", "function": {"name": name, "description": description, "parameters": schema}}
    for name, description, schema in [
        ("get_status", "查询真实业务状态；阶段不代表实际位移。可按任务或机器人筛选。", object_schema({"task_id": ID, "robot_id": ID})),
        ("get_locations", "查询货架名称/别名及其pickup_id、取货点和配送点名称/别名。货架编号不一定等于取货点编号；下单前查当前实际对应关系，歧义须澄清。", object_schema({"kind": {"type": "string", "enum": ["all", "pickup", "delivery", "shelf"]}})),
        ("create_tasks", "执行明确下单指令。用户货架/地点表达由你理解，先get_locations查询正式映射，再填写返回的P取货点ID和D配送点ID。缺少或歧义地点先追问，不用猜测。整批预检后顺序创建，普通默认2级，明确紧急5级；最多20项。", object_schema({"tasks": array_schema(object_schema({"pickup_id": ID, "delivery_id": ID, "priority": {"type": "integer", "minimum": 1, "maximum": 5}}, ["pickup_id", "delivery_id"]))}, ["tasks"])),
        ("raise_task_priorities", "执行明确提升指令。increment提升一级；set指定等级，不能降级；紧急为5。", object_schema({"changes": array_schema(object_schema({"task_id": ID, "mode": {"type": "string", "enum": ["increment", "set"]}, "priority": {"type": "integer", "minimum": 1, "maximum": 5}}, ["task_id", "mode"]))}, ["changes"])),
        ("cancel_tasks", "取消尚未开始装货的任务。目标须由本轮用户原文明确写出T编号，或在原文无编号时由本轮界面明确关联；不得从查询、历史或唯一候选推断，缺失时先澄清。装货、配送和卸货中的任务不可取消。", object_schema({"task_ids": array_schema(ID)}, ["task_ids"])),
        ("get_metrics", "查询完成数量、距离、任务周转及下单至装货耗时；耗时单位为调度时间步。", object_schema()),
        ("assign_task", "将尚未开始装货的任务指定给无其他任务的机器人，或锁定其当前执行机器人；允许装货前安全改派到空闲/回停车位机器人，不抢占或预约忙碌机器人的其他任务，不绕过硬优先级。指定关系保留，紧急任务可暂时抢占未装货普通任务，但其后仍只交给指定机器人。先查询真实状态。", object_schema({"task_id": ID, "robot_id": ID}, ["task_id", "robot_id"])),
        ("release_task_assignment", "解除任务的人工指定或软偏好，恢复自动分配并重新规划；只允许尚未开始装货的任务，不取消任务。", object_schema({"task_id": ID}, ["task_id"])),
        ("set_task_preference", "设置任务的软偏好：在同等硬优先级分配数量下优先满足可立即接手的机器人偏好，再最小化ETA。忙碌时可用其他机器人，不因普通任务偏好抢占别的任务。可替换原人工指定；仅装货前允许，执行机器人不保证是偏好机器人。", object_schema({"task_id": ID, "robot_id": ID}, ["task_id", "robot_id"])),
        ("copy_task", "明确复制已有任务，创建1至20个独立新任务。默认继承取送地点和等级，可明确指定新等级；不继承原任务状态、机器人归属、指定或偏好。已完成或取消的任务也可作为来源。先查询源任务，用户未指定份数则默认1。", object_schema({"task_id": ID, "count": {"type": "integer", "minimum": 1, "maximum": MAX_BATCH}, "priority": {"type": "integer", "minimum": 1, "maximum": 5}}, ["task_id"])),
    ]
]


def fields(value, allowed, required=()):
    if not isinstance(value, dict) or set(value) - set(allowed) or set(required) - set(value):
        raise ValueError("参数字段缺失或包含不支持的字段")


def number(value, prefix=""):
    if isinstance(value, bool):
        raise ValueError("标识无效")
    if isinstance(value, int):
        result = value
    elif isinstance(value, str) and re.fullmatch(rf"{prefix}0*[1-9]\d*", value, re.I):
        result = int(re.sub(r"^[A-Za-z]+", "", value))
    else:
        raise ValueError("请使用查询返回的作业点、任务或机器人ID")
    if not 1 <= result <= 10**9:
        raise ValueError("标识超出范围")
    return result


def priority(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
        raise ValueError("等级必须为1至5的整数")
    return value


def identifier(value, prefix):
    if not isinstance(value, str):
        raise ValueError("工具中的ID必须为字符串")
    return number(value, prefix)


def sequence(value):
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_BATCH:
        raise ValueError("批量数量必须为1至20项，请拆分过长请求")
    return value


def normalize(name, args):
    if name in ("assign_task", "release_task_assignment", "set_task_preference"):
        required = ["task_id"] if name == "release_task_assignment" else ["task_id", "robot_id"]
        fields(args, required, required)
        mode = {"assign_task": "forced", "release_task_assignment": "auto", "set_task_preference": "preferred"}[name]
        return [{"operation": "assignment", "task_id": identifier(args["task_id"], "T"), "mode": mode,
                 "robot_id": None if mode == "auto" else identifier(args["robot_id"], "R")}]
    if name == "copy_task":
        fields(args, ["task_id", "count", "priority"], ["task_id"])
        source = identifier(args["task_id"], "T")
        count = args.get("count", 1)
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= MAX_BATCH:
            raise ValueError("复制数量必须为1至20的整数")
        level = {"priority": priority(args["priority"])} if "priority" in args else {}
        return [{"operation": "copy", "source_task_id": source, **level} for _ in range(count)]
    if name == "get_status":
        fields(args, ["task_id", "robot_id"])
        return {k: identifier(v, "T" if k == "task_id" else "R") for k, v in args.items()}
    if name == "get_locations":
        fields(args, ["kind"])
        kind = args.get("kind", "all")
        if kind not in ("all", "pickup", "delivery", "shelf"):
            raise ValueError("作业点类型无效")
        return {"kind": kind}
    if name == "get_metrics":
        fields(args, [])
        return {}
    # 模型返回的地点ID先校验格式，再转换成执行器使用的业务动作。
    if name == "create_tasks":
        fields(args, ["tasks"], ["tasks"])
        result = []
        for item in sequence(args["tasks"]):
            fields(item, ["pickup_id", "delivery_id", "priority"], ["pickup_id", "delivery_id"])
            # 普通任务默认2级；实际地点存在性由执行器按当前地图再次检查。
            result.append({"operation": "add", "pickup": identifier(item["pickup_id"], "P"), "delivery": identifier(item["delivery_id"], "D"), "priority": priority(item.get("priority", 2))})
        return result
    if name == "raise_task_priorities":
        fields(args, ["changes"], ["changes"])
        result = []
        for item in sequence(args["changes"]):
            fields(item, ["task_id", "mode", "priority"], ["task_id", "mode"])
            mode = item["mode"]
            if mode not in ("increment", "set") or (mode == "increment" and "priority" in item):
                raise ValueError("提升模式无效")
            result.append({"operation": "priority", "task_id": identifier(item["task_id"], "T"), "mode": mode, **({"priority": priority(item.get("priority"))} if mode == "set" else {})})
        return result
    if name == "cancel_tasks":
        fields(args, ["task_ids"], ["task_ids"])
        return [{"operation": "cancel", "task_id": identifier(value, "T")} for value in sequence(args["task_ids"])]
    raise ValueError("不支持此工具；助手仅提供十类业务工具")


def task_view(task, warehouse):
    pickup = warehouse.locations["pickups"][warehouse.pickups.index(task.pickup)]
    delivery = warehouse.locations["deliveries"][warehouse.deliveries.index(task.delivery)]
    shelves = [s["name"] for s in warehouse.locations["shelves"] if s["pickup_id"] == pickup["id"]]
    return {"task_id": f"T{task.id:03}", "pickup_id": pickup["id"], "pickup_name": pickup["name"],
            "pickup_label": shelves[0] if len(shelves) == 1 else pickup["name"], "shelf_names": shelves,
            "delivery_id": delivery["id"], "delivery_name": delivery["name"], "priority": task.priority,
            "business_phase": task.status, "phase_label": PHASES[task.status],
            "assigned_robot": f"R{task.robot_id}" if task.robot_id else None,
            "assignment_mode": task.assignment_mode,
            "requested_robot": f"R{task.assignment_robot_id}" if task.assignment_robot_id else None,
            "assignment_label": {"auto": "自动分配", "forced": "人工指定", "preferred": "软偏好"}[task.assignment_mode],
            "copied_from": f"T{task.copied_from:03}" if task.copied_from else None}


def query(sim, name, args):
    if name == "get_locations":
        result = {}
        for kind, group in (("pickup", "pickups"), ("delivery", "deliveries"), ("shelf", "shelves")):
            if args["kind"] in ("all", kind):
                result[kind] = deepcopy(sim.warehouse.locations[group])
        if args["kind"] in ("all", "shelf"):
            result["note"] = "货架通过pickup_id取货，编号不必相同；没有登记的货架不能猜测。名称或别名有多个候选时先询问。当前无库存系统，一项任务表示一次搬运，不推断全部库存数量。"
        return result
    if name == "get_metrics":
        m = sim.snapshot().metrics
        return {"completed": m.get("completed", 0), "pending": m.get("pending", 0), "distance": m.get("distance", 0), "path_waits": m.get("waits", 0), "average_turnaround": m.get("avg_completion", 0), "average_order_to_loading": m.get("avg_wait", 0), "duration_unit": "调度时间步（不是秒）"}
    if "task_id" in args and args["task_id"] not in sim.tasks:
        raise ValueError("任务不存在")
    if "robot_id" in args and not any(r.id == args["robot_id"] for r in sim.robots):
        raise ValueError("机器人不存在")
    tasks = [task_view(t, sim.warehouse) for t in sorted(sim.tasks.values(), key=lambda t: t.id) if (t.status != "cancelled" or "task_id" in args) and ("task_id" not in args or t.id == args["task_id"])]
    robots = [{"robot_id": f"R{r.id}", "position": list(r.position), "business_phase": r.phase, "phase_label": PHASES[r.phase], "loaded": r.loaded, "task_id": f"T{r.task_id:03}" if r.task_id else None, "reserved_task": f"T{r.next_task_id:03}" if r.next_task_id else None, "completed": r.completed} for r in sim.robots if "robot_id" not in args or r.id == args["robot_id"]]
    return {"tasks": tasks, "robots": robots, "note": "业务阶段不证明当前实际移动，预约不等于已开始搬运。"}
