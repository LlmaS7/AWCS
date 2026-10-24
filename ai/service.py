"""One user request at a time; network work never runs on the simulation actor."""
from collections import deque
from concurrent.futures import TimeoutError
from copy import deepcopy
import json
from threading import Event, RLock, Thread
from uuid import uuid4
from time import monotonic

from .authorization import cancellation_targets, check_cancellation
from .configuration import Configuration
from .conversation import Conversation
from .provider import CancelToken, DeepSeek, ProviderError, Stopped
from .tools import TOOLS, WRITES, normalize, number


class AIService:
    def __init__(self, controller, configuration=None, provider=None):
        self.controller = controller
        self.configuration = configuration or Configuration()
        self.provider = provider or DeepSeek()
        self.lock = RLock()
        self.events = deque(maxlen=4096)
        self.serial = 0
        self.session = uuid4().hex
        self.generation = controller.generation
        self.conversation = Conversation()
        self.models = []
        self.verified = False
        self.active = None
        self.closed = Event()
        from task_imports.service import ImportService
        self.imports = ImportService(self)
        self.monitor = Thread(target=self._monitor, name="ai-scene-monitor", daemon=True)
        self.monitor.start()

    def emit(self, kind, **data):
        with self.lock:
            self.serial += 1
            self.events.append({"id": self.serial, "kind": kind, **data})

    def _monitor(self):
        while not self.closed.wait(.1):
            self.sync_scene()

    def sync_scene(self):
        generation = self.controller.state()["generation"]
        with self.lock:
            if generation == self.generation:
                return
            self.generation = generation
            self.imports.invalidate()
            self._new_context("工作场景已更新，旧消息仅供查看", generation=generation)

    def _new_context(self, reason, keep_local=False, **extra):
        if self.active and not (keep_local and self.active['kind'] == 'import_commit'):
            token = self.active["token"]
            token.event.set()
            Thread(target=token.cancel, name="ai-cancel-stream", daemon=True).start()
        self.session = uuid4().hex
        self.conversation = Conversation()
        self.emit("context", message=reason, session=self.session, **extra)

    def public(self):
        self.sync_scene()
        with self.lock:
            return {**self.configuration.public(), "models": deepcopy(self.models), "verified": self.verified,
                    "busy": self.active is not None, "request_id": self.active["id"] if self.active else None,
                    "session": self.session, "generation": self.generation}

    def save_settings(self, data):
        with self.lock:
            old_token = self.active["token"] if self.active and self.active['kind'] != 'import_commit' else None
            context_changed, changed = self.configuration.save(data)
            if changed:
                self.verified = False
                if old_token:
                    old_token.event.set()
            if context_changed:
                self.models = []
                self._new_context("接入设置已更新，开始新的对话上下文", keep_local=True)
        if changed and old_token:
            old_token.cancel()
        return self.public()

    def event_page(self, after):
        self.sync_scene()
        with self.lock:
            first = self.events[0]["id"] if self.events else self.serial + 1
            return {"events": [deepcopy(e) for e in self.events if e["id"] > after], "cursor": self.serial,
                    "gap": after < first - 1, "busy": self.active is not None,
                    "request_id": self.active["id"] if self.active else None,
                    "session": self.session, "generation": self.generation}

    def launch(self, kind, data=None):
        self.sync_scene()
        data = data or {}
        with self.lock:
            if self.closed.is_set() or self.active:
                raise ValueError("请等待当前请求完成或停止回复")
            if kind not in ('message', 'models', 'test', 'import_extract'):
                raise ValueError('未知请求类型')
            cfg = self.configuration.snapshot()
            if not cfg["api_key"]:
                raise ValueError("请先在设置中填写API Key")
            if kind != "models" and not cfg["model"]:
                raise ValueError("请先选择或填写模型ID")
            model = next((m for m in self.models if m["id"] == cfg["model"]), {})
            if model.get("efforts") and cfg["effort"] != "off" and cfg["effort"] not in model["efforts"]:
                raise ValueError("当前模型不支持此思考程度，请在设置中调整")
            for key in ("context_window", "max_output_tokens"):
                value = model.get(key)
                if isinstance(value, int) and not isinstance(value, bool) and value >= 1024:
                    cfg[key] = value
            if kind == "message":
                text = data.get("text")
                if not isinstance(text, str) or not text.strip() or len(text) > 6000:
                    raise ValueError("请输入1至6000字的消息，过长请求请拆分")
                if data.get("generation") != self.generation:
                    raise ValueError("工作场景已更新，请刷新关联任务后重发")
                if data.get("task_id") is not None:
                    number(data["task_id"], "T")
            elif kind == 'import_extract':
                self.imports.begin_analysis(data)
            request = {"id": uuid4().hex, "kind": kind, "session": self.session, "generation": self.generation,
                       "token": CancelToken(cfg["timeout"]), "cfg": cfg, "conversation": self.conversation,
                       "cancel_targets": cancellation_targets(data["text"], data.get("task_id")) if kind == "message" else frozenset()}
            self.active = request
            self.emit("start", request_id=request["id"], job=kind, generation=self.generation,
                      text=data.get("text", ""), task_id=data.get("task_id"),
                      **({'filename': self.imports.store.current['filename']} if kind == 'import_extract' else {}))
            Thread(target=self._work, args=(request, data), name="deepseek-worker", daemon=True).start()
            return {"request_id": request["id"]}

    def stop(self, request_id=None):
        with self.lock:
            request = self.active
            if request and (request_id is None or request_id == request["id"]):
                request["token"].event.set()
                self.emit("notice", request_id=request["id"], message="正在停止；已经生效的操作不会撤销")
            else:
                return
        request["token"].cancel()

    def clear(self):
        self.stop()
        with self.lock:
            self.session = uuid4().hex
            self.conversation = Conversation()
            self.imports.clear()
            # Preserve event IDs so old queued results never masquerade as new messages.
            self.emit("clear", session=self.session)

    def close(self):
        self.closed.set()
        self.stop()
        self.monitor.join(timeout=1)
        with self.configuration.lock:
            self.configuration.key = ""

    def fresh(self, request):
        request["token"].check()
        if request["generation"] != self.controller.generation or request["session"] != self.session or request["cfg"]["epoch"] != self.configuration.epoch:
            raise Stopped("工作场景或接入设置已更新，未继续执行旧请求")

    def tool(self, request, name, args, operation_id):
        self.fresh(request)
        actions = normalize(name, args)
        if name == "cancel_tasks":
            rejection = check_cancellation(actions, request.get("cancel_targets", frozenset()))
            if rejection:
                self.emit("result", request_id=request["id"], generation=request["generation"], tool=name, result=rejection)
                return rejection
        envelope = {"name": name, "arguments": args, "generation": request["generation"], "operation_id": operation_id,
                    "valid": lambda: not request["token"].event.is_set() and not self.closed.is_set()
                    and monotonic() < request["token"].deadline and self.active is request
                    and request["session"] == self.session and request["cfg"]["epoch"] == self.configuration.epoch}
        # 模型请求在后台处理，业务写入交给控制器串行执行，避免并发修改仿真状态。
        future = self.controller.submit("_ai_business", envelope)
        def publish(f):
            if name in WRITES:
                try:
                    self.emit("result", request_id=request["id"], generation=request["generation"], tool=name, result=f.result())
                except Exception:
                    self.emit("notice", request_id=request["id"], message="业务结果待核实；没有自动重发操作")
        future.add_done_callback(publish)
        while True:
            try:
                return future.result(timeout=.1)
            except TimeoutError:
                self.fresh(request)

    def _work(self, request, data):
        token, cfg = request["token"], request["cfg"]
        try:
            if request["kind"] == "models":
                values = self.provider.models(cfg, token)
                self.fresh(request)
                with self.lock:
                    self.models = values
                self.emit("models", request_id=request["id"], models=values)
            elif request["kind"] == "test":
                messages = [{"role": "system", "content": "只读协议测试。请调用get_locations查询作业点，不执行任何业务修改。"}, {"role": "user", "content": "请使用工具查询作业点。"}]
                tools = [TOOLS[1]]
                reply, _ = self.provider.chat(cfg, messages, tools, token)
                calls = reply.get("tool_calls", [])
                if not calls or any(c["function"]["name"] != "get_locations" for c in calls):
                    raise ProviderError("模型未返回预期只读工具调用，尚未通过工具协议测试")
                messages.append(reply)
                for i, call in enumerate(calls):
                    args = json.loads(call["function"]["arguments"])
                    output = self.tool(request, "get_locations", args, request["id"]+f"/test/{i}")
                    messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(output, ensure_ascii=False)})
                self.provider.chat(cfg, messages, tools, token)
                self.fresh(request)
                with self.lock:
                    self.verified = True
                self.emit("notice", request_id=request["id"], message="连接与只读工具往返测试通过")
            elif request['kind'] == 'import_extract':
                self.imports.extract(request, data)
            elif request['kind'] == 'import_commit':
                self.imports.execute(request, data)
            else:
                self._chat(request, data)
        except Stopped as exc:
            self.emit("notice", request_id=request["id"], message=str(exc))
        except (ProviderError, ValueError) as exc:
            token.event.set()
            message = str(exc).replace(cfg['api_key'], '[已隐藏]') if cfg.get('api_key') else str(exc)
            self.emit("error", request_id=request["id"], message=message)
        except Exception:
            token.event.set()
            self.emit("error", request_id=request["id"], message="请求处理未完成；已生效结果保留，没有重复提交业务操作")
        finally:
            with self.lock:
                if request['kind'] == 'import_extract':
                    self.imports.analysis_failed(request, '分析未完成或已停止，请显式重试；未创建任何任务')
                if self.active is request:
                    self.active = None
            self.emit("done", request_id=request["id"])

    def _chat(self, request, data):
        cfg, token, conversation = request["cfg"], request["token"], request["conversation"]
        notice = lambda message: self.emit("notice", request_id=request["id"], message=message)
        conversation.prepare(self.provider, cfg, token, notice)
        self.fresh(request)
        association = "未关联任务" if data.get("task_id") is None else f"当前明确关联任务：T{number(data['task_id'], 'T'):03}"
        turn = [{"role": "user", "content": data["text"].strip()+"\n\n[本轮关联对象："+association+"]"}]
        messages = conversation.messages() + turn
        count, writes = 0, {}
        try:
            # 有界工具调用循环：模型读取回执后可继续决策，最多8轮模型请求。
            for _ in range(8):
                self.fresh(request)
                reply, _ = self.provider.chat(cfg, messages, TOOLS, token,
                    lambda text: self.emit("text", request_id=request["id"], text=text) if not token.event.is_set() and request["session"] == self.session else None)
                self.fresh(request)
                messages.append(reply)
                turn.append(reply)
                # 未请求工具时结束本轮；操作是否生效以真实工具回执为准。
                calls = reply.get("tool_calls", [])
                if not calls:
                    return
                for call in calls:
                    count += 1
                    # 同一用户请求累计最多处理12次工具调用，防止模型循环失控。
                    if count > 12:
                        raise ProviderError("本轮工具次数达到上限，已停止后续操作；请查看已生效结果")
                    name = call["function"]["name"]
                    self.emit("progress", request_id=request["id"], tool=name)
                    try:
                        args = json.loads(call["function"]["arguments"])
                        # 先验证工具名与参数，再用规范化参数识别同轮重复写操作。
                        normalized = normalize(name, args)
                        signature = json.dumps([name, normalized], sort_keys=True)
                        # 同轮相同写操作复用回执；明确多份任务应由一次批量请求表达。
                        if name in WRITES and signature in writes:
                            output = writes[signature]
                        else:
                            output = self.tool(request, name, args, request["id"]+f"/{count}")
                            if name in WRITES and not output.get("error"):
                                writes[signature] = output
                    except (ValueError, KeyError, TypeError) as exc:
                        output = {"error": str(exc), "executed": False}
                    # 以tool消息回填真实结果，模型据此继续查询、调用工具或向用户解释。
                    message = {"role": "tool", "tool_call_id": call["id"], "content": json.dumps(output, ensure_ascii=False)}
                    messages.append(message)
                    turn.append(message)
            raise ProviderError("本轮模型次数达到上限，已停止后续操作；请查看已生效结果")
        finally:
            # Interrupted turns may contain unmatched calls: keep only a complete prefix.
            while turn and turn[-1].get("role") != "user":
                assistant = next((i for i in range(len(turn)-1, -1, -1) if turn[i]["role"] == "assistant"), None)
                if assistant is None:
                    break
                calls = turn[assistant].get("tool_calls", [])
                answered = {m.get("tool_call_id") for m in turn[assistant+1:] if m["role"] == "tool"}
                if all(c["id"] in answered for c in calls):
                    break
                turn = turn[:assistant]
            conversation.turns.append(turn)
