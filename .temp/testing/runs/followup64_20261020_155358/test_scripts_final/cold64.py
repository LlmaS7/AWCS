from pathlib import Path
import sys,json
sys.dont_write_bytecode=True
from followup64 import execute_child,config,dump
out=Path(sys.argv[1]);original=out.parent/'20261020_144032_8fe978'/'cases'
# Two representative cold starts; exact original 128-task lists and original maps.
for name in ('EXPERIMENT64-rectangle-20262018','EXPERIMENT64-rooms-20262018'):
    spec=dict(case_id=name+'-rolling128-cold',source_case=str(original/name),strategy='fixed_rolling128',
        wall_seconds=240,ticks=12000,from_start=True,respect_progress_watchdog=True,
        profile=config(mode='rolling',seconds=10,window=128,execute=16))
    execute_child(out,spec)