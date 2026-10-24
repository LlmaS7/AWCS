"""Preview parameters. Simulation time is measured in integer ticks."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / "outputs"
FRONTEND = ROOT / "frontend"
MAPS = ROOT / "maps"
DEFAULT_MAP = "warehouse"
DEFAULT_ROBOT_COUNT = 3
MAX_ROBOTS = 64
VERSION = "0.4_preview"
DEFAULT_SEED = 20261010
LOAD_TICKS = UNLOAD_TICKS = 2
INITIAL_TASKS = 9
AUTO_INTERVAL = 45
WAIT_WARNING = 120
PLAN_SECONDS = 2.0
PLAN_HORIZON = 260
CBS_NODE_LIMIT = 6000
FLEET_CBS_SECONDS = .35

