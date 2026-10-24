"""Versioned, renderer-independent grid maps and checked local map discovery."""
from collections import deque
from copy import deepcopy
import json
from pathlib import Path
import re

from config import MAPS, DEFAULT_MAP, DEFAULT_ROBOT_COUNT, MAX_ROBOTS
from locations import build_locations

FORMAT = "sditadc-map"
MAX_DIMENSION = 256
MAX_BYTES = 2 * 1024 * 1024


def integer(value, label, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{label} 必须为 {low}～{high} 的整数")
    return value


def robot_limits(definition):
    limits = definition.get("robots", {})
    if not isinstance(limits, dict):
        raise ValueError("robots 数量配置必须为对象")
    capacity = len(definition["points"]["starts"])
    maximum = integer(limits.get("max_count", min(capacity, MAX_ROBOTS)),
                      "robots.max_count", 1, MAX_ROBOTS)
    default = integer(limits.get("default_count", min(DEFAULT_ROBOT_COUNT, maximum)),
                      "robots.default_count", 1, maximum)
    if maximum > capacity or maximum > len(definition["points"]["parking"]):
        raise ValueError("机器人上限不能超过起点池或停车位数量")
    return default, maximum


def validate_map(value):
    """Return a detached definition; reject unsafe geometry before a scene changes."""
    if not isinstance(value, dict) or value.get("format") != FORMAT or type(value.get("version")) is not int or value["version"] != 1:
        raise ValueError("地图格式应为 sditadc-map，version 为 1")
    name = value.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 100:
        raise ValueError("地图 name 必须为 1～100 字符的名称")
    grid = value.get("grid")
    if not isinstance(grid, dict):
        raise ValueError("地图缺少 grid")
    width = integer(grid.get("width"), "地图宽度", 3, MAX_DIMENSION)
    height = integer(grid.get("height"), "地图高度", 3, MAX_DIMENSION)
    rows = grid.get("rows")
    if not isinstance(rows, list) or len(rows) != height:
        raise ValueError("grid.rows 行数与 height 不一致")
    for i, row in enumerate(rows):
        if not isinstance(row, str) or len(row) != width or set(row) - set(".#RO~"):
            raise ValueError(f"地图第 {i + 1} 行长度错误或含未知字符（只支持 . # R O ~，~ 为地图外）")
    points = value.get("points")
    if not isinstance(points, dict):
        raise ValueError("地图缺少 points 作业点配置")
    groups = {}
    for group in ("starts", "parking", "pickups", "deliveries"):
        raw = points.get(group)
        if not isinstance(raw, list) or not 1 <= len(raw) <= 256:
            raise ValueError(f"points.{group} 必须包含 1～256 个坐标")
        coords = []
        for p in raw:
            if not isinstance(p, list) or len(p) != 2:
                raise ValueError(f"points.{group} 中的坐标应为 [x, y]")
            x = integer(p[0], f"{group}.x", 0, width - 1)
            y = integer(p[1], f"{group}.y", 0, height - 1)
            if rows[y][x] != ".":
                raise ValueError(f"{group} 坐标 ({x}, {y}) 位于障碍上")
            coords.append((x, y))
        if len(set(coords)) != len(coords):
            raise ValueError(f"points.{group} 有重复坐标")
        groups[group] = set(coords)
    robot_limits(value)
    if not groups["starts"] <= groups["parking"]:
        raise ValueError("机器人起点必须属于停车位")
    if groups["parking"] & (groups["pickups"] | groups["deliveries"]) or groups["pickups"] & groups["deliveries"]:
        raise ValueError("停车、取货和配送点不能相互重叠")
    # Every prefix must stay adjacent, since a fleet uses the first N spawn slots.
    start = tuple(points["starts"][0])
    adjacent_starts = {start}
    for p in points["starts"][1:]:
        x, y = p
        if not adjacent_starts.intersection(((x+1,y), (x-1,y), (x,y+1), (x,y-1))):
            raise ValueError("起点池须按相邻顺序排列，使前 N 个起点四方向连通")
        adjacent_starts.add((x,y))
    reached = {start}
    queue = deque([start])
    while queue:
        x, y = queue.popleft()
        for q in ((x+1,y), (x-1,y), (x,y+1), (x,y-1)):
            if 0 <= q[0] < width and 0 <= q[1] < height and rows[q[1]][q[0]] == "." and q not in reached:
                reached.add(q); queue.append(q)
    open_count = sum(row.count(".") for row in rows)
    if len(reached) != open_count:
        raise ValueError("地图的可通行区域必须四方向连通")
    clutter = value.get("random_obstacles", {"count": 0})
    if not isinstance(clutter, dict):
        raise ValueError("random_obstacles 配置无效")
    integer(clutter.get("count", 0), "随机障碍数量", 0, 200)
    region = clutter.get("region", [0, 0, width, height])
    if not isinstance(region, list) or len(region) != 4:
        raise ValueError("随机障碍 region 应为 [左, 上, 右, 下]，右下不含")
    for v, label, limit in zip(region, ("左", "上", "右", "下"), (width, height, width, height)):
        integer(v, f"region.{label}", 0, limit)
    if region[0] >= region[2] or region[1] >= region[3]:
        raise ValueError("随机障碍 region 范围为空")
    build_locations(value)
    return deepcopy(value)


def read_map(path):
    path = Path(path)
    try:
        if path.stat().st_size > MAX_BYTES:
            raise ValueError("地图文件超过 2 MB")
        return validate_map(json.loads(path.read_text(encoding="utf-8-sig")))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取地图 {path.name}：{exc}") from exc


def load_map(map_id=DEFAULT_MAP):
    if not isinstance(map_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", map_id):
        raise ValueError("地图标识只能含英文字母、数字、下划线和短横线")
    path = (MAPS / f"{map_id}.json").resolve()
    if not path.is_relative_to(MAPS.resolve()):
        raise ValueError("地图必须位于本版本 maps 目录内")
    return read_map(path)


def catalog():
    entries = []
    for path in sorted(MAPS.glob("*.json")):
        try:
            definition = load_map(path.stem)
            grid = definition["grid"]
            default, maximum = robot_limits(definition)
            entries.append({"id": path.stem, "name": definition["name"],
                            "default_robots": default, "max_robots": maximum,
                            "width": grid["width"], "height": grid["height"], "available": True})
        except ValueError as exc:
            entries.append({"id": path.stem, "name": path.stem, "available": False, "error": str(exc)})
    return entries
