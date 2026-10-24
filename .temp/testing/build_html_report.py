from pathlib import Path
import sys,json,gzip,hashlib,datetime
from collections import Counter,defaultdict
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'.temp/testing';OLD=BASE/'runs/20261020_144032_8fe978';NEW=BASE/'runs/followup64_20261020_155358'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def trace(p,initial=None):
    frames=[]
    if initial:
        s=read(initial);frames.append([s['tick'],sum(t['status']=='completed' for t in s['tasks']),[[r['id'],*r['position'],phases.index(r['phase']),int(r['loaded'])] for r in s['robots']]])
    with gzip.open(p,'rt',encoding='utf-8') as f:
        for line in f:
            r=json.loads(line);frames.append([r['tick'],sum(t[1]=='completed' for t in r['tasks']),[[b[0],b[1],b[2],phases.index(b[3]),int(b[4])] for b in r['robots']]])
    return frames
phases=['idle','to_pickup','picking','to_delivery','unloading','parking','reserved']
# Real traces contain their first captured tick, supplemented by archived initial state.
allrows=[json.loads(l) for l in (OLD/'accepted_results.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
stages=defaultdict(Counter)
for r in allrows:stages[r['stage']][r['status']]+=1
follow=read(NEW/'results.json')
rows=[]
for r in follow:
    rows.append({k:r.get(k) for k in ['case_id','strategy','status','initial_completed','completed','total','tick','elapsed','plan_checks','failures','retentions','stable_parking_attempts','terminal']})
scenes=[]
for folder in sorted((OLD/'cases').glob('EXPERIMENT64-*')):
    o=read(folder/'result.json');passing=[r for r in follow if Path(r['source_case']).name==folder.name and r['status']=='PASS' and not r.get('reconstruction',{}).get('from_start')][0]
    scenes.append(dict(id=folder.name.replace('EXPERIMENT64-',''),before=o['completed'],old_tick=o['tick'],old_reason=o['terminal'],strategy=passing['strategy'],seconds=passing['elapsed'],tick=passing['tick'],retentions=passing.get('retentions',0)))
replays=[]
for shape,title in [('rectangle','矩形仓库'),('rooms','房间式仓库')]:
    name=f'EXPERIMENT64-{shape}-20262018';folder=NEW/'cases'/(name+'-retention-cold');original=OLD/'cases'/name
    attempts=[json.loads(l) for l in (folder/'attempts.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
    replays.append(dict(id=shape,title=title,map=read(folder/'actual_map.json'),frames=trace(folder/'trace.jsonl.gz',folder/'initial_state.json'),baseline=[[f[0],f[1]] for f in trace(original/'trace.jsonl.gz')],result=read(folder/'result.json'),original=read(original/'result.json'),failure_ticks=[a['tick'] for a in attempts if not a['success']]))
data=dict(main=read(OLD/'delivery_facts.json'),followup=read(NEW/'followup_facts.json'),stages={k:dict(v) for k,v in stages.items()},scenes=scenes,trials=rows,replays=replays,phases=phases,witness=read(NEW/'feasibility_witness.json'),hardware=read(OLD/'hardware.json'),environment=read(OLD/'environment.json'),provenance=read(NEW/'provenance.json'))
assert len(allrows)==2029 and len(rows)==19 and all(p['result']['completed']==128 for p in replays)
payload=json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
template=Path(__file__).with_name('report_template.html').read_text(encoding='utf-8')
output=ROOT/'.report/AWCS_项目测试报告.html';output.parent.mkdir(exist_ok=True)
output.write_text(template.replace('__REPORT_DATA__',payload),encoding='utf-8')
(BASE/'html_report_build.json').write_text(json.dumps(dict(output=str(output),bytes=output.stat().st_size,sha256=hashlib.sha256(output.read_bytes()).hexdigest(),main_cases=len(allrows),followup_trials=len(rows),replay_frames=[len(r['frames']) for r in replays],created=datetime.datetime.now().astimezone().isoformat()),ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(output=str(output),bytes=output.stat().st_size,replay_frames=[len(r['frames']) for r in replays]),ensure_ascii=False))
