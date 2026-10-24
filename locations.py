"""Map-owned business identities; linguistic interpretation belongs to the LLM."""
from copy import deepcopy
import re


def text(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 80 or any(ord(c) < 32 for c in value):
        raise ValueError(f"{label} 必须为1至80字符的名称")
    return value.strip()


def aliases(value, label):
    if not isinstance(value, list) or len(value) > 12:
        raise ValueError(f"{label} 最多12个别名")
    cleaned = [text(v, label) for v in value]
    if len(set(cleaned)) != len(cleaned):
        raise ValueError(f"{label} 别名重复")
    return cleaned


def build_locations(definition):
    """Old maps keep numbered points but never acquire guessed shelf identities.

    Shared aliases are allowed: the assistant must clarify multiple candidates.
    """
    raw = definition.get("locations", {})
    if not isinstance(raw, dict) or set(raw) - {"pickups", "deliveries", "shelves"}:
        raise ValueError("locations 仅支持pickups、deliveries、shelves")
    result = {"pickups": [], "deliveries": [], "shelves": []}
    for kind, prefix in (("pickups", "P"), ("deliveries", "D")):
        defaults = [{"id": f"P{i:02}" if prefix == "P" else f"D{i}",
                     "name": f"取货点{i:02}" if prefix == "P" else f"{i}号配送点",
                     "aliases": [], "position": list(p)} for i, p in enumerate(definition["points"][kind], 1)]
        by_id = {item["id"]: item for item in defaults}
        entries = raw.get(kind, [])
        if not isinstance(entries, list) or len(entries) > len(defaults):
            raise ValueError(f"locations.{kind} 数量无效")
        seen = set()
        for item in entries:
            if not isinstance(item, dict) or set(item) - {"id", "name", "aliases"} or not {"id", "name"} <= set(item):
                raise ValueError(f"locations.{kind} 字段无效")
            identity = item["id"]
            if not isinstance(identity, str) or identity not in by_id or identity in seen:
                raise ValueError(f"locations.{kind} ID不存在或重复")
            seen.add(identity)
            by_id[identity].update(name=text(item["name"], kind), aliases=aliases(item.get("aliases", []), kind))
        result[kind] = defaults
    shelves = raw.get("shelves", [])
    if not isinstance(shelves, list) or len(shelves) > 256:
        raise ValueError("locations.shelves 最多256项")
    identities, occupied = set(), set()
    pickup_ids = {p["id"]: p for p in result["pickups"]}
    grid = definition["grid"]
    for item in shelves:
        if not isinstance(item, dict) or set(item) - {"id", "name", "aliases", "pickup_id", "cells"} or not {"id", "name", "pickup_id", "cells"} <= set(item):
            raise ValueError("货架业务配置字段无效")
        identity = item["id"]
        if not isinstance(identity, str) or not re.fullmatch(r"S[A-Za-z0-9_-]{1,32}", identity) or identity in identities:
            raise ValueError("货架ID应以S开头且不可重复")
        identities.add(identity)
        if not isinstance(item["pickup_id"], str) or item["pickup_id"] not in pickup_ids:
            raise ValueError("货架对应的取货点不存在")
        cells = item["cells"]
        if not isinstance(cells, list) or not 1 <= len(cells) <= grid["width"] * grid["height"]:
            raise ValueError("货架cells不能为空或超出地图")
        checked = set()
        for p in cells:
            if not isinstance(p, list) or len(p) != 2 or any(type(v) is not int for v in p):
                raise ValueError("货架cells应为整数坐标")
            x, y = p
            if not (0 <= x < grid["width"] and 0 <= y < grid["height"]) or grid["rows"][y][x] != "R":
                raise ValueError("货架cells必须位于实际货架格")
            if (x, y) in checked or (x, y) in occupied:
                raise ValueError("货架cells重复或与其他货架登记重叠")
            checked.add((x, y))
        reached = {next(iter(checked))}
        todo = list(reached)
        while todo:
            x, y = todo.pop()
            for q in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
                if q in checked and q not in reached:
                    reached.add(q);todo.append(q)
        if reached != checked:
            raise ValueError("同一货架cells必须四方向连通")
        x, y = pickup_ids[item["pickup_id"]]["position"]
        if not checked.intersection(((x-1, y), (x+1, y), (x, y-1), (x, y+1))):
            raise ValueError("货架取货点须邻接登记货架")
        occupied |= checked
        result["shelves"].append({"id": identity, "name": text(item["name"], "货架名称"),
            "aliases": aliases(item.get("aliases", []), "货架"), "pickup_id": item["pickup_id"],
            "pickup_position": list(pickup_ids[item["pickup_id"]]["position"])})
    return deepcopy(result)
