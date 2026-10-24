"""Two independent native windows, sharing one local server and controller."""
from threading import RLock
from pathlib import Path
import sys
import webview


APP_ICON = Path(__file__).resolve().parent / "frontend" / "assets" / "app-icon.ico"
APP_USER_MODEL_ID = "AWCS"


def configure_native_identity():
    """Keep this desktop app separate from the Python host in the taskbar."""
    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes
    set_id = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
    set_id.argtypes = [wintypes.LPCWSTR]
    set_id.restype = ctypes.c_long
    result = set_id(APP_USER_MODEL_ID)
    if result < 0:
        raise OSError(f"Cannot set AWCS taskbar identity: HRESULT 0x{result & 0xffffffff:08x}")


class DesktopWindows:
    def __init__(self, url, hidden=False):
        configure_native_identity()
        self._url=url
        self._hidden=hidden
        self._lock=RLock()
        self._debug=None
        self._closing=False
        self._main=webview.create_window("AWCS",url,
                                      js_api=self,width=1460,height=940,min_size=(1080,720),
                                      hidden=hidden,maximized=not hidden,background_color="#121416")
        self._main.events.closed += self._main_closed

    def open_debug(self):
        with self._lock:
            if self._closing:
                return {"ok":False}
            if self._debug is not None and self._debug in webview.windows:
                window=self._debug
            else:
                window=webview.create_window("AWCS",self._url+"debug.html",
                                            js_api=self,width=900,height=800,min_size=(680,600),
                                            hidden=self._hidden,background_color="#121416")
                self._debug=window
                window.events.closed += lambda: self._debug_closed(window)
        if not self._hidden:
            window.show()
        return {"ok":True}

    def focus_main(self):
        if not self._hidden and not self._closing:
            self._main.show()
        return {"ok":not self._closing}

    def _debug_closed(self, window):
        with self._lock:
            if self._debug is window:
                self._debug=None

    def _main_closed(self):
        with self._lock:
            self._closing=True
            window=self._debug
            self._debug=None
        if window is not None and window in webview.windows:
            window.destroy()

