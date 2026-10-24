"""Build evidence-based follow-up report after all trials finish."""
from pathlib import Path
import sys,json,gzip,hashlib,shutil,subprocess,datetime
sys.dont_write_bytecode=True
from collections import Counter
from followup64 import dump,summarize,ROOT,HERE
from run_suite import hashes
from checkers import require

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def run(out):
    rows=summarize(out);rows=rows[0] if isinstance(rows,tuple) else rows
    if not isinstance(rows,list):rows=read(out/'results.json')
    rows=[read(p) for p in sorted((out/'cases').glob('*/result.json'))]
    require(len(rows)==19,'unfinished trial matrix')
    audits=read(out/'trace_audit.json');require(len(audits)==19 and all(r['status']=='PASS' for r in audits),'audit incomplete')
    old=out.parent/'20261020_144032_8fe978';originals=[read(p) for p in sorted((old/'cases').glob('EXPERIMENT64-*/result.json'))]
    counts=dict(Counter(r['status'] for r in rows));require(counts.get('FAIL',0)==0,'test failure requires adjudication')
    end=hashes();start=read(out/'source_hashes.json');oldhash=read(old/'source_hashes.json')
    integrity=dict(unchanged=start==end,unchanged_since_original_batch=oldhash==end,changed=[p for p in set(start)|set(end) if start.get(p)!=end.get(p)])
    require(integrity['unchanged'] and integrity['unchanged_since_original_batch'],'production source changed')
    dump(out/'source_integrity.json',integrity);dump(out/'source_hashes_final.json',end)
    provenance=[]
    for row in rows:
        folder=out/'cases'/row['case_id'];source=Path(row['source_case'])
        same=read(folder/'actual_map.json')['grid']['rows']==read(source/'actual_map.json')['grid']['rows']
        require(same,'frozen grid changed')
        provenance.append(dict(case_id=row['case_id'],original_input_sha256=sha(source/'input.json'),original_map_sha256=sha(source/'actual_map.json'),original_final_state_sha256=sha(source/'final_state.json'),identical_grid=True,result_sha256=sha(folder/'result.json')))
    dump(out/'provenance.json',provenance)
    scripts=out/'test_scripts_final';scripts.mkdir(exist_ok=True)
    names=['followup64.py','retention64.py','cold64.py','cold_recovery64.py','parking_diagnosis64.py','followup_evidence64.py','build_followup_report64.py','checkers.py','run_suite.py']
    for name in names:shutil.copy2(HERE/name,scripts/name)
    dump(out/'test_hashes_final.json',{p.name:sha(p) for p in sorted(scripts.glob('*.py'))})
    steps=sum(r.get('actual_steps_checked',0) for r in rows);plans=sum(r.get('plan_checks',0) for r in rows);points=sum(r.get('path_points_checked',0) for r in rows)
    attempts=[]
    for p in (out/'cases').glob('*/attempts.jsonl'):attempts.extend(json.loads(l) for l in p.read_text(encoding='utf-8').splitlines() if l.strip())
    witness=read(out/'feasibility_witness.json')
    facts=dict(trials=len(rows),statuses=counts,plan_checks=plans,actual_steps_checked=steps,path_points_checked=points,planning_attempts=len(attempts),service_transitions=sum(r['service_transitions'] for r in audits),source_integrity=integrity)
    dump(out/'followup_facts.json',facts)
    lines=['# AWCS：64 台未完成项目追加测试报告','',f'日期：2026-10-20；批次：`{out.name}`。原始批次：`{old.name}`。','',
    '**结论：六个原现场均已获得完成全部 128 项任务的安全续跑证据；其中两个使用原规划器的 8 秒预算，四个需要测试侧的安全路线后缀复用。两个代表性场景也已从初始状态完整跑通。恢复策略尚未集成正式程序，不能将以上结果写成“默认程序 64 台全部通过”。**','',
    '## 1. 追加试验范围与结果口径','',
    f'对原先六个未得结论的 64 台用例执行了 **{len(rows)} 次独立试验：PASS {counts.get("PASS",0)}、INCONCLUSIVE {counts.get("INCONCLUSIVE",0)}、FAIL {counts.get("FAIL",0)}**。这包括同一输入的不同策略、续跑及从头复跑，不能当作 19 个不同场景，也不与主批次 2029 项相加计算独立场景通过率。','',
    '延长后的续跑和恢复试验每次墙钟软限为 **600 秒**，父进程硬限为 660～690 秒；滚动窗口从头对照每次软限 240 秒。算法仍可能因搜索耗尽或单次预算不足提前停止，增加整体时限不会自动重试失败的规划。墙钟含检查与日志开销；续跑用时不含原始运行。','',
    '地图固定使用原批次 `actual_map.json`，64 台机器人、128 项任务、种子、任务优先级、取送点和装卸规则不变。没有重新生成更容易的地图，没有取消任务或降低安全要求。测试调用实际仿真、匹配、规划器与执行状态逻辑，不覆盖模型服务或图形界面。','',
    '## 2. 六个原现场的完成证据','',
    '| 原用例（省略 EXPERIMENT64-） | 原进度 | 成功续跑方式 | 最终进度 | 追加用时 | 最终 tick |','| --- | ---: | --- | ---: | ---: | ---: |']
    for oldrow in originals:
        cid=oldrow['case_id'];passed=[r for r in rows if r['source_case']==str(old/'cases'/cid) and r['status']=='PASS' and not r.get('reconstruction',{}).get('from_start')]
        # Compare resolved paths because source paths were written as absolute paths.
        if not passed:passed=[r for r in rows if Path(r['source_case']).name==cid and r['status']=='PASS' and not r.get('reconstruction',{}).get('from_start')]
        require(bool(passed),'missing successful continuation');r=passed[0]
        method='原规划器 8 秒；恢复后重规划' if r['strategy']=='adaptive' else '原规划器 8 秒续跑' if r['strategy']=='baseline8' else f'原规划器 10 秒＋安全后缀复用 {r["retentions"]} 次'
        lines.append(f'| {cid.removeprefix("EXPERIMENT64-")} | {oldrow["completed"]}/128 | {method} | {r["completed"]}/128 | {r["elapsed"]:.2f} 秒 | {r["tick"]} |')
    lines += ['',
    '两个内置大图的成功试验实际都只使用了 8 秒规划配置。2018 种子从原现场直接续跑会在下一次重规划停止；恢复后立即重新规划的另一次试验完成。恢复会重建距离缓存，并改变首次重规划时点；该结果说明允许恢复与更长运行可完成，不能严格归因为“仅增加总时限”。2019 种子直接续跑完成。','',
    '现场恢复核对全部机器人与任务的领域字段完全一致，包含位置、剩余路径、载货、服务倒计时、任务归属与时间戳。暂停标记在显式重试时清除，dirty 与 last_progress 按原终止状态/轨迹重建；这属于领域状态恢复，不是原进程的逐字节检查点。初始状态、恢复说明与最终状态均已保存。','',
    '## 3. 从初始状态复跑','',
    '| 场景 | 方法 | 结果 | 完成任务 | 墙钟 | 最终 tick | 后缀复用次数 |','| --- | --- | --- | ---: | ---: | ---: | ---: |']
    for r in rows:
        if not r.get('reconstruction',{}).get('from_start'):continue
        method='原程序 rolling，窗口 128 / 执行 16，10 秒' if r['strategy']=='fixed_rolling128' else '原规划器 10 秒＋测试侧后缀复用'
        lines.append(f'| {Path(r["source_case"]).name.removeprefix("EXPERIMENT64-")} | {method} | {r["status"]} | {r["completed"]}/128 | {r["elapsed"]:.2f} 秒 | {r["tick"]} | {r.get("retentions",0)} |')
    lines += ['',
    '这四次从头试验是两张代表性地图的两种策略对照。滚动窗口仍在原失败 tick 和进度停止；带恢复策略的两个完整流程均完成。其余四个原用例仅验证了冻结现场续跑，不宣称已完成六场景全部从头复跑，也不把各策略耗时作为严格的性能优劣排名。','',
    '## 4. 已尝试但未解决四个现场的方法','',
    '| 尝试 | 参数 | 四个冻结失败现场的结果 |','| --- | --- | --- |',
    '| 原配置重试 | scalable_full / off / 8 秒 | 均未形成新安全方案 |',
    '| 提高单次预算 | scalable_full / off / 10 秒 | 均未形成新安全方案 |',
    '| 占用估计联动 | estimated / 10 秒 | 均未形成新安全方案 |',
    '| 候选匹配联动 | candidate / 8 个候选上限 / 10 秒 | 均未形成新安全方案；实际无 pending 任务 |',
    '| 滚动规划 | 窗口 64 / 执行 8；窗口 128 / 执行 16；10 秒 | 均未形成新安全前缀 |',
    '| 低层求解器额外放宽 | 同一 SIPP 协调器 / 40 秒 | 均未形成新安全方案 |',
    '| 停车目标对照 | 正常重新计算 vs 临时保留原停车目标；缓存同样预热 | 两组均失败；本来就没有停车目标改变 |','',
    '正式 PlanningProfile 上限为 10 秒。40 秒试验通过测试代码直接调用同一低层求解器，明确属于外部实验，不能作为应用已有配置介绍。停车对照仅在一次调用内临时替换函数并立即恢复，未编辑生产文件。','',
    '## 5. 原因：已有方案可行，但重规划未能重建','',
    '四个冻结现场均没有 pending 任务，重新 dispatch 后任务归属、状态以及所有停车目标均未变化。当前剩余路线通过独立几何/业务检查，也通过生产 validate_itineraries 的完整装卸及持久停车检查；路线长度在默认完整搜索时域以内：','',
    '| 场景 | 当前完整后缀最长步数 | 默认规划时域 | 独立检查 | 生产检查 |','| --- | ---: | ---: | --- | --- |']
    for w in witness:lines.append(f'| {w["case_id"].removeprefix("EXPERIMENT64-")} | {w["max_path_steps"]} | {w["production_horizon"]} | PASS | PASS |')
    lines += ['',
    '因此，这四个状态有明确可行解证据，不是地图无解、任务归属改变或停车重新匹配造成。生产代码在任务完成后触发重规划；64 台使用有限优先顺序的 SIPP 预约协调和局部冲突修复，没有全局完备性保证。搜索返回 timeout 或 ordering_exhausted 后，执行层暂停，未继续使用仍合法的旧方案。rectangle-2018 即使给低层 40 秒，仍约 4.41 秒就枚举耗尽，证明该例不能只靠增加墙钟解决。','',
    '该发现定位的是多机器人重规划搜索覆盖与失败恢复能力；不能据此指认单机器人 SIPP 搜索错误，也不说明任务分配的匹配最优性验证失效。原先安全暂停确实阻止了未验证方案执行，但不足以保证任务排空。','',
    '## 6. 成功的恢复策略及适用边界','',
    '测试代码先正常请求 10 秒完整规划。若失败，则重新验证当前全部剩余路线：覆盖所有机器人、按当前装卸倒计时完成全部剩余作业、结束后持续停车、无障碍穿越、无同格或对向换位冲突。确认仍有移动或服务可推进后，复用最多 32 个时间步，再尝试原规划器；期间遇到作业完成也重新检查剩余路线。','',
    '四次现场续跑分别复用 2、2、4、4 次；两个从头试验的实际次数见表。没有降低优先级、改变任务、清空载货或移动机器人“解堵”。实验脚本另备有固定空闲停车目标的分支，但所有成功恢复试验均未调用该分支，stable_parking_attempts=0。','',
    '**这是一项测试侧执行策略验证，尚未写入正式程序。** 当前验证针对静态地图与固定任务批；若用户改图、强制改派、注入新任务或业务规则变化，必须按新状态重新认证路线，不能直接套用本次成功结论。','',
    '## 7. 安全证据、源码与统计','',
    f'- 本次 {len(rows)} 次试验共核验 {plans} 次方案/后缀，{steps} 个实际时间步，{points} 个路线或位置样本（包含重复检查，不能视为独立轨迹点）。',
    f'- 事后重新读取 {len(audits)} 份轨迹，核验 {sum(r["service_transitions"] for r in audits)} 次装卸完成转换；核对逐步移动、冲突、装卸驻留与完成时间戳，全部通过。零步停止用例也核对轨迹长度为零。',
    '- PASS 要求 128 项任务全部完成，且执行检查通过；INCONCLUSIVE 表示该策略预算内未排空任务，不作为安全违规或无解证明。未发现被检查方案与实际执行的安全违规。',
    '- 生产 Git 跟踪文件的 SHA-256 与原主批次、本次开始时一致，Git 工作区干净。全部改动与产物仅在已忽略的 .temp/testing 内。原始主批次报告与原始结果未覆盖。',
    '- 一个恢复脚本初次启动时出现测试变量未导入，发生于任何用例启动前；已修正并完整执行，retention_preflight_note.txt 留档，不计入生产失败。','',
    '## 8. 可用于项目提交的测试结论','',
    '> AWCS 在固定版本与所测地图、任务和预算下，通过了任务分配及路径安全的核心验证；4/16 台的 28 个主场景、32 台的 8 个目标规模场景均完成。针对 64 台原先未完成的六个现场，追加试验均取得 128/128 项任务完成的安全续跑证据：两个沿用原规划器的 8 秒预算，四个借助测试侧安全剩余路线复用；其中两个代表性场景也从初始状态完成。追加检查未发现所检路线及执行轨迹的冲突或装卸约束违规。64 台仍属于实验范围，默认程序尚存在重规划失败后的恢复限制，恢复策略尚未集成，不能宣称默认程序在全部 64 台场景中稳定通过，也不构成任意任务流下的全局最优或长期无死锁保证。','',
    '## 9. 交付文件与复现','',
    '- summary.csv、results.json：19 次试验原始结论，保留所有未完成策略。',
    '- cases/<case_id>/：input、初始/最终状态、实际地图、规划尝试、压缩方案与逐步轨迹。',
    '- parking_diagnosis.json：四现场任务/停车目标变化与 A/B 结果；feasibility_witness.json：已有可行方案和搜索时域证据。',
    '- trace_audit.json、followup_facts.json：轨迹复审与汇总统计；source_integrity.json、provenance.json：源码、地图与来源可追溯性。',
    '- test_scripts_final/、test_hashes_final.json：本次测试脚本归档与哈希。环境与原任务清单可追溯到 environment.json、source_cases.json 和原始批次。','',
    '复现时新建 runs 下的独立批次目录，禁止覆盖此批次。原规划策略矩阵入口为 followup64.py；四个现场恢复入口为 retention64.py；两张代表图从头对照入口为 cold64.py 与 cold_recovery64.py。所有入口使用项目虚拟环境，保留原始批次以读取冻结输入；恢复脚本输出属于实验结果。通过时间预算控制的搜索会随机器负载变化，复现应核对任务完成与安全判据，不要求路径或耗时逐项相同。','',
    '建议后续工程修正集中于：在任务与地图修订一致时，认证并保留可行方案，在重规划失败时有界继续执行；再对动态任务、改图、强制派单和滚动证书失效做回归。本次未实施该生产改动。']
    report='\n'.join(lines)+'\n';(out/'64台追加测试报告.md').write_text(report,encoding='utf-8');(HERE/'64台追加测试结论.md').write_text(report,encoding='utf-8')
    delivery=HERE/'交付测试结论.md';text=delivery.read_text(encoding='utf-8')
    if not text.startswith('> 64 台追加测试更新'):
        prefix=f'> 64 台追加测试更新（2026-10-20）：六个原现场均有 128/128 完成的安全续跑证据；两个沿用原规划器，四个依靠尚未集成的测试侧安全后缀复用，两个代表图从头复跑也通过。原程序默认 64 台能力仍按实验范围交付。详见 [64 台追加测试结论](64台追加测试结论.md)，原始主批次记录保留如下。\n\n'
        delivery.write_text(prefix+text,encoding='utf-8')
    print(json.dumps(facts,ensure_ascii=False),flush=True)
if __name__=='__main__':run(Path(sys.argv[1]).resolve())
