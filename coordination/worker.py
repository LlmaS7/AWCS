"""One cancellable, persistent planner PROCESS. Never receives AI credentials."""
from multiprocessing import get_context
from time import monotonic
from collections import OrderedDict


def _main(connection, cancel):
    from coordination.coordinator import solve
    caches = OrderedDict()
    try:
        while True:
            item = connection.recv()
            if item is None:
                return
            key,snapshot = item
            geometry = key.geometry
            if geometry in caches:
                snapshot.warehouse._distances = caches[geometry]
            try:
                if snapshot.profile.mode=='legacy_full':
                    from coordination.contracts import Proposal
                    success = snapshot._legacy_ensure_plan()
                    proposal = Proposal(key,success,snapshot.robots,snapshot.tasks,
                                        snapshot.assignment,snapshot.metrics,
                                        'success' if success else 'timeout')
                else:
                    proposal = solve(snapshot,key,cancel)
                caches[geometry] = snapshot.warehouse._distances
                caches.move_to_end(geometry)
                while len(caches)>2:
                    caches.popitem(last=False)
                connection.send((key,proposal,None))
            except Exception as exc:
                # Exception details are local algorithm diagnostics, no secrets
                # were included in this process in the first place.
                connection.send((key,None,f'{type(exc).__name__}: {exc}'))
    except (EOFError,BrokenPipeError):
        pass
    finally:
        connection.close()


class PlannerWorker:
    def __init__(self):
        self.context = get_context('spawn')
        self.process = None
        self.connection = None
        self.cancel = self.context.Event()
        self.current = None
        self.pending = None
        self.started = 0

    def start(self):
        if self.process is not None and self.process.is_alive():
            return
        if self.process is not None:
            self.process.join(timeout=0)
            self.process.close()
        if self.connection is not None:
            self.connection.close()
        parent,child = self.context.Pipe()
        self.connection = parent
        self.process = self.context.Process(target=_main,args=(child,self.cancel),daemon=True,
                                            name='awcs-planner')
        self.process.start()
        child.close()
        self.current = None

    def submit(self, key, snapshot):
        self.start()
        self.pending = key,snapshot
        if self.current is not None:
            self.cancel.set()
        else:
            self._send()

    def _send(self):
        if self.pending is None:
            return
        key,snapshot = self.pending
        self.pending = None
        self.cancel.clear()
        self.connection.send((key,snapshot))
        self.current = key
        self.started = monotonic()

    def invalidate(self):
        self.pending = None
        self.cancel.set()

    def poll(self):
        if self.current is None:
            return None
        if not self.process.is_alive():
            key = self.current
            self.current = None
            return key,None,'planner process exited'
        if self.connection.poll():
            try:
                result = self.connection.recv()
            except EOFError:
                result = self.current,None,'planner pipe closed'
            self.current = None
            self._send()
            return result
        # Hard process-level bound covers a stuck solver/extension too.
        if monotonic()-self.started>12:
            key = self.current
            pending = self.pending
            self.close()
            self.pending = pending
            if pending:
                self.start()
                self._send()
            return key,None,'planner hard deadline exceeded'
        return None

    def close(self):
        self.cancel.set()
        if self.process is not None:
            if self.process.is_alive():
                try:
                    self.connection.send(None)
                except (BrokenPipeError,EOFError,OSError):
                    pass
                self.process.join(timeout=.5)
                if self.process.is_alive():
                    self.process.terminate()
                    self.process.join(timeout=1)
            self.process.close()
        if self.connection is not None:
            self.connection.close()
        self.process,self.connection,self.current,self.pending = None,None,None,None
