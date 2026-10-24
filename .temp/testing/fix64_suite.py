"""Run fixed production code on frozen inputs. No test-side recovery policy."""
from pathlib import Path
import sys,datetime,json,subprocess,os,time,hashlib,shutil
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT))
from run_suite import dump,record,summarize
ORIGINAL=HERE/'runs/20261020_144032_8fe978'

def fingerprint():
    names=set(subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0'))
    names.update(('coordination/recovery.py','tests/test_plan_recovery.py'))
    return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(names) if n and (ROOT/n).is_file()}

def trial(out, source, budget=None):
    spec=json.loads((source/'input.json').read_text(encoding='utf-8'))
    spec['source_case']=str(source);spec['map_file']=str(source/'actual_map.json')
    spec['case_id']=('FIX10-' if budget else 'FIX-')+spec['case_id']
    if budget:spec['plan_seconds']=budget
    if spec.get('kind') in ('worker','probe'):
        if not Path(spec['map_file']).exists():spec['map_file']=json.loads((source/'input.json').read_text(encoding='utf-8'))['map_file']
    if spec.get('robots')==64:
        spec.update(timeout=690,wall_seconds=600,ticks=30000)
    target=out/'cases'/spec['case_id'];target.mkdir(parents=True,exist_ok=True)
    dump(target/'input.json',spec)
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONIOENCODING':'utf-8'}
    try:
        p=subprocess.run([sys.executable,'-B',str(HERE/'run_case.py'),str(target/'input.json'),str(target)],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=spec.get('timeout',120))
        (target/'stdout.txt').write_text(p.stdout,encoding='utf-8');(target/'stderr.txt').write_text(p.stderr,encoding='utf-8')
        if not (target/'result.json').exists():dump(target/'result.json',dict(case_id=spec['case_id'],stage=spec['stage'],status='FAIL',error=p.stderr))
    except subprocess.TimeoutExpired:dump(target/'result.json',dict(case_id=spec['case_id'],stage=spec['stage'],status='INCONCLUSIVE',terminal='hard_timeout'))
    row=json.loads((target/'result.json').read_text(encoding='utf-8'));record(out,row);summarize(out)
    print(json.dumps({k:row.get(k) for k in ('case_id','stage','status','completed','total','tick','elapsed','terminal','error')},ensure_ascii=False),flush=True)

def main(out,phase):
    out=Path(out).resolve();(out/'counterexamples').mkdir(exist_ok=True)
    if not (out/'source_hashes_after_fix.json').exists():dump(out/'source_hashes_after_fix.json',fingerprint())
    sources=sorted((ORIGINAL/'cases').glob('EXPERIMENT64-*')) if phase.startswith('cold64') else sorted(p.parent for p in (ORIGINAL/'cases').glob('*/input.json') if json.loads(p.read_text(encoding='utf-8')).get('stage') in ('P4-main','P4-dynamic','P6-32','P6-coupling','P6-mode','P5-process'))
    for source in sources:
        cid=('FIX10-' if phase=='cold64-10' else 'FIX-')+source.name
        if (out/'cases'/cid/'result.json').exists():continue
        trial(out,source,10 if phase=='cold64-10' else None)
    if phase=='regression':
        for name in ('rectangle-20262019','rooms-20262018','rooms-20262019'):
            if (out/'cases'/('FIX-ACTOR64-'+name)/'result.json').exists():continue
            env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONIOENCODING':'utf-8'}
            p=subprocess.run([sys.executable,'-B',str(HERE/'fix64_actor.py'),str(out),name],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=360)
            (out/('actor_'+name+'.stdout.txt')).write_text(p.stdout,encoding='utf-8')
            (out/('actor_'+name+'.stderr.txt')).write_text(p.stderr,encoding='utf-8')
            target=out/'cases'/('FIX-ACTOR64-'+name)/'result.json'
            if not target.exists():raise RuntimeError('Actor trial did not return its result: '+p.stderr)
            row=json.loads(target.read_text(encoding='utf-8'))
            print(json.dumps({k:row.get(k) for k in ('case_id','status','completed','total','elapsed','error')},ensure_ascii=False),flush=True)
    final=fingerprint();dump(out/'source_hashes_final.json',final)
    dump(out/'source_integrity.json',dict(unchanged_since_fix=final==json.loads((out/'source_hashes_after_fix.json').read_text(encoding='utf-8'))))
    rows,counts=summarize(out);print(json.dumps(dict(phase=phase,counts=counts)),flush=True)
if __name__=='__main__':main(sys.argv[1],sys.argv[2])
