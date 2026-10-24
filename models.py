"""Domain data only; no dependency on Pygame."""
from dataclasses import dataclass, field

Position = tuple[int, int]
FINISHED = {"completed", "cancelled"}
TASK_LABELS = {
    "pending": "待分配", "reserved": "等待接手", "to_pickup": "前往取货",
    "picking": "装货中", "to_delivery": "送货中", "unloading": "卸货中",
    "completed": "已完成", "cancelled": "已取消",
}
ROBOT_LABELS = {"idle": "空闲", "parking": "前往停车位", **TASK_LABELS}


@dataclass
class Task:
    id: int
    pickup: Position
    delivery: Position
    priority: int
    created_at: int
    status: str = "pending"
    robot_id: int | None = None
    picked_at: int | None = None
    completed_at: int | None = None
    preemptions: int = 0
    assignment_mode: str = "auto"
    assignment_robot_id: int | None = None
    copied_from: int | None = None
    source: dict | None = None


@dataclass
class Robot:
    id: int
    position: Position
    previous: Position
    parking: Position
    phase: str = "idle"
    task_id: int | None = None
    next_task_id: int | None = None
    service_left: int = 0
    loaded: bool = False
    path: list[Position] = field(default_factory=list)
    distance: int = 0
    waits: int = 0
    completed: int = 0


@dataclass(frozen=True)
class Waypoint:
    position: Position
    hold: int = 0
    delivery: bool = False
    urgent: bool = False


@dataclass
class View:
    warehouse: object
    robots: list[Robot]
    tasks: dict[int, Task]
    tick: int
    paused: bool
    auto: bool
    message: str
    metrics: dict
    assignment: dict
    replaying: bool

