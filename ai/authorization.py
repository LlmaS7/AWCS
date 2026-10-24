"""Cancellation target provenance, independent of model replies and tool results."""
import re

from .tools import number


TASK_REFERENCE = re.compile(r"(?<![A-Za-z0-9_])T[0-9]+(?![A-Za-z0-9_])", re.I)


def cancellation_targets(text, associated_task=None):
    """Freeze targets from this user turn only; explicit IDs override UI selection.

    This checks target provenance, not arbitrary natural-language intent. History,
    summaries and IDs discovered by a model must never enlarge this scope.
    """
    references = TASK_REFERENCE.findall(text)
    if references:
        targets = set()
        for reference in references:
            try:
                targets.add(number(reference, "T"))
            except ValueError:
                pass
        return frozenset(targets)
    if associated_task is not None:
        return frozenset({number(associated_task, "T")})
    return frozenset()


def check_cancellation(actions, targets):
    # Check the entire batch before submitting anything to the simulation actor.
    if any(action["task_id"] not in targets for action in actions):
        return {
            "error": "未明确要取消的任务，整批未执行。请回复“取消 T001”（替换为目标任务编号），或关联目标任务后重发。",
            "code": "cancellation_target_required",
            "executed": False,
            "requires_clarification": True,
        }
    return None
