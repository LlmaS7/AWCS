from pathlib import Path
import sys,json,datetime,uuid,os
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
from run_case import execute

if __name__=='__main__':
    source=Path(sys.argv[1]).resolve()
    spec=json.loads(source.read_text(encoding='utf-8'))
    frozen=source.parent/'actual_map.json'
    if frozen.exists():spec['map_file']=str(frozen)
    else:
        archived=source.parents[2]/'maps'/Path(spec['map_file']).name
        if archived.exists():spec['map_file']=str(archived)
    target=HERE/'runs'/('replay_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6])/'cases'/spec['case_id']
    result=execute(spec,target)
    print(json.dumps(dict(output=str(target),case_id=result['case_id'],status=result['status']),ensure_ascii=False))