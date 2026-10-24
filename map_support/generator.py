"""Compatibility for historical built-in regeneration; implementation is in map_studio.

Normal simulation startup reads JSON and does not import this adapter.
"""
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path

_source = Path(__file__).resolve().parents[1]/'map_studio'/'legacy.py'
_spec = spec_from_file_location('_awcs_legacy_map_generator',_source)
_module = module_from_spec(_spec)
_spec.loader.exec_module(_module)
generate = _module.generate