"""One state-owning actor with a cancellable, isolated planning process."""
from concurrent.futures import Future
from dataclasses import asdict
from queue import Empty, Queue
from threading import Event, Lock, Thread
from time import monotonic
from copy import deepcopy
from collections import OrderedDict
import json, traceback
from uuid import uuid4
from ai.executor import BusinessExecutor, business_fingerprint
from ai.tools import WRITES, task_view
from config import DEFAULT_SEED, DEFAULT_MAP, OUTPUTS, VERSION, WAIT_WARNING, MAX_ROBOTS
from models import TASK_LABELS, ROBOT_LABELS
from persistence import load, save
from simulation import Simulation
from coordination.contracts import PlanningProfile, RequestKey, snapshot_for_planning
from coordination.worker import PlannerWorker


class Controller:
    def __init__(self, seed=DEFAULT_SEED, paused=False, auto=False, scenario=None,
                 map_id=DEFAULT_MAP, robot_count=None, profile=None):
        self.sim = load(scenario) if scenario else Simulation(seed, map_id=map_id, robot_count=robot_count, profile=profile)
        self.seed = self.sim.warehouse.seed
        self.sim.paused = paused
        if auto:
            self.sim.command('auto', enabled=True)
        self.speed, self.generation, self.revision = 2, 0, 0
        self.run_id = uuid4().hex
        self.business = BusinessExecutor(self)
        self.last_step = monotonic()
        self._planning = False
        self._lock, self._wake, self._closed = Lock(), Event(), Event()
        self._commands = Queue(maxsize=64)
        self._view = {}
        self._domain_revision, self._request_serial = 0, 0
        self._requested = None
        self._waiters, self._steps, self._jobs = [], [], {}
        self._web_jobs = OrderedDict()
        self.worker = PlannerWorker()
        self._map = self._serialize_map()
        self._publish()
        self._thread = Thread(target=self._run, name='simulation-owner', daemon=True)

    def _serialize_map(self):
        w = self.sim.warehouse
        return dict(id=w.map_id, name=w.name, seed=w.seed, width=w.width, height=w.height,
                    walls=sorted(w.walls), voids=sorted(w.voids), starts=w.starts, random_count=w.random_count,
                    start_pool=w.start_pool, max_robots=w.max_robots, default_robots=w.default_robots,
                    shelves=sorted(w.shelves), obstacles=sorted(w.obstacles), blocked=sorted(w.blocked),
                    pickups=w.pickups, deliveries=w.deliveries, parking=w.parking,
                    topology=w.topology.public(), hash=w.topology.map_hash)

    def _publish(self):
        view = self.sim.snapshot()
        tasks = []
        for t in sorted(view.tasks.values(), key=lambda t: t.id):
            if t.status == 'cancelled':
                continue
            value = asdict(t)
            value.update(label=TASK_LABELS[t.status], pickup_number=view.warehouse.pickups.index(t.pickup)+1,
                         delivery_number=view.warehouse.deliveries.index(t.delivery)+1)
            tasks.append(value)
        robots = []
        for r in view.robots:
            value = asdict(r)
            current = view.tasks.get(r.task_id)
            value.update(label=ROBOT_LABELS[r.phase], urgent=current is not None and current.priority == 5)
            robots.append(value)
        self.revision += 1
        data = dict(version=VERSION, generation=self.generation, revision=self.revision,
                    domain_revision=self._domain_revision, tick=view.tick, speed=self.speed,
                    paused=view.paused, planning=self._planning, auto=view.auto, message=view.message,
                    replaying=view.replaying, map=self._map, robots=robots, robot_count=len(robots),
                    tasks=tasks, metrics={**view.metrics, 'visible_total': len(tasks)},
                    assignment=view.assignment, wait_warning=WAIT_WARNING,
                    planning_profile=asdict(self.sim.profile), plan_valid_until=self.sim.plan_valid_until)
        with self._lock:
            self._view = data

    def state(self):
        with self._lock:
            return {**self._view, 'seconds_since_step': monotonic()-self.last_step}

    def start(self):
        self.worker.start()
        self._thread.start()

    def submit(self, operation, data=None):
        if self._closed.is_set():
            raise RuntimeError('仿真已关闭')
        future = Future()
        self._commands.put_nowait((operation, data or {}, future))
        self._wake.set()
        return future

    def submit_web(self, operation, data, command_id):
        return self.submit('_web_command',dict(operation=operation,data=data,id=command_id))

    def _web_status(self, command_id):
        entry = self._web_jobs.get(command_id)
        if entry is None:
            return dict(status='unknown',error='操作记录已过期，请先核实当前状态；不要自动重发')
        future = entry['future']
        if not future.done():
            return dict(status='running',operation_id=command_id)
        try:
            return dict(status='finished',operation_id=command_id,ok=True,state=future.result())
        except Exception as exc:
            return dict(status='finished',operation_id=command_id,ok=False,error=str(exc))

    def stop(self, save_on_exit=True):
        if self._thread.is_alive():
            self.submit('_close', {'save': save_on_exit}).result(timeout=12)
            self._thread.join(timeout=2)
        self.worker.close()

    def _touch(self):
        self._domain_revision += 1
        self._requested = None
        self.worker.invalidate()

    def _plan(self):
        if not self.sim.dirty:
            return
        if self._requested and self._requested.domain_revision == self._domain_revision:
            return
        self._request_serial += 1
        key = RequestKey(self.run_id, self.generation, self._domain_revision, self.sim.tick,
                         self._request_serial, self.sim.warehouse.topology.map_hash)
        self._requested, self._planning = key, True
        self.worker.submit(key, snapshot_for_planning(self.sim))
        self._publish()

    def _poll_plan(self):
        result = self.worker.poll()
        if result is None:
            return
        key, proposal, error = result
        if key != self._requested or key.generation != self.generation or key.tick != self.sim.tick:
            self.sim.metrics['stale_plans'] = self.sim.metrics.get('stale_plans', 0)+1
            return
        self._planning, self._requested = False, None
        if error:
            self.sim.paused = True
            self.sim.message = '已安全暂停：规划进程未返回可用方案 · '+error
            self.sim.metrics['planning_status'] = 'worker_error'
        else:
            try:
                self.sim.apply_proposal(proposal)
            except Exception as exc:
                self._error(exc)
        self._publish()
        self._finish_waiters()
        self._resume_jobs()

    def _finish_waiters(self):
        waiters, self._waiters = self._waiters, []
        for generation, revision, future in waiters:
            if not future.done():
                future.set_result(self.state())

    @staticmethod
    def integer(data, key, low, high):
        value = data.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f'{key} 参数无效')
        return value

    def _execute(self, op, data):
        if op == 'pause':
            if not isinstance(data.get('paused'), bool):
                raise ValueError('暂停参数无效')
            self.sim.command(op, paused=data['paused'])
        elif op == 'speed':
            speed = self.integer(data, 'value', 1, 8)
            if speed not in (1, 2, 4, 8):
                raise ValueError('支持 1、2、4、8 倍速度')
            self.speed = speed
        elif op in ('priority', 'cancel'):
            task = self.integer(data, 'task_id', 1, 10**9)
            if task not in self.sim.tasks:
                raise ValueError('任务不存在')
            self.sim.command(op, task_id=task, **({'priority': self.integer(data, 'priority', 1, 5)} if op == 'priority' else {}))
            self._touch()
        elif op == 'add':
            p = self.integer(data, 'pickup', 1, len(self.sim.warehouse.pickups))
            d = self.integer(data, 'delivery', 1, len(self.sim.warehouse.deliveries))
            self.sim.command(op, pickup=self.sim.warehouse.pickups[p-1], delivery=self.sim.warehouse.deliveries[d-1],
                             priority=self.integer(data, 'priority', 1, 5))
            self._touch()
        elif op == 'auto':
            if not isinstance(data.get('enabled'), bool):
                raise ValueError('自动任务开关无效')
            self.sim.command(op, enabled=data['enabled'])
        elif op in ('random', 'retry'):
            self.sim.command(op)
            self._touch()
        elif op == 'planning':
            allowed = {'mode', 'coupling', 'seconds', 'candidates', 'window', 'execute'}
            if set(data)-allowed:
                raise ValueError('未知规划配置')
            self.sim.profile = PlanningProfile(**{**asdict(self.sim.profile), **data})
            self.sim.dirty = True
            self._touch()
        elif op == 'save':
            save(self.sim)
            self.sim.message = '已保存本版场景与输入回放记录'
        elif op in ('reset', 'load'):
            if op == 'reset':
                seed = self.integer(data, 'seed', 0, 2**31-1) if 'seed' in data else self.seed
                count = self.integer(data, 'robot_count', 1, MAX_ROBOTS) if 'robot_count' in data else len(self.sim.robots)
                replacement = Simulation(seed, map_id=data.get('map_id', self.sim.warehouse.map_id),
                                         robot_count=count, profile=self.sim.profile)
                self.sim, self.seed = replacement, seed
                self.sim.message = f'已应用{self.sim.warehouse.name} · {count}台机器人，点击继续开始'
            else:
                self.sim = load()
                self.seed = self.sim.warehouse.seed
            self.sim.paused = True
            self.generation += 1
            self._touch()
            self._map = self._serialize_map()
            self.last_step = monotonic()
            self._finish_waiters()
            self._resume_jobs(force=True)
        elif op == '_close':
            if data.get('save'):
                save(self.sim)
            self._closed.set()
            self.worker.invalidate()
        else:
            raise ValueError('不支持的操作')
        self.sim.assert_invariants()
        self._publish()

    def _business(self, envelope, future):
        if envelope['name'] not in WRITES:
            future.set_result(self.business.run(envelope))
            return
        key = envelope['operation_id']
        fingerprint = business_fingerprint(envelope)
        if key in self._jobs:
            job = self._jobs[key]
            if job['fingerprint'] != fingerprint:
                raise ValueError('同一操作标识不能使用不同参数')
            job['futures'].append(future)
            return
        if len(self._jobs)>=64:
            raise ValueError('业务操作队列已满，请等待已接收操作完成')
        job = dict(iterator=self.business.iterate(envelope), futures=[future],
                   fingerprint=fingerprint, generation=self.generation, waiting=False)
        self._jobs[key] = job
        self._advance_job(key, job)

    def _advance_job(self, key, job):
        job['waiting'] = False
        try:
            next(job['iterator'])
            self._touch()
            job['waiting'] = True
            self._plan()
        except StopIteration as done:
            for future in job['futures']:
                if not future.done():
                    future.set_result(deepcopy(done.value))
            self._jobs.pop(key, None)
        except Exception as exc:
            if job['waiting']:
                # Inject scheduling failures at the generator's planning yield:
                # the committed item remains applied, and later items stop.
                try:
                    job['iterator'].throw(exc)
                except StopIteration as done:
                    for future in job['futures']:
                        if not future.done():
                            future.set_result(deepcopy(done.value))
                    self._jobs.pop(key,None)
                    return
                except Exception as propagated:
                    exc = propagated
            for future in job['futures']:
                if not future.done():
                    future.set_exception(exc)
            self._jobs.pop(key, None)

    def _resume_jobs(self, force=False):
        for key, job in list(self._jobs.items()):
            if job['waiting'] and (force or not self._planning):
                self._advance_job(key, job)

    def _import_reconcile(self, data):
        """Internal read only: reconcile a terminated submission from trusted sources."""
        key = data['operation_id']
        old = self.business.ledger.get(key)
        if old and old['result'].get('status') == 'finished':
            return deepcopy(old['result'])
        if key in self._jobs or data['generation'] != self.generation:
            return {'status': 'unknown', 'actions': []}
        from task_imports.schema import validate_source
        actions = []
        for item in data['items']:
            source = validate_source(item['source'])
            matches = [t for t in self.sim.tasks.values() if t.source == source]
            if len(matches) > 1:
                return {'status': 'unknown', 'actions': []}
            if matches:
                actions.append({'operation': 'add', 'outcome': 'applied',
                                **task_view(matches[0], self.sim.warehouse),
                                'planning': 'unavailable' if self.sim.dirty else 'available',
                                'reason': '原提交已结束，已按当前场景核实真实任务'})
            else:
                actions.append({'operation': 'add', 'outcome': 'not_executed',
                                'reason': '原提交已结束，经当前场景核实未创建'})
        return {'status': 'finished', 'actions': actions}

    def _step_ready(self):
        if not self._steps or self._planning:
            return
        generation, future = self._steps.pop(0)
        if generation != self.generation:
            future.set_exception(ValueError('工作场景已更新，未执行旧单步'))
            return
        if self.sim.dirty:
            future.set_result(self.state())
            return
        self.sim.paused = False
        try:
            if self.sim.step():
                self.last_step = monotonic()
        finally:
            self.sim.paused = True
        if self.sim.dirty:
            self._touch()
            self._plan()
        self._publish()
        future.set_result(self.state())

    def _run(self):
        try:
            self._plan()
            next_step = monotonic()+1/self.speed
            while not self._closed.is_set():
                self._wake.wait(timeout=max(0, min(.02, next_step-monotonic())))
                self._wake.clear()
                self._poll_plan()
                while not self._closed.is_set():
                    try:
                        op, data, future = self._commands.get_nowait()
                    except Empty:
                        break
                    try:
                        if op=='_operation_status':
                            future.set_result(self._web_status(data['id']))
                            continue
                        if op=='_web_command':
                            command_id = data['id']
                            fingerprint = json.dumps([data['operation'],data['data']],sort_keys=True,ensure_ascii=False)
                            if command_id in self._web_jobs:
                                old = self._web_jobs[command_id]
                                if old['fingerprint']!=fingerprint:
                                    raise ValueError('同一操作标识不能使用不同参数')
                                def relay(source,destination=future):
                                    if destination.done():return
                                    try:destination.set_result(source.result())
                                    except Exception as exc:destination.set_exception(exc)
                                old['future'].add_done_callback(relay)
                                continue
                            self._web_jobs[command_id] = dict(fingerprint=fingerprint,future=future)
                            while len(self._web_jobs)>128:
                                expired = next((k for k,v in self._web_jobs.items() if v['future'].done()),None)
                                if expired is None:break
                                del self._web_jobs[expired]
                            op,data = data['operation'],data['data']
                        if op == '_ai_business':
                            self._business(data, future)
                        elif op == '_import_reconcile':
                            future.set_result(self._import_reconcile(data))
                        elif op == 'step':
                            self.sim.paused = True
                            self._steps.append((self.generation, future))
                            self._plan()
                        else:
                            self._execute(op, data)
                            if self.sim.dirty and op not in ('pause', 'speed', 'save', 'auto', '_close'):
                                self._waiters.append((self.generation, self._domain_revision, future))
                                self._plan()
                            else:
                                future.set_result(self.state())
                    except (ValueError, KeyError) as exc:
                        if not future.done():
                            future.set_exception(ValueError(str(exc)))
                    except Exception as exc:
                        self._error(exc)
                        if not future.done():
                            future.set_exception(exc)
                self._step_ready()
                if self._closed.is_set():
                    break
                if monotonic() >= next_step:
                    if not self.sim.paused and not self._planning:
                        if self.sim.dirty:
                            self._plan()
                        else:
                            if self.sim.step():
                                self.last_step = monotonic()
                            self._publish()
                            if self.sim.dirty:
                                self._touch()
                                self._plan()
                    next_step = monotonic()+1/self.speed
        except Exception as exc:
            self._error(exc)
        finally:
            for _, _, future in self._waiters:
                if not future.done():
                    future.set_exception(RuntimeError('仿真已关闭'))
            for _, future in self._steps:
                if not future.done():
                    future.set_exception(RuntimeError('仿真已关闭'))
            for job in self._jobs.values():
                for future in job['futures']:
                    if not future.done():
                        future.set_exception(RuntimeError('仿真已关闭'))
            self._closed.set()

    def _error(self, exc):
        self.sim.paused = True
        self._planning = False
        self.sim.message = f'已安全暂停：{exc}'
        OUTPUTS.mkdir(parents=True, exist_ok=True)
        (OUTPUTS/'error.log').write_text(traceback.format_exc(), encoding='utf8')
        self._publish()

