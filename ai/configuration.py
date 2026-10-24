"""Local nonsecret settings and per-endpoint credential binding."""
from copy import deepcopy
import json
from pathlib import Path
from threading import RLock
from urllib.parse import urlsplit
from config import ROOT
from .credentials import CredentialStore

DEFAULTS = {"base_url": "https://api.deepseek.com", "model": "", "effort": "high", "timeout": 300, "remember": False}


def address(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError("API地址无效")
    value = value.strip().rstrip("/")
    parsed = urlsplit(value)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or not parsed.hostname:
        raise ValueError("地址不能包含账号、密码、查询参数或片段")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost", "::1")):
        raise ValueError("外部API请使用HTTPS；HTTP仅用于本机测试")
    return value


class Configuration:
    def __init__(self, path=None, store=None):
        self.path = Path(path) if path else ROOT / "local_settings.json"
        self.store = store or CredentialStore()
        self.lock = RLock()
        self.values = deepcopy(DEFAULTS)
        self.key = ""
        self.epoch = 0
        self.warning = ""
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.values.update(self.clean(data))
                if self.values["remember"]:
                    self.key = self.store.read(self.values["base_url"])
        except Exception:
            self.warning = "本地设置或凭据未能加载，请在设置中重新配置"

    @staticmethod
    def clean(data):
        if not isinstance(data, dict) or set(data) - set(DEFAULTS):
            raise ValueError("设置字段无效")
        result = {**DEFAULTS, **data}
        result["base_url"] = address(result["base_url"])
        if not isinstance(result["model"], str) or len(result["model"]) > 160 or any(ord(c) < 32 for c in result["model"]):
            raise ValueError("模型ID无效")
        result["model"] = result["model"].strip()
        if result["effort"] not in ("off", "low", "high", "max"):
            raise ValueError("思考程度无效")
        if isinstance(result["timeout"], bool) or not isinstance(result["timeout"], int) or not 30 <= result["timeout"] <= 900:
            raise ValueError("总等待上限为30至900秒")
        if not isinstance(result["remember"], bool):
            raise ValueError("记住密钥选项无效")
        return result

    def public(self):
        with self.lock:
            return {**self.values, "has_key": bool(self.key), "warning": self.warning}

    def snapshot(self):
        with self.lock:
            return {**self.values, "api_key": self.key, "epoch": self.epoch}

    def save(self, data):
        if not isinstance(data, dict) or set(data) - (set(DEFAULTS) | {"api_key", "delete_key"}):
            raise ValueError("设置字段无效")
        with self.lock:
            previous = self.values
            values = self.clean({**previous, **{k: v for k, v in data.items() if k in DEFAULTS}})
            endpoint_changed = values["base_url"] != previous["base_url"]
            key = "" if endpoint_changed else self.key
            if "api_key" in data:
                if not isinstance(data["api_key"], str) or len(data["api_key"]) > 2048 or any(ord(c) < 32 for c in data["api_key"]):
                    raise ValueError("密钥格式无效")
                if data["api_key"].strip():
                    key = data["api_key"].strip()
            if data.get("delete_key") is True:
                self.store.delete(values["base_url"])
                key = ""
                values["remember"] = False
            self.warning = ""
            if previous["remember"] and (endpoint_changed or not values["remember"]):
                self.store.delete(previous["base_url"])
            if values["remember"] and key:
                try:
                    self.store.write(values["base_url"], key)
                except RuntimeError:
                    values["remember"] = False
                    self.warning = "凭据保存失败，密钥仅本次有效；不会写入明文文件"
            if endpoint_changed and not key:
                self.warning = "地址已更改，请明确填写要提交到新地址的密钥"
            context_changed = endpoint_changed or values["model"] != previous["model"]
            changed = values != previous or key != self.key
            self.values, self.key = values, key
            if changed:
                self.epoch += 1
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.path)
            return context_changed, changed
