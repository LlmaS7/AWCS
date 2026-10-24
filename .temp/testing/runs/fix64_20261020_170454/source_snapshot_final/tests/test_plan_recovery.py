"""Regression checks for bounded recovery and controller acceptance boundaries.

Run with: python -B -m unittest discover -s tests -v
"""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

from coordination.contracts import PlanningProfile, Proposal, RequestKey
from coordination.recovery import RETAIN_STEPS, can_retain_routes
from simulation import Simulation


def scene():
    definition = dict(format='sditadc-map', version=1, name='Recovery regression',
        grid=dict(width=9, height=9, rows=['#########']+['#.......#']*7+['#########']),
        points=dict(starts=[[1,1],[2,1]], parking=[[1,1],[2,1],[7,1],[7,7]],
                    pickups=[[2,4],[4,4]], deliveries=[[6,4],[6,6]]),
        robots=dict(default_count=2, max_count=2), random_obstacles=dict(count=0))
    sim = Simulation(7, initial_tasks=0, map_id='recovery-test', map_definition=definition,
                     robot_count=2, profile=PlanningProfile(seconds=1))
    sim.add_task(sim.warehouse.pickups[0], sim.warehouse.deliveries[0], 2)
    if not sim.ensure_plan():
        raise AssertionError('Recovery fixture could not obtain its initial route')
    return sim


def failed(status='timeout'):
    return Proposal(None, False, status=status, metrics={'last_plan_ms': 50})


class RecoveryTests(unittest.TestCase):
    def test_failure_reuses_only_committed_state(self):
        sim = scene()
        before = deepcopy((sim.robots, sim.tasks, sim.assignment, sim.tick))
        proposal = failed()
        proposal.robots, proposal.tasks, proposal.assignment = [], {}, {'forged': True}
        self.assertTrue(sim.apply_proposal(proposal))
        self.assertEqual((sim.robots, sim.tasks, sim.assignment, sim.tick), before)
        self.assertFalse(sim.paused)
        self.assertEqual(sim.plan_valid_until, sim.tick+RETAIN_STEPS)
        self.assertEqual(sim.metrics['planning_status'], 'retained_safe_plan')

    def test_manual_pause_is_preserved(self):
        sim = scene(); sim.paused = True
        self.assertTrue(sim.apply_proposal(failed()))
        self.assertTrue(sim.paused)

    def test_rechecks_do_not_extend_lease_and_expiry_replans(self):
        sim = scene()
        # Delay every robot equally; tasks then remain unfinished for the whole lease.
        for r in sim.robots:r.path = [r.position]*40+r.path[1:]
        self.assertTrue(sim.apply_proposal(failed()))
        expiry = sim.plan_valid_until
        with patch('coordination.coordinator.solve', side_effect=AssertionError('Unexpected replan')):
            for _ in range(RETAIN_STEPS):
                sim.dirty = True
                self.assertTrue(sim.ensure_plan())
                self.assertEqual(sim.plan_valid_until, expiry)
                self.assertTrue(sim.step())
        self.assertTrue(sim.dirty)
        with patch('coordination.coordinator.solve', return_value=failed()) as solve:
            self.assertTrue(sim.ensure_plan())
            solve.assert_called_once_with(sim)
        self.assertEqual(sim.plan_valid_until, expiry+RETAIN_STEPS)

    def test_new_task_cannot_be_starved_by_recovery(self):
        sim = scene(); self.assertTrue(sim.apply_proposal(failed()))
        sim.add_task(sim.warehouse.pickups[1], sim.warehouse.deliveries[1], 5)
        self.assertFalse(sim.continue_retained_plan())
        self.assertFalse(sim.apply_proposal(failed()))
        self.assertTrue(sim.paused)

    def test_cancelled_search_cannot_grant_recovery(self):
        sim = scene()
        self.assertFalse(sim.apply_proposal(failed('cancelled')))
        self.assertTrue(sim.paused)
        self.assertIsNone(sim.plan_valid_until)

    def test_changed_map_invalidates_retained_route(self):
        sim = scene(); self.assertTrue(sim.apply_proposal(failed()))
        robot = next(r for r in sim.robots if r.task_id is not None)
        blocked = next(p for p in robot.path if p != robot.position)
        sim.warehouse.blocked.add(blocked); sim.dirty = True
        self.assertFalse(sim.continue_retained_plan())
        self.assertFalse(sim.apply_proposal(failed()))

    def test_forced_reassignment_does_not_reuse_old_itinerary(self):
        sim = scene(); self.assertTrue(sim.apply_proposal(failed()))
        task = next(iter(sim.tasks.values())); other = 3-task.robot_id
        sim.set_assignment(task.id, 'forced', other)
        self.assertFalse(sim.continue_retained_plan())
        self.assertFalse(sim.apply_proposal(failed()))
        self.assertEqual(task.robot_id, other)

    def test_cancellation_cannot_reuse_old_job(self):
        sim = scene(); self.assertTrue(sim.apply_proposal(failed()))
        sim.cancel_task(next(iter(sim.tasks)))
        self.assertFalse(sim.continue_retained_plan())
        self.assertFalse(sim.apply_proposal(failed()))

    def test_emergency_upgrade_requests_new_dispatch(self):
        sim = scene(); self.assertTrue(sim.apply_proposal(failed()))
        sim.set_priority(next(iter(sim.tasks)), 5)
        self.assertFalse(sim.continue_retained_plan())
        self.assertFalse(sim.apply_proposal(failed()))

    def test_atomic_service_cannot_be_truncated(self):
        sim = scene()
        for _ in range(40):
            if any(r.phase == 'picking' for r in sim.robots):break
            self.assertTrue(sim.step())
        robot = next(r for r in sim.robots if r.phase == 'picking')
        self.assertTrue(sim.apply_proposal(failed()))
        robot.path = [robot.position, next(p for p in robot.path if p != robot.position)]
        sim.dirty = True
        self.assertFalse(sim.continue_retained_plan())
        self.assertFalse(sim.apply_proposal(failed()))

    def test_loaded_custody_is_preserved(self):
        sim = scene()
        for _ in range(40):
            if any(r.loaded for r in sim.robots):break
            self.assertTrue(sim.step())
        before = deepcopy((sim.robots, sim.tasks))
        self.assertTrue(any(r.loaded for r in sim.robots))
        self.assertTrue(sim.apply_proposal(failed()))
        self.assertEqual((sim.robots, sim.tasks), before)

    def test_orphan_task_is_rejected(self):
        sim = scene(); robot = next(r for r in sim.robots if r.task_id is not None)
        robot.task_id = None; robot.phase = 'parking'
        self.assertFalse(sim.apply_proposal(failed()))

    def test_stationary_routes_cannot_claim_progress(self):
        sim = scene()
        for r in sim.robots:r.path = [r.position]
        self.assertFalse(sim.apply_proposal(failed()))

    def test_collision_and_swap_are_rejected(self):
        for kind in ('collision', 'swap'):
            with self.subTest(kind=kind):
                sim = scene();a,b = sim.robots
                if kind == 'collision':a.path = [a.position, b.position]
                else:a.path,b.path = [a.position,b.position],[b.position,a.position]
                self.assertFalse(sim.apply_proposal(failed()))

    def test_rolling_prefix_never_gets_an_extended_recovery_certificate(self):
        sim = scene()
        sim.profile = PlanningProfile(mode='rolling', seconds=1, window=8, execute=2)
        sim.plan_valid_until = sim.tick+2
        self.assertFalse(sim.apply_proposal(failed()))
        self.assertEqual(sim.plan_valid_until, sim.tick+2)
        self.assertFalse(sim.continue_retained_plan())

    def test_legacy_failure_still_pauses(self):
        sim = scene(); sim.profile = PlanningProfile(mode='legacy_full')
        self.assertFalse(sim.apply_proposal(failed()))


    def test_successful_replan_clears_retention_status_message(self):
        from coordination.coordinator import solve
        sim = scene(); self.assertTrue(sim.apply_proposal(failed()))
        sim.dirty = True
        proposal = solve(sim); self.assertTrue(proposal.success)
        self.assertTrue(sim.apply_proposal(proposal))
        self.assertIsNone(sim.plan_valid_until)
        self.assertEqual(sim.metrics['planning_status'], 'success')
        self.assertEqual(sim.message, '安全路线已更新，可继续执行')

    def test_direct_legacy_success_clears_retained_deadline(self):
        sim = scene(); self.assertTrue(sim.apply_proposal(failed()))
        sim.profile = PlanningProfile(mode='legacy_full'); sim.dirty = True
        self.assertTrue(sim.ensure_plan()); self.assertIsNone(sim.plan_valid_until)
        self.assertEqual(sim.metrics['planning_status'], 'success')
        for _ in range(RETAIN_STEPS+5):
            self.assertTrue(sim.ensure_plan()); self.assertTrue(sim.step())
        self.assertTrue(all(t.status=='completed' for t in sim.tasks.values()))
        self.assertFalse(sim.dirty)

    def test_controller_mode_switch_clears_retained_deadline(self):
        from controller import Controller
        sim = scene(); self.assertTrue(sim.apply_proposal(failed()))
        with patch('controller.Simulation', return_value=sim):c = Controller(paused=True)
        c.start()
        try:
            view = c.submit('planning', {'mode':'legacy_full'}).result(timeout=20)
            self.assertIsNone(view['plan_valid_until'])
            self.assertEqual(view['metrics']['planning_status'], 'success')
            self.assertTrue(view['paused'])
            self.assertEqual(view['message'], '安全路线已更新，可继续执行')
        finally:c.stop(save_on_exit=False)


class ControllerRecoveryTests(unittest.TestCase):
    def controller(self, sim):
        from controller import Controller
        c = Controller.__new__(Controller)
        c.sim = sim; c.generation = 0; c._domain_revision = 0
        c.run_id = 'recovery'; c._request_serial = 0
        c._requested = None; c._planning = False
        c.worker = Mock(); c._publish = Mock(); c._finish_waiters = Mock(); c._resume_jobs = Mock()
        return c

    def test_async_result_uses_owner_side_recovery(self):
        c = self.controller(scene()); key = RequestKey('recovery',0,0,c.sim.tick,1,'map')
        c._requested = key; c._planning = True
        c.worker.poll.return_value = key, failed(), None
        c._poll_plan()
        self.assertFalse(c._planning)
        self.assertEqual(c.sim.metrics['planning_status'], 'retained_safe_plan')
        self.assertFalse(c.sim.dirty)
        c._finish_waiters.assert_called_once()

    def test_retained_event_does_not_submit_another_worker_job(self):
        c = self.controller(scene()); self.assertTrue(c.sim.apply_proposal(failed()))
        c.sim.dirty = True; c._plan()
        c.worker.submit.assert_not_called()
        self.assertFalse(c.sim.dirty)
        c._finish_waiters.assert_called_once()

    def test_new_pending_task_goes_to_worker(self):
        c = self.controller(scene()); self.assertTrue(c.sim.apply_proposal(failed()))
        c.sim.add_task(c.sim.warehouse.pickups[1],c.sim.warehouse.deliveries[1],5)
        c._plan(); c.worker.submit.assert_called_once()
        self.assertTrue(c._planning)

    def test_stale_failure_cannot_grant_a_recovery_lease(self):
        fields = ('run_id','generation','domain_revision','tick','request_id','geometry')
        for field in fields:
            with self.subTest(field=field):
                c = self.controller(scene()); key = RequestKey('recovery',0,0,c.sim.tick,1,'map')
                old = replace(key, **{field: 'old' if field in ('run_id','geometry') else 99})
                c._requested = key; c.worker.poll.return_value = old, failed(), None
                c._poll_plan()
                self.assertIsNone(c.sim.plan_valid_until)
                self.assertEqual(c.sim.metrics['stale_plans'], 1)

    def test_worker_error_still_pauses_with_valid_routes(self):
        c = self.controller(scene()); key = RequestKey('recovery',0,0,c.sim.tick,1,'map')
        c._requested = key; c.worker.poll.return_value = key, None, 'injected crash'
        c._poll_plan()
        self.assertTrue(c.sim.paused)
        self.assertIsNone(c.sim.plan_valid_until)
        self.assertEqual(c.sim.metrics['planning_status'], 'worker_error')

    def test_controller_actor_and_real_worker_complete_workload(self):
        from controller import Controller
        sim = scene(); sim.dirty = True
        with patch('controller.Simulation', return_value=sim):
            c = Controller(paused=True)
        c.start()
        try:
            for _ in range(80):
                state = c.submit('step').result(timeout=20)
                if all(t['status']=='completed' for t in state['tasks']):break
            else:self.fail('Controller actor did not complete the workload')
            self.assertEqual(state['metrics']['collisions'], 0)
        finally:c.stop(save_on_exit=False)


if __name__ == '__main__':unittest.main()
