from pathlib import Path
import sys,json
sys.dont_write_bytecode=True
from run_suite import execute_child
out=Path(sys.argv[1])
source=json.loads((out/'cases/WORKER-PROCESS/input.json').read_text(encoding='utf-8'))
source['case_id']='WORKER-PROCESS-UTF8'
source['retest_of']='WORKER-PROCESS'
execute_child(out,source)
result=json.loads((out/'cases/WORKER-PROCESS-UTF8/result.json').read_text(encoding='utf-8'))
if result['status']=='PASS':
    (out/'adjudications.json').write_text(json.dumps({'WORKER-PROCESS':dict(classification='HARNESS_ERROR',resolved_by='WORKER-PROCESS-UTF8',reason='Test harness used platform-default GBK to read a UTF-8 JSON map. Fixed encoding in worker fixture only; original error occurred before production worker initialization. Original result retained.')},ensure_ascii=False,indent=2),encoding='utf-8')