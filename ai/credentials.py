"""Windows generic credentials, with no plaintext fallback."""
import ctypes
from ctypes import wintypes
import hashlib
import os


class CredentialStore:
    @staticmethod
    def target(address):
        return "SDITADC/v0.3/" + hashlib.sha256(address.encode()).hexdigest()[:32]

    def _api(self):
        if os.name != "nt":
            raise RuntimeError("此平台不支持Windows凭据存储，可仅在本次运行使用密钥")
        class CREDENTIAL(ctypes.Structure):
            _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                        ("Comment", wintypes.LPWSTR), ("LastWritten", wintypes.FILETIME),
                        ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                        ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
                        ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]
        api = ctypes.WinDLL("Advapi32", use_last_error=True)
        api.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIAL), wintypes.DWORD]
        api.CredWriteW.restype = wintypes.BOOL
        api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(CREDENTIAL))]
        api.CredReadW.restype = wintypes.BOOL
        api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        api.CredDeleteW.restype = wintypes.BOOL
        api.CredFree.argtypes = [ctypes.c_void_p]
        return api, CREDENTIAL

    def read(self, address):
        api, record_type = self._api()
        ptr = ctypes.POINTER(record_type)()
        if not api.CredReadW(self.target(address), 1, 0, ctypes.byref(ptr)):
            if ctypes.get_last_error() == 1168:
                return ""
            raise RuntimeError("无法读取Windows凭据")
        try:
            return ctypes.string_at(ptr.contents.CredentialBlob, ptr.contents.CredentialBlobSize).decode("utf-8")
        finally:
            api.CredFree(ptr)

    def write(self, address, key):
        api, record_type = self._api()
        data = key.encode("utf-8")
        blob = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        record = record_type(Type=1, TargetName=self.target(address), UserName="SDITADC", Persist=2,
                             CredentialBlobSize=len(data), CredentialBlob=blob)
        if not api.CredWriteW(ctypes.byref(record), 0):
            raise RuntimeError("无法保存Windows凭据，密钥仅本次有效")

    def delete(self, address):
        api, _ = self._api()
        if not api.CredDeleteW(self.target(address), 1, 0) and ctypes.get_last_error() != 1168:
            raise RuntimeError("无法删除Windows凭据")
