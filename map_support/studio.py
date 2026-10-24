"""Optional debug tool, loaded only when opened; no simulation state access."""
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
import sys
from threading import Lock

_lock = Lock()


def open_studio(owner):
    with _lock:
        if not hasattr(owner,'map_studio'):
            root = Path(__file__).resolve().parents[1]/'map_studio'
            if not (root/'__init__.py').is_file():
                raise ValueError('未找到 map_studio；请保留随程序提供的地图工坊目录')
            package = '_awcs_map_studio'
            if package not in sys.modules:
                spec = spec_from_file_location(package,root/'__init__.py',submodule_search_locations=[str(root)])
                module = module_from_spec(spec);sys.modules[package]=module;spec.loader.exec_module(module)
            from importlib import import_module
            owner.map_studio = import_module(package+'.manager').start_server()
        return owner.map_studio[1]
