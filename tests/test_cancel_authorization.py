"""D07 regression through AIService, the real controller actor and executor.

Only provider replies are scripted; no network, credentials or saved scenes used.
Run with: python -B -m unittest discover -s tests -v
"""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch

from ai.authorization import cancellation_targets
from ai.configuration import Configuration
from ai.service import AIService
from controller import Controller
from simulation import Simulation


def tool_reply(name, args):
    return {"role": "assistant", "content": "", "tool_calls": [{
        "id": "scripted-call", "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }]}


class ScriptedProvider:
    def __init__(self):
        self.replies = []
        self.inputs = []

    def chat(self, cfg, messages, tools, token, on_text=None):
        token.check()
        self.inputs.append(deepcopy(messages))
        if self.replies:
            return self.replies.pop(0), {}
        return {"role": "assistant", "content": "请核对业务回执。"}, {}


class TargetExtractionTests(unittest.TestCase):
    def test_only_explicit_ids_or_current_association(self):
        for text, association, expected in [
            ("刚才那个，取消掉。", None, set()),
            ("取消这个任务", "T001", {1}),
            ("取消T002", "T001", {2}),
            ("取消t0002和T003。", None, {2, 3}),
            ("取消 T1000000000", "T001", {1000000000}),
            ("取消 T1000000001", "T001", set()),
            ("取消 T000", "T001", set()),
            ("取消 XT001 或 T001abc", None, set()),
        ]:
            with self.subTest(text=text):
                self.assertEqual(cancellation_targets(text, association), expected)


class CancellationAuthorizationTests(unittest.TestCase):
    def setUp(self):
        definition = dict(format="sditadc-map", version=1, name="D07 regression",
            grid=dict(width=9, height=9, rows=["#########"] + ["#.......#"] * 7 + ["#########"]),
            points=dict(starts=[[1, 1], [2, 1]], parking=[[1, 1], [2, 1], [7, 1], [7, 7]],
                        pickups=[[2, 4], [4, 4]], deliveries=[[6, 4], [6, 6]]),
            robots=dict(default_count=2, max_count=2), random_obstacles=dict(count=0))
        sim = Simulation(7, initial_tasks=0, map_id="d07-test", map_definition=definition,
                         robot_count=2)
        sim.add_task(sim.warehouse.pickups[0], sim.warehouse.deliveries[0], 2)
        self.assertTrue(sim.ensure_plan())
        with patch("controller.Simulation", return_value=sim):
            self.controller = Controller(paused=True)
        self.addCleanup(self.controller.stop, save_on_exit=False)
        self.controller.start()
        temporary = TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(temporary.cleanup)
        configuration = Configuration(path=Path(temporary.name) / "settings.json")
        configuration.save(dict(api_key="synthetic-local-only", model="scripted", remember=False))
        self.provider = ScriptedProvider()
        self.ai = AIService(self.controller, configuration, self.provider)
        self.addCleanup(self.ai.close)

    def message(self, text, replies=(), association=None):
        self.provider.replies = list(replies)
        finished = Event()
        original = self.ai.emit

        def emit(kind, **data):
            original(kind, **data)
            if kind == "done":
                finished.set()

        cursor = self.ai.serial
        with patch.object(self.ai, "emit", side_effect=emit):
            self.ai.launch("message", dict(text=text, task_id=association,
                                           generation=self.controller.generation))
            self.assertTrue(finished.wait(15), "AI request did not finish")
        events = self.ai.event_page(cursor)["events"]
        self.assertFalse([e for e in events if e["kind"] == "error"], events)
        self.assertFalse(self.provider.replies, "Scripted provider replies were not consumed")
        return events

    def snapshot(self):
        # All requests finish before this read, and the fixture remains paused.
        return deepcopy((self.controller.sim.tasks, self.controller.sim.robots,
                         self.controller.sim.assignment, self.controller.sim.next_id))

    def assert_blocked(self, events):
        results = [e["result"] for e in events if e["kind"] == "result"]
        self.assertTrue(results, events)
        for result in results:
            self.assertEqual(result.get("code"), "cancellation_target_required")
            self.assertIs(result["executed"], False)
            self.assertIs(result["requires_clarification"], True)

    def test_d07_clear_query_unique_task_then_cancel_is_blocked_before_submit(self):
        self.message("查询这个任务状态。", [tool_reply("get_status", {"task_id": "T001"})], "T001")
        old_session = self.ai.session
        self.ai.clear()
        self.assertNotEqual(old_session, self.ai.session)
        before = self.snapshot()
        with patch.object(self.controller, "submit", wraps=self.controller.submit) as submit:
            events = self.message("刚才那个，取消掉。", [
                tool_reply("get_status", {}),
                tool_reply("cancel_tasks", {"task_ids": ["T001"]}),
                tool_reply("cancel_tasks", {"task_ids": ["T001"]}),
            ])
        self.assert_blocked(events)
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(submit.call_args_list)
        self.assertTrue(all(call.args[1]["name"] == "get_status" for call in submit.call_args_list))
        current_user = next(m["content"] for m in self.provider.inputs[-1] if m["role"] == "user")
        self.assertIn("未关联任务", current_user)

    def test_clarification_with_explicit_id_then_real_cancellation(self):
        events = self.message("刚才那个，取消掉。", [tool_reply("cancel_tasks", {"task_ids": ["T001"]})])
        self.assert_blocked(events)
        events = self.message("取消 T001。", [tool_reply("cancel_tasks", {"task_ids": ["T001"]})])
        self.assertEqual(self.controller.sim.tasks[1].status, "cancelled")
        applied = [e for e in events if e["kind"] == "result"][0]["result"]["actions"][0]
        self.assertEqual(applied["outcome"], "applied")
        self.assertTrue(all(r.task_id != 1 for r in self.controller.sim.robots))

    def test_current_ui_association_allows_pronoun(self):
        self.message("取消这个任务。", [tool_reply("cancel_tasks", {"task_ids": ["T001"]})], "T001")
        self.assertEqual(self.controller.sim.tasks[1].status, "cancelled")

    def test_explicit_target_overrides_different_ui_selection(self):
        before = self.snapshot()
        events = self.message("取消 T002。", [tool_reply("cancel_tasks", {"task_ids": ["T001"]})], "T001")
        self.assert_blocked(events)
        self.assertEqual(self.snapshot(), before)

    def test_batch_rejected_atomically_when_model_adds_target(self):
        before = self.snapshot()
        events = self.message("取消 T001。", [tool_reply("cancel_tasks", {"task_ids": ["T001", "T002"]})])
        self.assert_blocked(events)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(len(self.controller.business.ledger), 0)

    def test_previous_user_id_does_not_carry_to_next_turn(self):
        self.message("查询 T001。", [tool_reply("get_status", {"task_id": "T001"})])
        before = self.snapshot()
        events = self.message("取消刚才那个。", [tool_reply("cancel_tasks", {"task_ids": ["T001"]})])
        self.assert_blocked(events)
        self.assertEqual(self.snapshot(), before)

    def test_history_summary_and_assistant_suggestion_cannot_grant_target(self):
        self.ai.conversation.summary = "之前关联 T001，用户想取消它。"
        self.message("先看看。", [{"role": "assistant", "content": "是否取消 T001？"}])
        before = self.snapshot()
        events = self.message("确认。", [tool_reply("cancel_tasks", {"task_ids": ["T001"]})])
        self.assert_blocked(events)
        self.assertEqual(self.snapshot(), before)

    def test_read_queries_and_other_write_tools_still_work(self):
        events = self.message("查询任务，然后把 T001 提高一级。", [
            tool_reply("get_status", {"task_id": "T001"}),
            tool_reply("raise_task_priorities", {"changes": [{"task_id": "T001", "mode": "increment"}]}),
        ])
        self.assertEqual(self.controller.sim.tasks[1].priority, 3)
        self.assertEqual([e for e in events if e["kind"] == "result"][0]["result"]["actions"][0]["outcome"], "applied")

    def test_explicit_batch_and_duplicate_write_keep_existing_semantics(self):
        self.message("从一号取货点往二号配送点创建任务。", [
            tool_reply("create_tasks", {"tasks": [{"pickup_id": "P1", "delivery_id": "D2"}]}),
        ])
        events = self.message("取消 T001 和 T002。", [
            tool_reply("cancel_tasks", {"task_ids": ["T001", "T002"]}),
            tool_reply("cancel_tasks", {"task_ids": ["T001", "T002"]}),
        ])
        self.assertTrue(all(t.status == "cancelled" for t in self.controller.sim.tasks.values()))
        self.assertEqual(len([e for e in events if e["kind"] == "result"]), 1)

    def test_explicit_target_still_cannot_cancel_loaded_task(self):
        for _ in range(40):
            state = self.controller.submit("step").result(timeout=15)
            if any(robot["loaded"] for robot in state["robots"]):
                break
        else:
            self.fail("Fixture did not reach the loaded phase")
        before = self.snapshot()
        events = self.message("取消 T001。", [tool_reply("cancel_tasks", {"task_ids": ["T001"]})])
        result = [e for e in events if e["kind"] == "result"][0]["result"]
        self.assertIn("不能取消", result["error"])
        self.assertTrue(all(a["outcome"] == "not_executed" for a in result["actions"]))
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
