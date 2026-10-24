"""Read-only A/B runs of archived original and fixed simulation code."""
from pathlib import Path
import sys,json,os,subprocess
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];sys.path.insert(0,str(ROOT))
from run_suite import dump

def child(out,name,variant):
    out=Path(out);import simulation
    if variant=='before':
        original=(out/'baseline/simulation.py').read_text(encoding='utf-8')
        exec(compile(original,str(out/'baseline/simulation.py'),'exec'),simulation.__dict__)
    from run_case import execute
    source=HERE/'runs/20261020_144032_8fe978/cases'/name
    spec=json.loads((source/'input.json').read_text(encoding='utf-8'))
    spec.update(map_file=str(source/'actual_map.json'),case_id=variant+'-'+name,source_case=str(source))
    folder=out/'baseline_controls'/spec['case_id'];folder.mkdir(parents=True,exist_ok=True)
    dump(folder/'input.json',spec)
    execute(spec,folder)

def main(out):
    out=Path(out).resolve();records=[]
    names=['DYNAMIC-courtyard','DYNAMIC-rectangle']
    for rf in sorted((out/'cases').glob('FIX-SCALE32-*/result.json')):
        if json.loads(rf.read_text(encoding='utf-8'))['status']!='PASS':names.append(rf.parent.name.removeprefix('FIX-'))
    for name in names:
        pair={}
        for variant in (('before','after') if name.startswith('DYNAMIC-') else ('before',)):
            env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONIOENCODING':'utf-8'}
            p=subprocess.run([sys.executable,'-B',str(__file__),'--child',str(out),name,variant],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=130)
            folder=out/'baseline_controls'/(variant+'-'+name)
            (folder/'stdout.txt').write_text(p.stdout,encoding='utf-8');(folder/'stderr.txt').write_text(p.stderr,encoding='utf-8')
            if not (folder/'result.json').exists():raise RuntimeError('Control did not return a result: '+p.stderr)
            row=json.loads((folder/'result.json').read_text(encoding='utf-8'))
            pair[variant]={k:row.get(k) for k in ('status','completed','total','tick','elapsed','terminal','metrics')}
            print(json.dumps(dict(case=name,variant=variant,**{k:row.get(k) for k in ('status','completed','elapsed')})),flush=True)
        if 'after' not in pair:
            row=json.loads((out/'cases'/('FIX-'+name)/'result.json').read_text(encoding='utf-8'))
            pair['after']={k:row.get(k) for k in ('status','completed','total','tick','elapsed','terminal','metrics')}
            pair['after_from_original_matrix']=True
        records.append(dict(case_id=name,plan_seconds=3,**pair));dump(out/'baseline_controls_summary.json',records)
if __name__=='__main__':
    if sys.argv[1]=='--child':child(sys.argv[2],sys.argv[3],sys.argv[4])
    else:main(sys.argv[1])
