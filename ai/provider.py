"""Small DeepSeek adapter: bounded HTTPS, complete SSE messages, no secret logs."""
import json
from threading import Event, Lock
from time import monotonic
import httpx


class Stopped(Exception):
    pass


class ProviderError(Exception):
    pass


class CancelToken:
    def __init__(self, timeout=300):
        self.event = Event()
        self.deadline = monotonic() + timeout
        self.lock = Lock()
        self.closers = []

    def check(self):
        if self.event.is_set():
            raise Stopped("已停止后续回复；已生效操作保留")
        if monotonic() >= self.deadline:
            raise ProviderError("等待已达到上限；请查看已生效的业务结果")

    def attach(self, closer):
        with self.lock:
            self.closers.append(closer)
        if self.event.is_set():
            closer()

    def cancel(self):
        self.event.set()
        with self.lock:
            closers = list(self.closers)
        for closer in closers:
            try:
                closer()
            except Exception:
                pass


class DeepSeek:
    @staticmethod
    def headers(config):
        if not config.get("api_key"):
            raise ProviderError("请先在设置中填写API Key")
        return {"Authorization": "Bearer " + config["api_key"], "Content-Type": "application/json"}

    @staticmethod
    def check_status(response):
        if response.status_code >= 300:
            messages = {401: "API密钥无效", 403: "此密钥或模型没有访问权限", 402: "账户余额不足", 404: "接口或模型不存在，请检查地址和模型ID", 429: "上游限流，请稍后重试"}
            raise ProviderError(messages.get(response.status_code, f"上游请求失败（HTTP {response.status_code}），请检查接入设置"))

    def models(self, config, token):
        token.check()
        try:
            with httpx.Client(timeout=httpx.Timeout(20, connect=10), follow_redirects=False) as client:
                token.attach(client.close)
                response = client.get(config["base_url"] + "/models", headers=self.headers(config))
                self.check_status(response)
                value = response.json()
                if not isinstance(value, dict) or not isinstance(value.get("data"), list):
                    raise ProviderError("上游模型列表格式不兼容，可手动填写模型ID")
                result = []
                for item in value["data"][:500]:
                    if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                        continue
                    levels = item.get("effort", {}).get("supported_levels", []) if isinstance(item.get("effort"), dict) else []
                    result.append({"id": item["id"][:160], "name": str(item.get("name") or item["id"])[:200], "context_window": item.get("context_window"), "max_output_tokens": item.get("max_output_tokens"), "efforts": [x for x in levels if x in ("low", "high", "max")]})
                token.check()
                return result
        except (httpx.HTTPError, ValueError):
            token.check()
            raise ProviderError("模型列表请求失败或格式不兼容；可手动填写模型ID") from None

    def chat(self, config, messages, tools, token, on_text=None):
        token.check()
        if not config.get("model"):
            raise ProviderError("请先选择或填写模型ID")
        payload = {"model": config["model"], "messages": messages, "stream": True,
                   "max_tokens": min(8192, config.get("max_output_tokens") or 8192),
                   "thinking": {"type": "disabled" if config["effort"] == "off" else "enabled"}}
        if config["effort"] != "off":
            payload["reasoning_effort"] = config["effort"]
        if tools:
            payload.update(tools=tools, tool_choice="auto")
        content, reasoning, calls = [], [], {}
        finish, done, usage = None, False, None
        total_size = 0
        try:
            with httpx.Client(timeout=httpx.Timeout(90, connect=10), follow_redirects=False) as client:
                token.attach(client.close)
                with client.stream("POST", config["base_url"] + "/chat/completions", headers=self.headers(config), json=payload) as response:
                    token.attach(response.close)
                    self.check_status(response)
                    for line in response.iter_lines():
                        token.check()
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            done = True
                            break
                        total_size += len(data)
                        if total_size > 2_000_000:
                            raise ProviderError("模型输出超过本地处理上限，已停止后续操作")
                        chunk = json.loads(data)
                        usage = chunk.get("usage") or usage
                        for choice in chunk.get("choices", []):
                            delta = choice.get("delta", {})
                            if delta.get("content"):
                                content.append(delta["content"])
                                if on_text:
                                    on_text(delta["content"])
                            if delta.get("reasoning_content"):
                                reasoning.append(delta["reasoning_content"])
                            for part in delta.get("tool_calls") or []:
                                index = part.get("index", 0)
                                call = calls.setdefault(index, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                                if part.get("id"):
                                    call["id"] = part["id"]
                                fun = part.get("function", {})
                                call["function"]["name"] += fun.get("name") or ""
                                call["function"]["arguments"] += fun.get("arguments") or ""
                            finish = choice.get("finish_reason") or finish
                    token.check()
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            token.check()
            raise ProviderError("上游流式连接中断或响应格式不兼容；已生效操作保留") from None
        if not done or finish not in ("stop", "tool_calls"):
            raise ProviderError("模型响应未完整结束，未执行这次返回的工具调用")
        message = {"role": "assistant", "content": "".join(content), "reasoning_content": "".join(reasoning)}
        if calls:
            values = [calls[k] for k in sorted(calls)]
            if len(values) > 12 or any(not c["id"] or not c["function"]["name"] for c in values):
                raise ProviderError("工具调用标识不完整或过多，未执行")
            message["tool_calls"] = values
        return message, usage
