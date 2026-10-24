from pathlib import Path
import sys,json
sys.dont_write_bytecode=True
from core import Recorder
from checkers import require
out=Path(sys.argv[1]);rec=Recorder(out)
adjudications=json.loads((out/'adjudications.json').read_text(encoding='utf-8'))
for path in sorted((out.parent.parent/'datasets/maps').glob('*.json')):
    original='G-independent-'+path.stem
    def static(path=path):
        d=json.loads(path.read_text(encoding='utf-8'))
        starts=list(map(tuple,d['points']['starts']));parking=set(map(tuple,d['points']['parking']))
        require(set(starts)<=parking,'start not parking')
        require(len(starts)>=d['robots']['max_count'] and len(parking)>=d['robots']['max_count'],'capacity exceeds endpoints')
        connected=set()
        for p in starts:
            if connected:require(any(abs(p[0]-q[0])+abs(p[1]-q[1])==1 for q in connected),'start prefix disconnected')
            connected.add(p)
        groups=[set(map(tuple,d['points'][k])) for k in ('parking','pickups','deliveries')]
        require(all(not groups[i]&groups[j] for i in range(3) for j in range(i)),'business point groups overlap')
    row=rec.case(original+'-UTF8','P4-static-audit',static,dict(map_file=str(path),retest_of=original))
    if row['status']=='PASS':adjudications[original]=dict(classification='HARNESS_ERROR',resolved_by=row['case_id'],reason='Supplemental fixture decoded a UTF-8 map with Windows default GBK, before any static assertions ran. Explicit UTF-8 fixed; same static assertions rerun and original record retained.')
rec.file.close()
(out/'adjudications.json').write_text(json.dumps(adjudications,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(retests=len(rec.rows),passed=sum(r['status']=='PASS' for r in rec.rows))))