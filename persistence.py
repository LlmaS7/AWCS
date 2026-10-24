"""Portable input-event replay and reports, always under this version directory."""
import json
from dataclasses import asdict
from coordination.contracts import PlanningProfile
from datetime import datetime
from config import OUTPUTS, ROOT, VERSION, DEFAULT_MAP, DEFAULT_ROBOT_COUNT
from simulation import Simulation


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def save(sim):
    scenario = {"version": VERSION, "seed": sim.warehouse.seed,
                "robot_count": len(sim.robots),
                "map_id": sim.warehouse.map_id, "map_definition": sim.warehouse.export_map(),
                "events": sim.events + sim.replay_events,
                "planning_profile": asdict(sim.profile),
                "replay_kind": "input-events",
                "map_hash": sim.warehouse.topology.map_hash}
    write_json(OUTPUTS / "last_scenario.json", scenario)
    view = sim.snapshot()
    report = {"saved_at": datetime.now().astimezone().isoformat(), "tick": sim.tick,
              "seed": sim.warehouse.seed, "metrics": view.metrics,
              "map_id": sim.warehouse.map_id, "map_name": sim.warehouse.name,
              "robot_count": len(sim.robots),
              "assignment": sim.assignment, "tasks": [asdict(t) for t in sim.tasks.values()],
              "robots": [asdict(r) for r in sim.robots], "frames": sim.frames,
              "recording": {"kind":"bounded-position-trace","max_frames":10000,
                            "dropped_frames":sim.metrics.get('frames_dropped',0),
                            "first_tick":sim.frames[0]['tick'] if sim.frames else None},
              "replay_error": sim.replay_error,
              "events": sim.events}
    write_json(OUTPUTS / "last_run.json", report)
    return OUTPUTS / "last_scenario.json"


def load(path=None):
    path = path or (OUTPUTS / "last_scenario.json")
    if not path.exists():
        path = ROOT / "scenarios" / "ordinary.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") not in ("0.1_preview", "0.2_preview", "0.2.1_preview", "0.3_preview", VERSION):
        raise ValueError("场景版本不匹配")
    sim = Simulation(int(data["seed"]), initial_tasks=0,
                     map_id=data.get("map_id", DEFAULT_MAP), map_definition=data.get("map_definition"),
                     robot_count=data.get("robot_count", DEFAULT_ROBOT_COUNT),
                     profile=PlanningProfile(**data['planning_profile']) if data.get('planning_profile') else
                     PlanningProfile(mode='legacy_full',coupling='off'))
    events = data.get("events", [])
    if any(not isinstance(e.get("tick"), int) or e["tick"] < 0 for e in events):
        raise ValueError("场景事件时间无效")
    if any(e.get("operation") not in ("add", "priority", "cancel", "auto", "assignment", "copy") for e in events):
        raise ValueError("场景包含不支持的操作")
    sim.replay_events = sorted(events, key=lambda e: e["tick"])
    sim.replaying = True
    if sim.apply_replay_events():
        sim.message = "已加载场景输入回放 · 新的手动操作将转为交互运行"
    return sim
