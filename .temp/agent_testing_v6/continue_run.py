"""Versioned continuation: retain valid first attempts and their original failures."""
from harness import *
from run_agent_suite import prepare,report,ROOT
from review_existing import PARENT
import argparse
import ast,hashlib

def prepare_continuation(parent,track=True):
    parent=Path(parent).resolve();audit=parent/'review/20261021_r1'
    checked=read(audit/'summary_reviewed.json');reviews=read(audit/'adjudications.json')
    manifest=read(parent/'manifest.json')
    old_root=parent.parent.parent
    for filename,sha in manifest['test_hashes'].items():
        if digest(old_root/filename)!=sha:raise RuntimeError('frozen parent test source changed: '+filename)
    def scope(folder,filename,name):
        tree=ast.parse((folder/filename).read_text(encoding='utf-8'))
        node=next(n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name==name)
        return hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest()
    unchanged={}
    for filename,names in {'checks.py':['offline'],'matrix.py':['document_run','inspect_protocol','expected_new'],
                           'oracle.py':['multiset','process_errors','query_satisfied','classify']}.items():
        for name in names:
            old=scope(old_root,filename,name);new=scope(ROOT,filename,name)
            if old!=new:raise RuntimeError('inherited scoring/guard scope changed: '+name)
            unchanged[filename+':'+name]=old
    if checked['raw_jsonl_sha256']!=digest(parent/'results_raw.jsonl'):raise RuntimeError('parent raw evidence changed')
    if manifest['source_hashes']!=sources():raise RuntimeError('production source changed; cannot carry prior evidence')
    if checked['test_invalid']!=['D09'] or checked['unexpected_business_side_effects_observed']!=0:raise RuntimeError('parent audit does not authorize this continuation')
    if checked['failures']!=['C01','F01']:raise RuntimeError('parent failure accounting changed')
    for r in reviews:
        d=Path(r['evidence_dir'])
        for filename,sha in r['evidence_hashes'].items():
            if digest(d/filename)!=sha:raise RuntimeError('audited case evidence changed: '+r['case_id'])
    run=prepare();new_cases={c['case_id']:c for c in read(run/'cases_manifest.json')}
    original_cases={c['case_id']:c for c in read(parent/'cases_manifest.json')}
    old_maps=read(parent/'fixtures/manifest.json');new_maps=read(run/'fixtures/manifest.json')
    if {f['id']:f['sha256'] for f in old_maps}!={f['id']:f['sha256'] for f in new_maps}:raise RuntimeError('map fixture changed')
    rows=[]
    for r in reviews:
        k=r['case_id']
        if k=='D09':continue
        if new_cases[k]!=original_cases[k]:raise RuntimeError('input changed, cannot carry case '+k)
        old_path=Path(r['evidence_dir'])/'result.json';record=read(old_path)
        record.update(execution_origin='inherited_first_attempt',origin_result=str(old_path),origin_result_sha256=digest(old_path),origin_test_version=manifest['version'])
        write(run/'cases'/k/f"repeat_{record['repeat']}"/'result.json',record);rows.append(record)
    if len(rows)!=41:raise RuntimeError('expected exactly 41 valid parent first attempts')
    with (run/'results_raw.jsonl').open('a',encoding='utf-8') as out:
        for r in rows:out.write(json.dumps(r,ensure_ascii=False)+'\n')
    write(run/'review/adjudications.json',[r for r in reviews if r['case_id']!='D09'])
    write(run/'parent_D09_invalid.json',next(r for r in reviews if r['case_id']=='D09'))
    for filename in ('O_results.json','connection_config.json'):write(run/filename,read(parent/filename))
    write(run/'parent_H_results.json',read(parent/'H_results.json'))
    write(run/'inherited_config.json',read(parent/'connection_config.json'))
    write(run/'protocol/result.json',{**read(parent/'protocol/result.json'),'evidence_origin':str(parent/'protocol/result.json'),'inherited':True})
    old_budget=read(parent/'budget.json');budget=deepcopy(old_budget)
    budget['parent_start']=budget['start'];budget['start']=None
    budget['lineage_note']='129 prior reservations retained; new version wall-clock window begins with next real call'
    write(run/'budget.json',budget)
    cp=read(run/'checkpoint.json');old_cp=read(parent/'checkpoint.json')
    cp['stages']={k:{**old_cp['stages'][k],'inherited_from':str(parent)} for k in ('offline','protocol','smoke')}
    cp['stop_reason']=None;write(run/'checkpoint.json',cp)
    m=read(run/'manifest.json');m['lineage']={'parent_run':str(parent),'parent_test_version':manifest['version'],
      'inherited_cases':41,'inherited_api_reservations':len(budget['reservations']),'excluded_invalid_case':'D09',
      'new_execution_count_expected':169,'audit':str(audit/'summary_reviewed.json'),
      'new_case_input_changed':['D09'],'budget_clock':'fresh 4h for explicitly new version; all historical reservations retained'}
    m['lineage']['unchanged_scope_hashes']=unchanged
    write(run/'manifest.json',m)
    if track:write(ROOT/'latest_continuation.json',{'parent_run':str(parent),'run_dir':str(run)})
    report(run)
    print('CONTINUATION_RUN='+str(run));print('INHERITED_FIRST_ATTEMPTS=41');print('REMAINING=169')
    return run

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--parent',type=Path,default=PARENT);p.add_argument('--prepare-only',action='store_true')
    args=p.parse_args();pointer=ROOT/'latest_continuation.json'
    if pointer.exists():
        existing=read(pointer)
        if Path(existing['parent_run']).resolve()!=args.parent.resolve():raise RuntimeError('another parent already bound to this continuation root')
        run=Path(existing['run_dir'])
    else:run=prepare_continuation(args.parent)
    if not args.prepare_only:
        from run_agent_suite import main
        sys.argv=[sys.argv[0],'--stage','all','--resume',str(run)]
        raise SystemExit(main())
