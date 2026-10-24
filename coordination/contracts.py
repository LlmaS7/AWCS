"""Versioned, credential-free process contracts."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PlanningProfile:
    mode: str = 'scalable_full'
    coupling: str = 'off'
    seconds: float = 3.0
    candidates: int = 4
    window: int = 32
    execute: int = 4

    def __post_init__(self):
        if isinstance(self.seconds,bool) or not isinstance(self.seconds,(int,float)):
            raise ValueError('规划秒数必须为数值')
        if any(type(v) is not int for v in (self.candidates,self.window,self.execute)):
            raise ValueError('候选数与窗口必须为整数')
        if self.mode not in ('legacy_full','scalable_full','rolling'):
            raise ValueError('未知规划模式')
        if self.coupling not in ('off','estimated','candidate'):
            raise ValueError('未知任务路径联动模式')
        if not .05 <= self.seconds <= 10 or not 1 <= self.candidates <= 8:
            raise ValueError('规划预算或候选数超出范围')
        if not 4 <= self.window <= 512 or not 1 <= self.execute <= self.window:
            raise ValueError('规划窗口必须不小于执行前缀')


@dataclass(frozen=True)
class RequestKey:
    run_id: str
    generation: int
    domain_revision: int
    tick: int
    request_id: int
    geometry: str


@dataclass
class Proposal:
    key: RequestKey | None
    success: bool
    robots: list = field(default_factory=list)
    tasks: dict = field(default_factory=dict)
    assignment: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    status: str = 'timeout'
    diagnostics: dict = field(default_factory=dict)
    safe_steps: int | None = None


def snapshot_for_planning(sim):
    """Picklable isolated snapshot. No controller, frames, events, settings or secrets."""
    from copy import copy, deepcopy
    clone = copy(sim)
    clone.robots = deepcopy(sim.robots)
    clone.tasks = deepcopy(sim.tasks)
    clone.metrics = deepcopy(sim.metrics)
    clone.assignment = deepcopy(sim.assignment)
    clone.events, clone.frames, clone.replay_events = [], [], []
    clone.replaying = False
    return clone
