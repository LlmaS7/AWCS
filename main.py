"""Launch the independent HTML desktop window, browser mode, or headless core."""
import argparse
import json
import sys
import traceback
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep
import webbrowser

from config import DEFAULT_SEED, DEFAULT_MAP, OUTPUTS
from controller import Controller
from persistence import load, save, write_json
from server import start_server
from simulation import Simulation
from coordination.contracts import PlanningProfile


def planning_profile(args):
    return PlanningProfile(mode=args.planner,coupling=args.coupling,seconds=args.plan_seconds)


def headless(args):
    sim = load(Path(args.load)) if args.load else Simulation(args.seed, map_id=args.map_id, robot_count=args.robots, profile=planning_profile(args))
    if args.auto:
        sim.command("auto", enabled=True)
    for _ in range(args.ticks):
        if not sim.step():
            raise RuntimeError(sim.message)
    if not args.no_save:
        save(sim)
    print(json.dumps({"tick": sim.tick, "robot_count": len(sim.robots), **sim.snapshot().metrics}, ensure_ascii=False, indent=2))


def graphical(args):
    native = not (args.serve or args.browser)
    controller = Controller(args.seed, paused=args.paused or native, auto=args.auto,
                            scenario=Path(args.load) if args.load else None, map_id=args.map_id,
                            robot_count=args.robots, profile=planning_profile(args))
    server, url = start_server(controller, args.port)
    controller.start()
    print(f"AWCS: {url}", flush=True)
    try:
        if args.serve or args.browser:
            if args.browser:
                webbrowser.open(url)
                if args.debug_window:
                    webbrowser.open_new(url + "debug.html")
            while True:
                sleep(.25)
        else:
            import webview
            from desktop import APP_ICON, DesktopWindows
            smoke = args.smoke_test
            windows = DesktopWindows(url, hidden=smoke)
            window = windows._main
            result = {"ok": False}

            def valid_main(value):
                if not value or not value.get("ready"):
                    return False
                coordinates, canvas = value.get("positions", []), value.get("canvas2d", [])
                same = len(coordinates) == len(canvas) == len(controller.sim.robots) and all(
                    abs(a["x"]-b["x"]) < 1e-6 and abs(a["y"]-b["y"]) < 1e-6
                    for a,b in zip(coordinates,canvas))
                return bool(value.get("webgl2") and value.get("drawCalls",0)>0 and same
                            and all(t is not None and int(t)==value["tick"] for t in value.get("viewTicks",[])))

            def wait_pair(tick, task_count):
                deadline = monotonic()+15
                while monotonic()<deadline:
                    if windows._debug is not None:
                        primary = window.evaluate_js("window.previewDebug ? window.previewDebug.inspect() : null")
                        secondary = windows._debug.evaluate_js("window.debugInspect ? window.debugInspect() : null")
                        if valid_main(primary) and secondary and secondary.get("ready"):
                            if primary["tick"] == secondary["tick"] == tick and primary["taskIds"] == secondary["taskIds"] and len(primary["taskIds"]) == task_count:
                                return primary,secondary
                    sleep(.12)
                raise RuntimeError("两个窗口的状态未同步")

            def inspect_window():
                deadline = monotonic() + 35
                try:
                    while monotonic() < deadline:
                        try:
                            value = window.evaluate_js("window.previewDebug ? window.previewDebug.inspect() : null")
                            if value and value.get("ready"):
                                result.update(value)
                                if smoke:
                                    bridge = window.evaluate_js("Boolean(window.pywebview?.api?.open_debug)")
                                    if not valid_main(value) or not bridge:
                                        sleep(.12)
                                        continue
                                    result["pair_check_started"] = True
                                    window.evaluate_js("document.querySelector('#debug-window').click(); true")
                                    first, debug = wait_pair(0,9)
                                    result["main"] = first
                                    result["debug"] = debug
                                    result["two_windows"] = True
                                    controller.submit("random").result(timeout=10)
                                    wait_pair(0,10)
                                    controller.submit("step").result(timeout=10)
                                    wait_pair(1,10)
                                    result["shared_commands"] = True
                                    windows._debug.destroy()
                                    close_deadline = monotonic()+5
                                    while windows._debug is not None and monotonic()<close_deadline:
                                        sleep(.1)
                                    if windows._debug is not None:
                                        raise RuntimeError("关闭调试窗口未释放窗口引用")
                                    windows.open_debug()
                                    wait_pair(1,10)
                                    result["reopen_preserves_state"] = True
                                    result["ok"] = True
                                elif args.debug_window:
                                    windows.open_debug()
                                if not smoke and not args.paused:
                                    controller.submit("pause", {"paused": False}).result(timeout=10)
                                break
                        except Exception as exc:
                            if smoke and result.get("pair_check_started"):
                                result["error"] = str(exc)
                                break
                        sleep(.15)
                finally:
                    if smoke:
                        write_json(OUTPUTS / "desktop_check.json", result)
                        window.destroy()

            with TemporaryDirectory(prefix="sditadc-webview-", ignore_cleanup_errors=True) as profile:
                webview.start(inspect_window, gui="edgechromium", debug=args.debug,
                              private_mode=True, storage_path=profile, icon=str(APP_ICON))
            if smoke and not (result["ok"] and result.get("shared_commands") and result.get("reopen_preserves_state")):
                raise RuntimeError(f"独立窗口渲染检查未通过：{result}")
    except KeyboardInterrupt:
        pass
    finally:
        server.ai.close()
        controller.stop(save_on_exit=not args.no_save and not args.smoke_test)
        server.shutdown()
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description="AWCS HTML + Three.js multi-robot preview")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--map", dest="map_id", default=DEFAULT_MAP, help="Map filename stem under maps/")
    parser.add_argument("--robots", type=int, help="Robot count within the selected map's capacity")
    parser.add_argument('--planner', choices=['legacy_full','scalable_full','rolling'], default='scalable_full')
    parser.add_argument('--coupling', choices=['off','estimated','candidate'], default='off')
    parser.add_argument('--plan-seconds', type=float, default=3.0)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--ticks", type=int, default=1200)
    parser.add_argument("--auto", action="store_true")
    parser.add_argument("--paused", action="store_true")
    parser.add_argument("--load")
    parser.add_argument("--browser", action="store_true", help="Open the same UI in a browser")
    parser.add_argument("--serve", action="store_true", help="Serve locally without opening a window")
    parser.add_argument("--port", type=int, default=0, help="0 selects a free local port")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--debug-window", action="store_true", help="Open the separate control/debug window on startup")
    parser.add_argument("--smoke-test", action="store_true", help="Check hidden native WebView2 rendering")
    parser.add_argument("--no-save", action="store_true", help="Do not overwrite saved runs on exit")
    args = parser.parse_args()
    headless(args) if args.headless else graphical(args)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        OUTPUTS.mkdir(parents=True, exist_ok=True)
        (OUTPUTS / "startup_error.log").write_text(traceback.format_exc(), encoding="utf-8")
        if sys.stderr is None:
            if "--smoke-test" not in sys.argv:
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, "启动未完成，请查看本版本 outputs/startup_error.log。", "AWCS", 16)
            sys.exit(1)
        raise

