from pathlib import Path
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT))
import os,json,hashlib,subprocess,platform,datetime,uuid,time,csv,argparse,random
from collections import Counter


def dump(path,value):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding='utf-8')


def hashes():
    tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in tracked if p and (ROOT/p).is_file()}


def summarize(out):
    file=out/'results.jsonl'
    rows=[json.loads(line) for line in file.read_text(encoding='utf-8').splitlines() if line.strip()] if file.exists() else []
    grouped={}
    for stage in sorted({r['stage'] for r in rows}):
        grouped[stage]=dict(Counter(r['status'] for r in rows if r['stage']==stage))
    fields=['case_id','stage','status','elapsed','completed','total','tick','plan_checks','actual_steps_checked','path_points_checked','terminal','error']
    with (out/'summary.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
    counts=Counter(r['status'] for r in rows)
    text=['# AWCS 测试运行汇总','',f'运行目录：{out.name}', '',f'逐例记录：{len(rows)}；状态：{dict(counts)}','', '| 阶段 | 状态数量 |','| --- | --- |']
    text += [f'| {k} | {v} |' for k,v in grouped.items()]
    text += ['','## 非通过结果','']
    text += [f"- {r['case_id']}：{r['status']}；{r.get('error') or r.get('message') or r.get('terminal','')}" for r in rows if r['status']!='PASS'] or ['无。']
    text += ['','本汇总仅陈述实际运行结果；完整范围与交付结论见本批次的交付报告。']
    (out/'summary.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    return rows,counts


def record(out,row):
    with (out/'results.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False,default=str)+'\n')
    if row['status']=='FAIL':dump(out/'counterexamples'/(row['case_id']+'.json'),row)


def execute_child(out,spec):
    caseout=out/'cases'/spec['case_id'];caseout.mkdir(parents=True,exist_ok=True)
    dump(caseout/'input.json',spec)
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONIOENCODING':'utf-8'}
    started=time.monotonic()
    try:
        p=subprocess.run([sys.executable,'-B',str(HERE/'run_case.py'),str(caseout/'input.json'),str(caseout)],cwd=ROOT,env=env,
            capture_output=True,text=True,encoding='utf-8',timeout=spec.get('timeout',90))
        (caseout/'stdout.txt').write_text(p.stdout,encoding='utf-8');(caseout/'stderr.txt').write_text(p.stderr,encoding='utf-8')
        if (caseout/'result.json').exists():row=json.loads((caseout/'result.json').read_text(encoding='utf-8'))
        else:row=dict(case_id=spec['case_id'],stage=spec['stage'],status='FAIL',error='child exited without result',returncode=p.returncode,elapsed=time.monotonic()-started)
    except subprocess.TimeoutExpired as exc:
        row=dict(case_id=spec['case_id'],stage=spec['stage'],status='INCONCLUSIVE',terminal='hard_timeout',elapsed=time.monotonic()-started,inputs=spec)
        dump(caseout/'result.json',row)
    record(out,row);summarize(out)
    print(json.dumps({k:row.get(k) for k in ('case_id','status','completed','total','tick','elapsed','error')},ensure_ascii=False),flush=True)


def workload(definition,n,seed,dynamic=False):
    rng=random.Random(seed);items=[]
    for i in range(60 if dynamic else 2*n):
        items.append(dict(tick=(i//12)*40 if dynamic else 0,pickup=rng.randrange(len(definition['points']['pickups'])),
            delivery=rng.randrange(len(definition['points']['deliveries'])),priority=1+i%5))
    return items


def prepare_maps(out):
    from map_studio.generator import generate
    from map_format import validate_map
    from checkers import Grid,require
    entries=[]
    for shape in ('rectangle','l','t','u','courtyard','rooms','random'):
        for seed in (20261018,20261019):
            params=dict(width=96,height=64,robots=32,seed=seed,shape=shape,aisle=3,density=65,obstacles=20)
            cid=f'MAP-{shape}-{seed}';began=time.monotonic()
            try:
                definition=generate(**params);again=generate(**params)
                require(definition==again,'generator not reproducible')
                validate_map(definition);grid=Grid(definition['grid']['rows']);origin=tuple(definition['points']['starts'][0])
                todo=[origin];seen={origin}
                for p in todo:
                    for q in grid.neighbors(p):
                        if q not in seen:seen.add(q);todo.append(q)
                require(len(seen)==sum(r.count('.') for r in grid.rows),'independent connectivity failed')
                for group in definition['points'].values():
                    require(all(tuple(p) in seen for p in group),'unreachable endpoint')
                path=HERE/'datasets'/'maps'/f'{shape}_{seed}.json';dump(path,definition)
                entries.append((shape,seed,path,definition))
                row=dict(case_id=cid,stage='P4-static',status='PASS',parameters=params,map_file=str(path),elapsed=time.monotonic()-began)
            except Exception as exc:
                row=dict(case_id=cid,stage='P4-static',status='FAIL',parameters=params,error=f'{type(exc).__name__}: {exc}',elapsed=time.monotonic()-began)
            record(out,row);print(cid,row['status'],flush=True)
    for path in sorted((ROOT/'maps').glob('*.json')):
        began=time.monotonic()
        try:
            definition=json.loads(path.read_text(encoding='utf-8-sig'));validate_map(definition)
            row=dict(case_id='STATIC-'+path.stem,stage='P4-static',status='PASS',elapsed=time.monotonic()-began)
        except Exception as exc:row=dict(case_id='STATIC-'+path.stem,stage='P4-static',status='FAIL',error=str(exc),elapsed=time.monotonic()-began)
        record(out,row)
    dump(out/'generated_maps_manifest.json',[dict(shape=s,seed=seed,map_file=str(p),parameters=d['metadata']['parameters']) for s,seed,p,d in entries])
    return entries


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=['core','generated','extended','all','summarize'],default='all');parser.add_argument('--run-dir');parser.add_argument('--case')
    args=parser.parse_args()
    if args.run_dir:out=Path(args.run_dir).resolve()
    else:
        now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
        out=HERE/'runs'/(now.strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6])
    out.mkdir(parents=True,exist_ok=True);(out/'counterexamples').mkdir(exist_ok=True)
    print('RUN_DIR='+str(out),flush=True)
    if not (out/'environment.json').exists():
        dump(out/'environment.json',dict(time=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),python=sys.version,executable=sys.executable,platform=platform.platform(),processor=platform.processor(),cpu_count=os.cpu_count(),cwd=str(ROOT),commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),git_status=subprocess.check_output(['git','status','--short'],cwd=ROOT,text=True)))
        dump(out/'source_hashes.json',hashes())
        dump(out/'test_hashes_start.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.glob('*.py')})
    if args.stage=='summarize':summarize(out);return
    if args.stage in ('all','core'):
        dump(out/'core_manifest.json',dict(assignment=dict(robots=list(range(5)),tasks=list(range(6)),seeds=list(range(40)),seed_formula='100000+n*10000+m*100+seed'),hungarian='n=0..4,m=max(1,n)..6,seed=0..4',reservations='seed=0..149',sipp='seed=300000..300199;horizon=12;grid=4x4'))
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONIOENCODING':'utf-8'}
        p=subprocess.run([sys.executable,'-B',str(HERE/'core.py'),str(out)],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=300)
        (out/'core.stdout.txt').write_text(p.stdout,encoding='utf-8');(out/'core.stderr.txt').write_text(p.stderr,encoding='utf-8');print(p.stdout,flush=True)
        if p.returncode:record(out,dict(case_id='CORE-PROCESS',stage='P0',status='FAIL',error=p.stderr,returncode=p.returncode))
        summarize(out)
    entries=[]
    if args.stage in ('all','generated','extended'):
        entries=prepare_maps(out)
    specs=[]
    if args.stage in ('all','generated'):
        for shape,seed,path,d in entries:
            for n in (4,16):specs.append(dict(case_id=f'GEN-{shape}-{seed}-{n}',stage='P4-main',map_file=str(path),robots=n,seed=seed+1000,tasks=workload(d,n,seed+1000),plan_seconds=3,ticks=6000,timeout=90,wall_seconds=85))
        for shape in ('rectangle','courtyard','rooms'):
            s,seed,path,d=next(e for e in entries if e[0]==shape)
            specs.append(dict(case_id='DYNAMIC-'+shape,stage='P4-dynamic',map_file=str(path),robots=16,seed=seed+1000,tasks=workload(d,16,seed+1000,True),plan_seconds=3,ticks=10000,timeout=120,wall_seconds=115))
        for shape in ('rectangle','rooms'):
            s,seed,path,d=next(e for e in entries if e[0]==shape)
            specs.append(dict(case_id='PROBE-'+shape,stage='P4-probe',kind='probe',map_file=str(path),robots=16,seed=20262018,timeout=90))
    if args.stage in ('all','extended'):
        from map_studio.generator import generate
        for source in ('fleet_64x64','irregular_96x64','rectangle','rooms'):
            if source in ('rectangle','rooms'):
                s,seed,path,d=next(e for e in entries if e[0]==source)
            else:path=ROOT/'maps'/(source+'.json');d=json.loads(path.read_text(encoding='utf-8'))
            for seed in (20262018,20262019):specs.append(dict(case_id=f'SCALE32-{source}-{seed}',stage='P6-32',map_file=str(path),robots=32,seed=seed,tasks=workload(d,32,seed),plan_seconds=3,ticks=10000,timeout=120,wall_seconds=115))
        for source in ('experimental_128x96','rectangle','rooms'):
            if source=='experimental_128x96':path=ROOT/'maps'/(source+'.json');d=json.loads(path.read_text(encoding='utf-8'))
            else:
                d=generate(width=128,height=96,robots=64,seed=20261018,shape=source,aisle=3,density=65,obstacles=20)
                path=HERE/'datasets'/'maps'/(source+'_64.json');dump(path,d)
            for seed in (20262018,20262019):specs.append(dict(case_id=f'EXPERIMENT64-{source}-{seed}',stage='P6-64',map_file=str(path),robots=64,seed=seed,tasks=workload(d,64,seed),plan_seconds=8,ticks=15000,timeout=180,wall_seconds=175))
        s,seed,path,d=next(e for e in entries if e[0]=='rectangle')
        for coupling in ('off','estimated','candidate'):
            for repetition in range(3):specs.append(dict(case_id=f'COUPLING-{coupling}-{repetition}',stage='P6-coupling',map_file=str(path),robots=4,seed=20262018,tasks=workload(d,4,20262018),coupling=coupling,plan_seconds=3,ticks=3000,timeout=60,wall_seconds=55))
        for mode in ('rolling','legacy_full'):
            specs.append(dict(case_id='MODE-'+mode,stage='P6-mode',map_file=str(path),robots=4,seed=20262018,tasks=workload(d,4,20262018),mode=mode,plan_seconds=3,ticks=4000,timeout=90,wall_seconds=85))
        specs.append(dict(case_id='WORKER-PROCESS',stage='P5-process',kind='worker',map_file=str(path),timeout=30))
    dump(out/(args.stage+'_cases_manifest.json'),specs)
    began=time.monotonic()
    for spec in specs:
        if args.case and args.case!=spec['case_id']:continue
        if time.monotonic()-began>6000:
            record(out,dict(case_id=spec['case_id'],stage=spec['stage'],status='NOT_RUN',reason='batch wall budget'));continue
        execute_child(out,spec)
    final=hashes();dump(out/'source_hashes_end.json',final)
    original=json.loads((out/'source_hashes.json').read_text(encoding='utf-8'))
    dump(out/'source_integrity.json',dict(unchanged=original==final,changed=[p for p in set(original)|set(final) if original.get(p)!=final.get(p)]))
    dump(out/'test_hashes_end.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.glob('*.py')})
    rows,counts=summarize(out);print(json.dumps(dict(final_counts=counts),ensure_ascii=False),flush=True)
    sys.exit(1 if counts.get('FAIL') else (2 if any(counts.get(s) for s in ('INCONCLUSIVE','NOT_RUN','BLOCKED')) else 0))

if __name__=='__main__':main()