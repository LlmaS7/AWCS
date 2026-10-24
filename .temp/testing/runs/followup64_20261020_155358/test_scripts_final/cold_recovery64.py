from pathlib import Path
import sys,json,subprocess,os,time
sys.dont_write_bytecode=True
from followup64 import dump,summarize,ROOT
HERE=Path(__file__).resolve().parent
out=Path(sys.argv[1]);original=out.parent/'20261020_144032_8fe978'/'cases'
for name in ('EXPERIMENT64-rectangle-20262018','EXPERIMENT64-rooms-20262018'):
    target=out/'cases'/(name+'-retention-cold');target.mkdir(parents=True,exist_ok=True)
    spec=dict(case_id=target.name,source_case=str(original/name),from_start=True,wall_seconds=600)
    dump(target/'input.json',spec)
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONIOENCODING':'utf-8'}
    try:
        p=subprocess.run([sys.executable,'-B',str(HERE/'retention64.py'),'--child',str(target/'input.json'),str(target)],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=660)
        (target/'stdout.txt').write_text(p.stdout,encoding='utf-8');(target/'stderr.txt').write_text(p.stderr,encoding='utf-8')
    except subprocess.TimeoutExpired:dump(target/'result.json',dict(case_id=spec['case_id'],source_case=spec['source_case'],strategy='retain_safe_suffix',status='INCONCLUSIVE',elapsed=660,terminal='hard_timeout'))
    row=json.loads((target/'result.json').read_text(encoding='utf-8'));summarize(out)
    print(json.dumps({k:row.get(k) for k in ('case_id','status','completed','total','elapsed','retentions','terminal','error')},ensure_ascii=False),flush=True)