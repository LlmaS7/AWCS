"""Validate universal maps or convert MovingAI grids with explicit MAPD points."""
import argparse
import json
from pathlib import Path

from map_format import read_map, validate_map, robot_limits, MAX_BYTES, MAX_DIMENSION


def import_movingai(source, points, name, blocked_kind="walls"):
    source = Path(source)
    if source.stat().st_size > MAX_BYTES:
        raise ValueError("MovingAI 地图文件超过 2 MB")
    lines = source.read_text(encoding="utf-8-sig").splitlines()
    if len(lines) < 4 or lines[0].strip() != "type octile" or lines[3].strip() != "map":
        raise ValueError("MovingAI 文件头应为 type octile / height / width / map")
    try:
        h_label, h = lines[1].split()
        w_label, w = lines[2].split()
        width, height = int(w), int(h)
    except (ValueError, IndexError) as exc:
        raise ValueError("MovingAI 宽高文件头无效") from exc
    if h_label != "height" or w_label != "width" or not 3 <= width <= MAX_DIMENSION or not 3 <= height <= MAX_DIMENSION:
        raise ValueError("MovingAI 宽高必须在 3～256 之间")
    rows = lines[4:]
    if len(rows) != height or any(len(row) != width for row in rows):
        raise ValueError("MovingAI 网格与文件头尺寸不一致")
    unknown = set("".join(rows)) - set(".G@OT")
    if unknown:
        raise ValueError(f"不支持的 MovingAI 地形：{', '.join(sorted(unknown))}；请先明确其通行语义")
    grid = []
    for y, row in enumerate(rows):
        converted = []
        for x, c in enumerate(row):
            if c in ".G":
                converted.append(".")
            else:
                perimeter = x in (0, width-1) or y in (0, height-1)
                converted.append("R" if blocked_kind == "shelves" and not perimeter else "#")
        grid.append("".join(converted))
    return validate_map({"format": "sditadc-map", "version": 1, "name": name,
                         "grid": {"width": width, "height": height, "rows": grid},
                         "points": points, "random_obstacles": {"count": 0},
                         "source": {"file": source.name, "movement": "four-direction in SDITADC"}})


def main():
    parser = argparse.ArgumentParser(description="SDITADC unified map tools")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("validate")
    check.add_argument("map", type=Path)
    convert = commands.add_parser("import-movingai")
    convert.add_argument("source", type=Path)
    convert.add_argument("--points", type=Path, required=True, help="JSON with starts/parking/pickups/deliveries")
    convert.add_argument("--name", required=True)
    convert.add_argument("--blocked-kind", choices=("walls", "shelves"), default="walls")
    convert.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "validate":
            value = read_map(args.map)
        else:
            if args.output.exists():
                raise ValueError("输出文件已存在，请使用新名称，避免覆盖地图")
            points = json.loads(args.points.read_text(encoding="utf-8-sig"))
            value = import_movingai(args.source, points, args.name, args.blocked_kind)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (ValueError, OSError) as exc:
        parser.exit(1, f"地图检查未通过：{exc}\n")
    grid = value["grid"]
    default, maximum = robot_limits(value)
    print(f"有效地图：{value['name']} · {grid['width']}×{grid['height']} · 默认 {default} 台，上限 {maximum} 台")


if __name__ == "__main__":
    main()
