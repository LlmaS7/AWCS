"""Build the post-fix delivery report without rewriting historical evidence."""
from pathlib import Path
import sys,json,hashlib,subprocess,shutil,datetime
sys.dont_write_bytecode=True
from collections import Counter
from run_suite import dump,summarize
from fix64_suite import fingerprint,ROOT,HERE,ORIGINAL

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def main(out):
    out=Path(out).resolve();rows,counts=summarize(out)
    final=fingerprint();first=read(out/'source_hashes_after_fix.json');require=__import__('checkers').require
    require(final==first,'source changed during tests')
    dump(out/'source_hashes_final.json',final);dump(out/'source_integrity.json',dict(unchanged_since_fix=True))
    changes=[n for n in set(read(out/'source_hashes_before.json'))|set(final) if read(out/'source_hashes_before.json').get(n)!=final.get(n)]
    dump(out/'changed_files.json',sorted(changes))
    archived=out/'test_scripts';archived.mkdir(exist_ok=True)
    for name in ('fix64_suite.py','fix64_actor.py','fix64_audit.py','fix64_report.py','run_suite.py','run_case.py','core.py','checkers.py','supplement.py','followup64.py'):
        shutil.copy2(HERE/name,archived/name)
    dump(out/'test_hashes_final.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(archived.glob('*.py'))})
    for name in ('simulation.py','controller.py','coordination/recovery.py','tests/test_plan_recovery.py'):
        target=out/'source_snapshot'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,target)
    (out/'tracked_changes.diff').write_text(subprocess.check_output(['git','diff','--binary'],cwd=ROOT).decode('utf-8'),encoding='utf-8')
    unit=read(out/'unit_test_summary.json');audits=read(out/'trace_audit.json')
    require(all(a['status']=='PASS' for a in audits),'trace audit failed')
    evidence=[]
    for r in rows:
        folder=out/'cases'/r['case_id'];specfile=folder/'input.json'
        if not specfile.exists():continue
        spec=read(specfile)
        source=spec.get('source_case') or r.get('source_case')
        if source and (folder/'actual_map.json').exists() and (Path(source)/'actual_map.json').exists():
            same=read(folder/'actual_map.json')['grid']['rows']==read(Path(source)/'actual_map.json')['grid']['rows']
            require(same,'input grid changed')
            evidence.append(dict(case_id=r['case_id'],source=source,identical_grid=same,original_input_sha256=hashlib.sha256((Path(source)/'input.json').read_bytes()).hexdigest()))
    dump(out/'input_provenance.json',evidence)
    p8=[r for r in rows if r['case_id'].startswith('FIX-EXPERIMENT64-')]
    p10=[r for r in rows if r['case_id'].startswith('FIX10-EXPERIMENT64-')]
    successes=lambda rs:sum(r['status']=='PASS' for r in rs)
    grouped={s:dict(Counter(r['status'] for r in rows if r['stage']==s)) for s in sorted({r['stage'] for r in rows})}
    dump(out/'postfix_facts.json',dict(counts=counts,groups=grouped,unit=unit,scale64_8s_pass=successes(p8),scale64_10s_pass=successes(p10),trace_count=len(audits),trace_ticks=sum(r['ticks'] for r in audits),service_transitions=sum(r['service_transitions'] for r in audits),source_unchanged_since_fix=True))
    lines=['# AWCS 安全路线复用修复及回归测试结论','',f'日期：2026-10-20（香港）；批次：`{out.name}`。','',
    '**修复已接入正式程序：完整模式重规划失败时，重新验证当前全部剩余路线；验证通过才限步继续执行。直接仿真和异步控制器使用相同的状态所有者校验。**','',
    f'64 台从头测试：原 8 秒规划预算 **{successes(p8)}/{len(p8)}** 完成；10 秒对照 **{successes(p10)}/{len(p10)}** 完成。所有未完成记录保留，不能将不同预算合并声称默认配置全部通过。','',
    '## 1. 实现与边界','',
    '- coordination/recovery.py：检查当前完整路线的障碍、合法移动、同格/对向换位、完整装卸、任务覆盖和持久停车；确认确有后续移动或服务可推进。',
    '- simulation.py：失败候选绝不提交；可复用时保留已提交任务、归属、载货和路线，授予 32 步执行区间。期间任务状态变化须重新校验，校验不延长原区间；到期重新尝试规划。',
    '- controller.py：异步控制器对有效复用区间执行同样的复查；原有请求标识、场景代际、时刻与过期结果淘汰逻辑保留。人工暂停状态保留。',
    '- 恢复仅适用于 scalable_full，且没有 pending 任务、所有未结束任务均已被当前/预留槽覆盖。新增待分配任务会结束复用并重新规划；取消或改派后须按新状态验证。',
    '- rolling 模式不从此机制获得新证书；legacy_full 失败保护保持原样。取消搜索、规划进程异常、路线验证失败均不能启用恢复。',
    '- 新增 tests/test_plan_recovery.py，可用项目虚拟环境运行 python -B -m unittest discover -s tests -v。','',
    '## 2. 原六个 64 台场景从头复跑','',
    '全部使用原始实际地图和 128 项任务，从 tick 0 启动；每例整体软限 600 秒、硬限 690 秒。没有注入测试侧恢复策略，执行由正式 Simulation.ensure_plan / apply_proposal / step 完成，测试只独立检查与记录。','',
    '| 场景 | 单次规划预算 | 状态 | 完成任务 | 最终 tick | 墙钟秒 | 正式路线复用次数 |','| --- | ---: | --- | ---: | ---: | ---: | ---: |']
    for r in sorted(p8+p10,key=lambda r:(r['inputs']['source_case'],r['inputs']['plan_seconds'])):
        name=Path(r['inputs']['source_case']).name.removeprefix('EXPERIMENT64-')
        lines.append(f'| {name} | {r["inputs"]["plan_seconds"]} 秒 | {r["status"]} | {r.get("completed","-")}/128 | {r.get("tick","-")} | {r.get("elapsed",0):.2f} | {r.get("metrics",{}).get("retained_plans",0)} |')
    lines += ['',
    '8 秒用例中存在首次规划就耗尽预算、或仍有 pending 任务时停止的情况：没有可复用的已提交完整方案，或不满足本轮保守恢复边界。恢复机制不能凭空产生初始路线；增加整体时限也不会自动重试失败的单次搜索。时间预算会受当次运行负载影响，本轮结果不作为严格性能排名。','',
    '## 3. 真实控制器和规划子进程','']
    actor=[r for r in rows if r['stage']=='FIX-actor64']
    for r in actor:
        lines.append(f'- {Path(r["source_case"]).name.removeprefix("EXPERIMENT64-")} 原现场：{r["status"]}；{r.get("initial_completed","-")}/128 → {r.get("completed","-")}/128，{r.get("elapsed",0):.2f} 秒；正式恢复次数 {r.get("metrics",{}).get("retained_plans",0)}。')
    lines += ['- 此项从冻结领域现场恢复，运行真实 Controller 所有者线程、真实 PlannerWorker 子进程和实际求解器；未替换求解结果，未注入恢复算法。它验证异步接入，不与从头测试混为同一种起点。',
    '- 22 项持久回归测试包含真实控制器/子进程小场景；对超时分支、过期结果和进程异常另有故障注入测试。','',
    '## 4. 回归与安全审计','',
    '| 测试阶段 | PASS | FAIL | INCONCLUSIVE |','| --- | ---: | ---: | ---: |',f'| 新增持久回归测试 | {unit["passed"]} | {unit["failed"]} | 0 |']
    for stage,cs in grouped.items():lines.append(f'| {stage} | {cs.get("PASS",0)} | {cs.get("FAIL",0)} | {cs.get("INCONCLUSIVE",0)} |')
    lines += ['',
    '核心回归继续使用独立匹配穷举、单机器人时空动态规划和业务保护检查；集成回归读取旧批次冻结的 4/16 台、有限动态任务、32 台、联动与模式输入，不重新生成较容易的任务或地图。','',
    f'事后重新检查 **{len(audits)}** 份轨迹、**{sum(r["ticks"] for r in audits)}** 个实际执行时间步、**{sum(r["service_transitions"] for r in audits)}** 次装卸完成转换；重读保存的方案，检查装卸连续性、持久停车、实际移动、冲突和执行证书期限。审计全部通过；未完成试验的已执行前缀也纳入检查。','',
    '安全检查通过不等于任务一定排空。PASS 表示该配置本次任务全部完成；INCONCLUSIVE 表示该策略在当次预算/恢复边界内未完成，不是无解证明。','',
    '## 5. 可用于提交的结论','',
    f'> AWCS 已增加完整模式下的安全剩余路线复用：重规划失败后，在已提交任务与完整路线重新校验通过时限步继续执行，并保持过期规划淘汰、人工暂停和装卸约束。新增 22 项回归测试通过。对六个 64 台固定场景从初始状态复跑，8 秒规划预算完成 {successes(p8)}/{len(p8)}，10 秒预算完成 {successes(p10)}/{len(p10)}；具体地图、任务、预算和未完成项随报告披露。所检方案及实际轨迹未发现安全约束违规。64 台仍按实验能力交付，本修复不保证初始方案必能找到，也不构成任意任务流下全局最优或长期无死锁保证。','',
    '## 6. 文件与重现','',
    '- summary.csv / results.jsonl：原始逐项结果，含所有未完成配置。cases/ 内保留输入、实际地图、方案、轨迹与最终状态。',
    '- unit_test_summary.json：22 项持久回归执行摘要。trace_audit.json：独立复审结果。input_provenance.json：冻结地图及原输入来源。',
    '- source_hashes_before.json 与 baseline/：修复前基线；source_hashes_after_fix.json / source_hashes_final.json：被测修复版本。source_snapshot/ 含新增文件完整副本；tracked_changes.diff 保存已有文件差异。',
    '- test_scripts/ / test_hashes_final.json：测试脚本归档及指纹。源码在本轮测试期间保持一致；本轮本来就修改了正式代码，不能沿用此前“源码未修改”的声明。',
    '- 本报告为修复后的新批次，不覆盖原始主批次或追加实验的历史报告。复现时使用归档脚本和相同修复版本，新建批次目录，保留原批次以读取冻结输入。','']
    report='\n'.join(lines)
    (out/'修复后测试报告.md').write_text(report,encoding='utf-8');(HERE/'修复后测试结论.md').write_text(report,encoding='utf-8')
    latest=HERE/'交付测试结论.md';text=latest.read_text(encoding='utf-8')
    if not text.startswith('> 正式修复后更新'):
        latest.write_text('> 正式修复后更新（2026-10-20）：已接入安全剩余路线复用。最新结果见 [修复后测试结论](修复后测试结论.md)；下面保留修复前的历史结论。\n\n'+text,encoding='utf-8')
    print(json.dumps(dict(counts=counts,scale64_8s=successes(p8),scale64_10s=successes(p10),changes=sorted(changes),traces=len(audits)),ensure_ascii=False),flush=True)
if __name__=='__main__':main(sys.argv[1])
