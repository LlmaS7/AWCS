"""AWCS agent test entry. Fresh first attempts; append-only results; no secret exports."""
from harness import *
from fixtures import prepare as prepare_fixtures
from cases import manifest as case_manifest,challenge_manifest
from collections import Counter
from datetime import datetime,timezone
import argparse,platform,subprocess

ROOT=Path(__file__).resolve().parent
KEY=PROJECT/'.temp/key.md'
STAGES=('prepare','selftest','offline','protocol','smoke','matrix','challenge','e2e','review','report','all')
SMOKE=('A01','A04','A07','B03','B08','B10','C01','C02','C08','E03','F01','F10')

def test_hashes():
    return {p.name:digest(p) for p in ROOT.glob('*.py') if p.name not in ('probe_environment.py','run_offline_probe.py')}
def prepare():
    run=ROOT/'runs'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');run.mkdir(parents=True)
    fixtures=prepare_fixtures(run/'fixtures');cases=case_manifest(fixtures);challenges=challenge_manifest(fixtures)
    from e2e import manifest
    for case in challenges:
        from challenges import instantiate
        case.update(instantiate(case,next(f for f in fixtures if f['id']==case['map'])))
    write(run/'cases_manifest.json',cases);write(run/'challenge_manifest.json',challenges);write(run/'e2e_manifest.json',manifest())
    plan=PROJECT/'.temp/Agent能力测试执行方案.md'
    try:
        status=subprocess.run(['git','-C',str(PROJECT),'status','--short'],capture_output=True,text=True,encoding='utf-8',errors='replace')
        commit=subprocess.run(['git','-C',str(PROJECT),'rev-parse','HEAD'],capture_output=True,text=True,encoding='utf-8',errors='replace')
    except OSError:
        status=subprocess.CompletedProcess([],1,stdout='');commit=status
    write(run/'manifest.json',{'version':'awcs-agent-suite-20261021-v6','created_utc':datetime.now(timezone.utc).isoformat(),
      'project':str(PROJECT),'artifact_root':str(ROOT),'run':str(run),'python':sys.executable,'platform':platform.platform(),
      'plan_sha256':digest(plan),'git_commit':commit.stdout.strip() if commit.returncode==0 else 'UNAVAILABLE_PERMISSION',
      'git_user_modifications':status.stdout.splitlines() if status.returncode==0 else ['UNAVAILABLE_PERMISSION'],
      'source_hashes':sources(),'test_hashes':test_hashes(),'key_file':str(KEY),'planned':{'H':20,'O':40,'matrix':180,'challenge':24,'e2e':6},
      'budget':{'api_requests':1200,'smoke_and_protocol':60,'seconds':14400,'session_seconds':900},
      'rubric':{'severity':['critical','major','minor','advisory'],'reviewer_type':'execution_AI','auto_retry':False,
                'review_required':'all critical factual claims, source/field semantics, refusals and guarantees',
                'partial_evidence':'never upgrade to complete acceptance'},
      'scope':'Service API integration, not desktop/browser UI; offline synthetic decisions excluded from real model denominator'})
    write(run/'checkpoint.json',{'stages':{},'stop_reason':None});Budget(run)
    print('RUN_DIR='+str(run),flush=True);return run

def verify(run):
    m=read(run/'manifest.json')
    if m['source_hashes']!=sources():raise RuntimeError('production source drift; create a new run')
    if m['test_hashes']!=test_hashes():raise RuntimeError('test source drift; create a new run')
    for f in read(run/'fixtures/manifest.json'):
        if digest(f['scenario'])!=f['sha256']:raise RuntimeError('fixture drift')
    return m

def checkpoint(run,stage,result):
    cp=read(run/'checkpoint.json');cp['stages'][stage]=result;write(run/'checkpoint.json',cp)

def gate(run):
    cp=read(run/'checkpoint.json')
    return all(cp['stages'].get(k,{}).get('passed') is True for k in ('selftest','offline','protocol'))

def protocol(run,values,budget):
    """Read-only production test route; never presents a write tool to the model."""
    f=read(run/'fixtures/manifest.json')[0];d=run/'protocol'
    if (d/'result.json').exists():return read(d/'result.json')
    d.mkdir(parents=True,exist_ok=True)
    write(run/'connection_config.json',{k:v for k,v in values.items() if k!='api_key'})
    result={'stage':'protocol','passed':False,'scope':'read-only production adapter and tool roundtrip'}
    try:
        with Session(f['scenario'],d,DeepSeek(),values,budget,'protocol') as s:
            events=s.message('',kind='test')
            result.update(passed=s.ai.verified,events=events,calls=len(s.observed.calls),tasks=len(s.snapshot()['tasks']),
                          network_errors=[c.get('error') for c in s.observed.calls if c['state']=='error'])
            if result['tasks']!=0:raise RuntimeError('unexpected protocol side effect')
    except Exception as exc:result.update(error_type=type(exc).__name__,error=scrub(str(exc),values.get('api_key','')))
    write(d/'result.json',result);return result

def current_results(run):
    result=[]
    for p in sorted((run/'cases').glob('*/*/result.json')) if (run/'cases').exists() else []:result.append(read(p))
    return result

def report(run):
    m=read(run/'manifest.json');cp=read(run/'checkpoint.json');records=current_results(run)
    reviews=read(run/'review/adjudications.json') if (run/'review/adjudications.json').exists() else []
    applied=[]
    for r in records:
        r=deepcopy(r)
        for review in reviews:
            if review['case_id']==r['case_id'] and review['repeat']==r['repeat']:
                if review.get('evidence_dir') and review['evidence_dir']!=r['evidence']:continue
                r['review']=review
                if r['raw_status'] not in ('FAIL','TEST_INVALID') and review.get('verdict')=='PASS' and all(r.get(k)=='PASS' for k in ('protocol_verdict','business_verdict','required_process_verdict')):
                    r.update(effective_status='PASS',response_verdict='PASS',review_status='COMPLETED')
                elif review.get('verdict')=='FAIL':r.update(effective_status='FAIL',response_verdict='FAIL',review_status='COMPLETED')
        applied.append(r)
    write(run/'results_effective.json',applied)
    H=read(run/'H_results.json') if (run/'H_results.json').exists() else []
    O=read(run/'O_results.json') if (run/'O_results.json').exists() else []
    matrix=[r for r in applied if r['case_id'][0] in 'ABCDEF'];U=[r for r in applied if r['case_id'].startswith('U')]
    X=[read(p) for p in sorted((run/'e2e').glob('*/result.json'))] if (run/'e2e').exists() else []
    for x in X:
        for review in reviews:
            if review['case_id']==x['case_id']:
                x['review']=review
                if review.get('verdict')=='FAIL':x.update(effective_status='FAIL',response_verdict='FAIL',review_status='COMPLETED')
                elif review.get('verdict')=='PASS' and all(x.get(d)=='PASS' for d in ('agent_business','assignment_rules','trajectory_safety','completion')):
                    x.update(effective_status='PASS',response_verdict='PASS',review_status='COMPLETED')
    write(run/'e2e_effective.json',X)
    def counts(rows,key='status',total=None):
        c=Counter(r.get(key,'NOT_RUN') for r in rows)
        if total and len(rows)<total:c['NOT_RUN']+=total-len(rows)
        return dict(c)
    budget=Budget(run).value
    stable=sum(sum(r['case_id']==f'{g}{i:02}' and r['effective_status']=='PASS' for r in matrix)==3 for g in 'ABCDEF' for i in range(1,11))
    summary={'H':counts(H,total=20),'O':counts(O,total=40),'matrix_raw':counts(matrix,'raw_status',180),
             'matrix_effective':counts(matrix,'effective_status',180),'challenge':counts(U,'effective_status',24),
             'e2e':counts(X,'effective_status',6),'stable_scenarios':stable,'api_reservations':len(budget['reservations']),
             'api_send_attempted':sum(x['state']!='reserved' for x in budget['reservations']),
             'api_stream_complete':sum(x['state']=='stream_complete' for x in budget['reservations']),
             'usage_known':sum(x['usage_known'] for x in budget['reservations']),'acceptance':'EVIDENCE_INCOMPLETE',
             'executed_matrix':len(matrix),'executed_challenge':len(U),'executed_e2e':len(X),'review_pending':sum(r.get('review_status')=='PENDING' for r in applied),
             'stop_reason':cp.get('stop_reason'),'source_integrity':sources()==m['source_hashes']}
    if m.get('lineage'):
        summary['lineage']=m['lineage']
        summary['carried_first_attempts']=sum(r.get('execution_origin')=='inherited_first_attempt' for r in applied)
        summary['executed_here']=len(applied)-summary['carried_first_attempts']
    critical=sum(r.get('review',{}).get('severity')=='critical' or r.get('stop_batch')=='UNEXPECTED_SIDE_EFFECT' for r in applied)
    if len(matrix)==180 and len(U)==24 and len(X)==6 and summary['matrix_effective'].get('PASS',0)>=171 and stable>=54 and summary['H'].get('PASS')==20 and summary['O'].get('PASS')==40 and all(x['effective_status']=='PASS' for x in X) and not summary['matrix_effective'].get('TEST_INVALID') and not summary['review_pending'] and not critical:summary['acceptance']='PASS'
    write(run/'summary.json',summary)
    lines=['# AWCS AI Agent 能力测试报告','',f"生成时间：{datetime.now(timezone.utc).astimezone().isoformat()}",'',
           '**结论：'+('达到预设验收线。' if summary['acceptance']=='PASS' else '证据尚不完整，不能判定 Agent 能力通过。')+'**','',
           f"停止原因：`{summary['stop_reason'] or '尚未完成全部阶段/语义复核'}`。",
           '离线预设模型只验证生产保护和驱动，不计真实模型能力；网络失败不记模型业务失败。','',
           '| 层次 | 计划 | 已执行 | 结果 |','| --- | ---: | ---: | --- |']
    for name,total,rows,key in [('H 测试系统自检',20,H,'H'),('O 生产保护',40,O,'O'),('主矩阵',180,matrix,'matrix_effective'),('U 独立挑战',24,U,'challenge'),('X 搬运闭环',6,X,'e2e')]:
        lines.append(f'| {name} | {total} | {len(rows)} | {json.dumps(summary[key],ensure_ascii=False)} |')
    lines += ['',f"主矩阵有效 PASS/{180}：{summary['matrix_effective'].get('PASS',0)}/180；三次稳定通过：{stable}/60。",'',
      '## 配置、版本与实际调用','',f"项目：`{PROJECT}`。源码前后指纹一致：`{summary['source_integrity']}`。",
      f"Git 提交：`{m['git_commit']}`；方案 SHA256：`{m['plan_sha256']}`。",
      '配置只保留非敏感字段，密钥不保存于产物；未调用其他模型、未调整生产 effort、提示词、输出上限或重试策略。']
    if m.get('lineage'):
        lines += ['', '本批为版本化证据继承：保留父批次41个有效首轮样本（包括C01和F01失败），其余案例由本版本继续执行；不声称全部由新驱动重测。',
                  '父批次D09为测试无效，原记录保留，修正输入的新D09须另测；129次历史API预留继承，总调用额度不重置。新版本4小时执行窗单独记录。',
                  f"父批次：`{m['lineage']['parent_run']}`；本批继承{summary['carried_first_attempts']}段，本批实际新增执行{summary['executed_here']}段。"]
    if (run/'connection_config.json').exists():lines += ['', '```json',json.dumps(read(run/'connection_config.json'),ensure_ascii=False,indent=2),'```']
    lines += ['',f"API 预留 {summary['api_reservations']} 次，尝试发送 {summary['api_send_attempted']} 次，完整流 {summary['api_stream_complete']} 次，可得 usage {summary['usage_known']} 次。",
      '无可靠价格或 usage 时不估算金额；尝试连接失败不等于已产生账单。','',
      '## 阻塞、失败与测试缺陷','']
    for r in H+O:
        if r['status']!='PASS':lines.append(f"- {r['case_id']}：**{r['status']}**；{r.get('error','')}。证据：`{r['case_id']}.json`。")
    if (run/'protocol/result.json').exists():
        p=read(run/'protocol/result.json');lines+=['',f"只读协议预检：`{'PASS' if p.get('passed') else 'BLOCKED/INCOMPLETE'}`。",'```json',json.dumps(p,ensure_ascii=False,indent=2),'```']
    for r in applied:
        if r['effective_status'] in ('FAIL','TEST_INVALID'):lines.append(f"- {r['case_id']}/repeat_{r['repeat']}：{r['effective_status']}；`{r['evidence']}`。")
    lines += ['', '## 地图与范围','', '| 地图 | 轮廓 | 四号货架实际映射 | 来源 |','| --- | --- | --- | --- |']
    for f in read(run/'fixtures/manifest.json'):lines.append(f"| {f['id']} | {f['shape']} | {f['pickup']} | {'替代生成' if f['replacement'] else '历史地图网格副本，重新登记业务名称'} |")
    lines += ['', '没有进行浏览器/桌面 UI 验收、长期稳定性或算法规模复测。未执行的矩阵、挑战、闭环和必要语义审阅均不能推定通过。',
      '', '## 复核与复现','',
      f"运行入口：`{ROOT/'run_local.ps1'}`。本批证据：`{run}`。",
      '本地执行后查看 `report/Agent测试报告.md` 和 `summary.json`，再依据逐例证据完成 `review/packet.json` 中的主张复核。',
      '评审标明 execution AI / human，保留原始首次结果，禁止被测模型自评分或拼接最好成绩。']
    (run/'report').mkdir(exist_ok=True)
    path=run/'report/Agent测试报告.md';path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    write(run/'artifact_manifest.json',[str(p.relative_to(run)) for p in run.rglob('*') if p.is_file()])
    return path,summary

def review(run):
    packet=[{'case_id':r['case_id'],'repeat':r['repeat'],'evidence':r['evidence'],'required_claims':r.get('details',{}).get('pending',[]),
             'reviewer_type':'execution_AI_or_human','instructions':'read exact raw replies, receipts, timing and source truth; no self-grading'} for r in current_results(run) if r.get('review_status')=='PENDING']
    write(run/'review/packet.json',packet)
    return {'passed':not packet,'pending':len(packet)}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=STAGES,default='all');parser.add_argument('--resume',type=Path)
    parser.add_argument('--key-file',type=Path,default=KEY);parser.add_argument('--max-api-calls',type=int,default=1200)
    parser.add_argument('--network',choices=['disabled','loopback-only','enabled'],default='enabled')
    args=parser.parse_args();run=args.resume.resolve() if args.resume else prepare();exit_code=0
    cp=read(run/'checkpoint.json')
    try:
        if args.stage=='prepare':return 0
        if args.stage not in ('review','report'):verify(run)
        stages=['selftest','offline','protocol','smoke','matrix','challenge','e2e','review'] if args.stage=='all' else [args.stage]
        values=None;fixtures=read(run/'fixtures/manifest.json');budget=Budget(run,args.max_api_calls)
        for stage in stages:
            cp=read(run/'checkpoint.json')
            if cp.get('stop_reason') and stage in ('smoke','matrix','challenge','e2e'):
                raise RuntimeError('STOPPED_RUN_REQUIRES_REVIEW: '+cp['stop_reason'])
            if stage in ('smoke','matrix','challenge','e2e') and any(r.get('execution_status')=='RUNNING' for r in current_results(run)):
                raise RuntimeError('INTERRUPTED_CASE_REQUIRES_RECONCILIATION: do not replay or skip an unresolved started case')
            if stage in cp['stages']:
                if cp['stages'][stage].get('passed') is False and stage in ('selftest','offline','protocol') and args.stage=='all':
                    cp['stop_reason']='GATE_'+stage.upper();write(run/'checkpoint.json',cp);exit_code=2;break
                continue
            if stage=='selftest':
                from checks import selftest
                rows=selftest(run/'selftest');write(run/'H_results.json',rows);result={'passed':all(r['status']=='PASS' for r in rows),'counts':dict(Counter(r['status'] for r in rows))}
            elif stage=='offline':
                from checks import offline
                rows=offline(run/'offline',fixtures[0]);write(run/'O_results.json',rows);result={'passed':all(r['status']=='PASS' for r in rows),'counts':dict(Counter(r['status'] for r in rows))}
            elif stage in ('protocol','smoke','matrix','challenge','e2e'):
                if args.network!='enabled':raise RuntimeError('external network disabled for this invocation')
                if stage!='protocol' and not gate(run):raise RuntimeError('real write matrix gate unmet: H/O/protocol must pass')
                if values is None:values=parse_key(args.key_file)
                if (run/'inherited_config.json').exists():
                    from ai.configuration import Configuration
                    expected=Configuration.clean(read(run/'inherited_config.json'))
                    actual=Configuration.clean({k:v for k,v in values.items() if k!='api_key'})
                    if expected!=actual:raise RuntimeError('configuration changed: inherited evidence cannot be continued under a new configuration')
                if stage=='protocol':result=protocol(run,values,budget)
                else:
                    from matrix import execute
                    cases=read(run/('challenge_manifest.json' if stage=='challenge' else 'cases_manifest.json'))
                    records=[];consecutive=0
                    if stage=='e2e':
                        from e2e import execute as eexecute
                        for case in read(run/'e2e_manifest.json'):
                            if (run/'e2e'/case['case_id']/'result.json').exists():continue
                            r=eexecute(case,run,fixtures,values,budget);records.append(r)
                            if r['raw_status']=='TEST_INVALID' or r.get('stop_batch'):
                                cp=read(run/'checkpoint.json');cp['stop_reason']=r.get('stop_batch','TEST_INFRASTRUCTURE');write(run/'checkpoint.json',cp);exit_code=2;break
                    else:
                        schedule=[(c,n) for n in (range(1,4) if stage=='matrix' else [1]) for c in cases if stage!='smoke' or c['case_id'] in SMOKE]
                        for case,n in schedule:
                            if (run/'cases'/case['case_id']/f'repeat_{n}'/'result.json').exists():continue
                            r=execute(case,n,run,fixtures,values,budget,stage);records.append(r)
                            consecutive=consecutive+1 if r.get('network_error') else 0
                            errors=[c.get('error','') for c in read(Path(r['evidence'])/'provider_calls.json')] if (Path(r['evidence'])/'provider_calls.json').exists() else []
                            hard=any(any(w in e for w in ('密钥无效','账户余额不足','没有访问权限','模型不存在','API_BUDGET_LIMIT','BATCH_TIME_LIMIT','SMOKE_API_LIMIT')) for e in errors)
                            if r.get('stop_batch') or consecutive>=3 or hard or r['raw_status']=='TEST_INVALID':
                                cp=read(run/'checkpoint.json');cp['stop_reason']=r.get('stop_batch') or ('AUTH_OR_MODEL' if hard else ('NETWORK_REPEATED' if consecutive>=3 else 'TEST_INFRASTRUCTURE'));write(run/'checkpoint.json',cp);exit_code=2;break
                    result={'passed':not exit_code,'executed_now':len(records),'review_required':True}
            elif stage=='review':result=review(run)
            elif stage=='report':result={'passed':True}
            else:raise RuntimeError('unknown stage')
            checkpoint(run,stage,result)
            if stage in ('selftest','offline','protocol') and result.get('passed') is False:
                cp=read(run/'checkpoint.json');cp['stop_reason']='GATE_'+stage.upper();write(run/'checkpoint.json',cp);exit_code=2;break
            if exit_code:break
    except Exception as exc:
        cp=read(run/'checkpoint.json');message=scrub(str(exc),values.get('api_key','') if 'values' in locals() and values else '')
        cp['stop_reason']=cp.get('stop_reason') or message;cp['last_error']=message;write(run/'checkpoint.json',cp)
        print('STOP_REASON='+cp['stop_reason'],flush=True);exit_code=2
    finally:
        path,summary=report(run)
        print('RUN_DIR='+str(run));print('SUMMARY='+str(run/'summary.json'));print('REPORT='+str(path))
        print('REMAINING='+str(210-summary['executed_matrix']-summary['executed_challenge']-summary['executed_e2e']))
        print('STOP_REASON='+str(summary['stop_reason']))
    return exit_code

if __name__=='__main__':raise SystemExit(main())
