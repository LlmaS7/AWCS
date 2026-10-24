from pathlib import Path
import sys,json,hashlib,csv,gzip,shutil,datetime,statistics
from collections import Counter
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from run_suite import hashes,summarize


def make_report(out):
    out=Path(out)
    raw_rows,raw_counts=summarize(out)
    adjudications=json.loads((out/'adjudications.json').read_text(encoding='utf-8')) if (out/'adjudications.json').exists() else {}
    indexed={r['case_id']:r for r in raw_rows}
    resolved={}
    for cid,judgment in adjudications.items():
        original=indexed.get(cid,{})
        replacement=indexed.get(judgment.get('resolved_by'),{})
        if judgment.get('classification')=='HARNESS_ERROR' and original.get('status')=='FAIL' and original.get('error','').startswith('UnicodeDecodeError:') and replacement.get('status')=='PASS':
            resolved[cid]=judgment
    rows=[r for r in raw_rows if r['case_id'] not in resolved]
    counts=Counter(r['status'] for r in rows)
    (out/'accepted_results.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,default=str)+'\n' for r in rows),encoding='utf-8')
    with (out/'验收结果.csv').open('w',encoding='utf-8-sig',newline='') as f:
        fields=['case_id','stage','status','elapsed','completed','total','tick','plan_checks','actual_steps_checked','path_points_checked','terminal','error']
        writer=csv.DictWriter(f,fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    summary_path=out/'summary.md'
    summary_path.write_text('> 本页为全部原始记录，含 '+str(len(resolved))+' 条已修复并重测通过的测试夹具编码错误。有效验收结果见 交付测试报告.md、验收结果.csv 和 adjudications.json。\n\n'+summary_path.read_text(encoding='utf-8'),encoding='utf-8')
    require_unique=len({r['case_id'] for r in rows})==len(rows)
    env=json.loads((out/'environment.json').read_text(encoding='utf-8'))
    hardware=json.loads((out/'hardware.json').read_text(encoding='utf-8')) if (out/'hardware.json').exists() else {}
    baseline=json.loads((out/'source_hashes.json').read_text(encoding='utf-8'))
    current=hashes();unchanged=baseline==current
    digest=hashlib.sha256(json.dumps(baseline,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    (out/'source_hashes_end.json').write_text(json.dumps(current,indent=2),encoding='utf-8')
    (out/'source_integrity.json').write_text(json.dumps(dict(unchanged=unchanged,changed=[p for p in set(current)|set(baseline) if current.get(p)!=baseline.get(p)]),indent=2),encoding='utf-8')
    snapshots=out/'test_scripts';snapshots.mkdir(exist_ok=True)
    for path in HERE.glob('*.py'):shutil.copy2(path,snapshots/path.name)
    shutil.copy2(HERE/'README.md',snapshots/'README.md')
    (out/'test_hashes_final.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in snapshots.glob('*.py')},indent=2),encoding='utf-8')
    maps=out/'maps';maps.mkdir(exist_ok=True)
    for path in (HERE/'datasets/maps').glob('*.json'):shutil.copy2(path,maps/path.name)
    for name in ('fleet_64x64','irregular_96x64','experimental_128x96'):
        source=HERE.parents[1]/'maps'/(name+'.json');shutil.copy2(source,maps/source.name)
    completed=[r for r in rows if r.get('tasks_completed')]
    main=[r for r in rows if r['stage']=='P4-main']
    scale32=[r for r in rows if r['stage']=='P6-32']
    scale64=[r for r in rows if r['stage']=='P6-64']
    failures=[r for r in rows if r['status']=='FAIL']
    uncertain=[r for r in rows if r['status'] in ('INCONCLUSIVE','BLOCKED','NOT_RUN')]
    checked=[r for r in rows if r.get('actual_steps_checked') is not None]
    plans=sum(r.get('plan_checks',0) for r in rows)
    ticks=sum(r.get('actual_steps_checked',0) for r in rows)
    positions=sum(r.get('path_points_checked',0) for r in rows)
    audited=[r for r in rows if r['stage']=='TRACE-audit']
    transitions=sum(r.get('details',{}).get('service_transitions_checked',0) for r in audited)
    groups={stage:Counter(r['status'] for r in rows if r['stage']==stage) for stage in sorted({r['stage'] for r in rows})}
    primary_ok=len(main)==28 and all(r['status']=='PASS' for r in main) and not failures and unchanged and require_unique
    outcome='主流程通过，扩展项存在未完成结果' if primary_ok and uncertain else ('本次限定测试范围通过' if primary_ok else '未达到整体通过条件')
    text=['# AWCS 交付测试报告','',f'测试日期：{datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d")}（香港时间）',f'批次：`{out.name}`','',
          f'**测试结论：{outcome}。**','',
          f'本批次有效验收 **{len(rows)}** 个用例：通过 **{counts.get("PASS",0)}**、失败 **{counts.get("FAIL",0)}**、未得结论 **{counts.get("INCONCLUSIVE",0)}**、阻塞 **{counts.get("BLOCKED",0)}**、未运行 **{counts.get("NOT_RUN",0)}**。各用例 ID '+('无重复。' if require_unique else '存在重复，需复核。'),
          '',f'原始日志保留 {len(raw_rows)} 条记录，其中 {len(resolved)} 条为已修复并重测通过的测试夹具编码错误，按 adjudications.json 的对应关系替换后得到以上有效验收数量；原始错误未删除，不计为生产缺陷。', '',f'主地图集 **{sum(r["status"]=="PASS" for r in main)}/28** 完成预设搬运任务。32 台范围 **{sum(r["status"]=="PASS" for r in scale32)}/{len(scale32)}**；64 台实验范围 **{sum(r["status"]=="PASS" for r in scale64)}/{len(scale64)}**。这些范围分开验收。','',
          f'测试期间生产文件指纹'+('保持一致，未修改算法、正式地图、配置或运行输出。' if unchanged else '出现变化，必须先复核版本。'),
          '', '## 1. 版本与环境','',
          f'- Git 提交：`{env["commit"]}`；开始时工作区：`{env["git_status"].strip() or "干净"}`。',
          f'- 完整被测文件清单及 SHA-256：`source_hashes.json`；集合指纹：`{digest}`。',
          f'- Python：`{env["python"].splitlines()[0]}`。',f'- 系统：`{env["platform"]}`；CPU：{hardware.get("cpu",env["processor"])}，{hardware.get("cores","未知")} 核 / {env["cpu_count"]} 逻辑处理器；内存 {hardware.get("physical_memory_gib","未知")} GiB。',
          '- 使用项目虚拟环境，串行执行规划用例；关闭测试字节码写入，未接入模型服务或启动图形界面。',
          '- 生产算法与业务规则在测试前后保持原样；测试代码和所有产物存放于 `.temp/testing/`。',
          '', '## 2. 方法与证据可信度','',
          '1. 匹配采用独立递归穷举，按任务等级、偏好、ETA 与创建时刻的未编码目标元组比较；同分匹配允许不同。另用列排列穷举检查匈牙利实现。',
          '2. SIPP 使用独立逐时间步动态规划对照，覆盖显式位置/边预约、连续服务、交付代价与停车；对照器不调用生产搜索、预约补集或生产冲突检查。',
          '3. 小型多机器人夹具采用独立联合状态 BFS；完整仿真对每个接收计划及实际执行步再次检查同格、对向换位、穿越障碍、非法移动、服务连续性与业务归属。',
          '4. 实际轨迹以压缩 JSONL 流式保存，并在主批次结束后重新读取审计服务倒计时与装卸时间戳。',
          '5. 独立检查器先通过正常样本及人工注入错误的自检，避免只凭生产 collisions 计数或搜索成功标记下结论。',
          '', '## 3. 分阶段结果','', '| 阶段 | PASS | FAIL | INCONCLUSIVE | BLOCKED / NOT_RUN |','| --- | ---: | ---: | ---: | ---: |']
    for stage,c in groups.items():text.append(f'| {stage} | {c.get("PASS",0)} | {c.get("FAIL",0)} | {c.get("INCONCLUSIVE",0)} | {c.get("BLOCKED",0)+c.get("NOT_RUN",0)} |')
    text += ['', '其中：', '', '- 匹配随机对照 1,200 例，覆盖 0～4 个机器人槽位、0～5 个任务；包括空集合边界，不将这些输入计为大规模实测。',
             '- 单机器人 SIPP 对照 300 例：200 例基本时空预约，100 例含障碍和多个交付作业点。',
             '- 匈牙利矩阵对照 120 例，另含非法形状拒绝与固定业务反例。',
             '- 小型联合状态对照 3 个固定夹具和 20 个随机两机器人夹具。',
             '- 七种生成轮廓 × 两个种子形成 14 张主集地图；每张重复生成核对一致性，另检查内置 9 张地图。',
             '', '## 4. 完整搬运与安全检查','',
             f'已完成搬运的集成用例累计完成 **{sum(r.get("completed",0) for r in completed)}** 项任务；未完成用例的局部进度不计入此完成总数。',
             f'主批次共记录 **{plans}** 次计划检查、**{ticks}** 个实际执行时间步、**{positions}** 个路线/位置样本检查（含计划样本与两时刻执行检查，存在按检查次数重复计数）。',
             f'完成了 **{len(audited)}** 份执行轨迹的后续审计，核对 **{transitions}** 次装卸完成转换。',
             '', '| 范围 | 用例数 | 完成通过 | 每例任务 | 规划预算 |','| --- | ---: | ---: | --- | --- |']
    for stage,label,budget in [('P4-main','生成主集 4 / 16 台','3 秒'),('P4-dynamic','16 台有限动态流','3 秒'),('P6-32','32 台目标规模','3 秒'),('P6-64','64 台实验规模','8 秒')]:
        selected=[r for r in rows if r['stage']==stage]
        tasknums=sorted({r.get('scheduled',len(r.get('inputs',{}).get('tasks',[]))) for r in selected})
        text.append(f'| {label} | {len(selected)} | {sum(r["status"]=="PASS" for r in selected)} | {" / ".join(map(str,tasknums))} | {budget} |')
    text += ['', '任务时长单位为仿真时间步，距离单位为网格；规划预算是算法参数，不是每例完整运行总耗时。主集每例硬时限 90 秒，动态流与 32 台为 120 秒，64 台为 180 秒；用例墙钟包含独立检查与日志开销。超时或安全暂停未完成，表示在本次预算下未排空任务，不代表数学无解。实际参数、时间与结果见 summary.csv 和 cases 下的原始 JSON。',
             '', '## 5. 未完成、失败与修正记录','']
    if failures or uncertain:
        text += ['| 用例 | 状态 | 说明 |','| --- | --- | --- |']
        for r in failures+uncertain:text.append(f'| {r["case_id"]} | {r["status"]} | {str((r.get("terminal", "")+"; "+str(r.get("completed","未知"))+"/"+str(r.get("total","未知"))+" tasks; "+str(r.get("error") or r.get("message") or r.get("reason",""))))[:300]} |')
    else:text.append('主批次与补充测试没有生产缺陷失败或未完成用例。')
    text += ['', '首轮批次 `20261020_144003_64ae11` 有一处重复归属注入夹具未真正制造重复归属，属于测试夹具问题。修正只涉及测试代码，原始结果及 fixture_correction.md 已保留；本报告所用主批次完整重跑核心测试通过。该首轮不与本批次重复累计。',
             '', '此外，本批次修正了测试代码在 Windows 下读取 UTF-8 地图时使用默认 GBK 的问题：真实进程夹具 1 项、独立静态审计 16 项，共 17 条原始错误。全部受影响项均使用相同断言重测通过，映射关系和原始记录保存在 adjudications.json、results.jsonl 与 test_scripts_initial/。仅修正测试读取编码，未修改生产程序。', '', '## 6. 交付适用范围','',
             '- 本报告适用于上述源码指纹、冻结地图、任务清单、机器人数量和时间预算下的仓储仿真。',
             '- 任务分配的最优性结论限定于给定匹配子问题；不表示未来任务流及所有路径的联合全局最优。',
             '- 通过静态检查或有限任务批不能证明任意任务流长期无死锁、无饥饿；规划器仍允许在预算不足时安全暂停。',
             '- 64 台和滚动窗口继续按实验能力交付；即使有限测试通过，也不改称通用性能保证。',
             '- 工坊原有 probe 是补充证据，复用生产检查，未与独立校验混为一种判据。',
             '- 本轮未验证实体机器人控制、真实库存、大模型语义准确率、外部模型服务、桌面 3D 渲染或长期生产运行。',
             '- legacy_full 使用其实现内的独立搜索预算，不能仅凭相同 profile.seconds 就作为与默认模式的严格等预算性能对比。',
             '', '## 7. 可直接用于提交材料的结论','']
    if primary_ok:
        text += [f'> AWCS 在本次固定版本和测试条件下，通过了任务分配、路径规划与执行保护的核心验证。七类生成布局的 28 个 4/16 台搬运场景全部完成，32 台目标规模的 {sum(r["status"]=="PASS" for r in scale32)}/{len(scale32)} 个场景完成。匹配结果与独立穷举一致，SIPP 经独立时空对照，已检查的返回路线及实际轨迹未发现冲突或业务约束违规。'+('64 台等扩展存在未完成项，按本报告单独披露；' if uncertain else '64 台及实验模式结果另列；')+'结论适用于所测地图、任务和预算，不代表任意任务流下的全局最优或长期无死锁保证。']
    else:text += ['> 本轮发现尚未满足的验收项，不宜表述为整体测试通过。请按第 5 节处理失败或版本问题，并重新执行受影响测试。']
    text += ['', '## 8. 交付文件与重现','',
             '- 验收结果.csv / accepted_results.jsonl：依据已核实夹具修正记录形成的有效验收结果。summary.csv / results.jsonl：保留所有原始记录，包含已被重测替换的夹具错误；adjudications.json 解释对应关系。',
             '- source_hashes.json / source_integrity.json：被测版本和测试前后一致性。',
             '- test_scripts/ / test_hashes_final.json：本次测试源码归档与指纹。',
             '- maps/：生成图和规模测试内置地图归档；cases/<用例>/actual_map.json 是实现种子障碍后的实际网格。',
             '- cases/<用例>/input.json / result.json / final_state.json：输入、结论、最终现场。',
             '- cases/<用例>/plans.jsonl.gz / trace.jsonl.gz：返回路线与逐步执行轨迹。',
             '- counterexamples/：出现断言失败时保存的反例。首轮夹具修正记录保留在首轮目录。',
             '- 复现：参阅测试根目录 README.md，使用当前测试入口生成新批次，或用 replay_case.py 读取一个已归档输入；不要覆盖原始运行结果。',
             '', '本报告不包含未经执行的通过结论。']
    report='\n'.join(text)+'\n'
    (out/'交付测试报告.md').write_text(report,encoding='utf-8')
    (HERE/'交付测试结论.md').write_text(report,encoding='utf-8')
    facts=dict(run=str(out),counts=dict(counts),raw_counts=dict(raw_counts),resolved_harness_errors=len(resolved),source_unchanged=unchanged,source_fingerprint=digest,primary_passed=primary_ok,unique_case_ids=require_unique,completed_tasks=sum(r.get('completed',0) for r in completed),plan_checks=plans,execution_ticks=ticks,position_samples=positions,trace_audits=len(audited),service_transitions=transitions,verdict=outcome)
    (out/'delivery_facts.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(facts,ensure_ascii=False,indent=2))

if __name__=='__main__':make_report(sys.argv[1])