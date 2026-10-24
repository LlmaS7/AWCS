"""Certify existing complete routes without changing committed business state."""
from models import FINISHED
from planning.validation import validate_itineraries

RETAIN_STEPS = 32


def can_retain_routes(sim):
    # Partial rolling routes never gain a new certificate through this fallback.
    if sim.profile.mode != 'scalable_full':
        return False
    unfinished = {t.id for t in sim.tasks.values() if t.status not in FINISHED}
    if not unfinished or any(t.status == 'pending' for t in sim.tasks.values()):
        return False
    try:
        sim.assert_invariants()
        owned = []
        for robot in sim.robots:
            if robot.task_id is not None:
                owned.append(robot.task_id)
            if robot.next_task_id is not None:
                task = sim.tasks[robot.next_task_id]
                if task.status != 'reserved' or task.robot_id != robot.id:
                    return False
                owned.append(task.id)
        if set(owned) != unfinished or len(owned) != len(unfinished):
            return False
        validate_itineraries(sim.warehouse,
                             {r.id: r.position for r in sim.robots},
                             {r.id: r.path for r in sim.robots},
                             {r.id: sim.itinerary(r) for r in sim.robots})
        # An all-wait suffix cannot recover an unfinished workload.
        return any(r.service_left > 0 or any(p != r.position for p in r.path[1:])
                   for r in sim.robots)
    except (ValueError, AssertionError, KeyError, IndexError, TypeError):
        return False
