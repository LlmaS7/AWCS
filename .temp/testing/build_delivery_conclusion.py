"""Produce a submission conclusion restricted to fleets of at most 32 robots."""
from pathlib import Path
from collections import Counter
import json,csv,shutil,datetime,re
HERE=Path(__file__).resolve().parent
out=Path((HERE/'fix64_active.txt').read_text(encoding='utf-8'))
root=HERE.parents[1]
allowed={'P0','P1','P2','P3','P4-main','P4-dynamic','P5','P5-process','P6-32','P6-coupling','P6-mode'}
rows=[json.loads(l) for l in (out/'results.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
rows=[r for r in rows if r['stage'] in allowed]
assert all((r['inputs'] if isinstance(r.get('inputs'),dict) else {}).get('robots',0)<=32 for r in rows)
assert not any(re.search(r'EXPERIMENT64|ACTOR64',r['case_id']) for r in rows)
ids={r['case_id'] for r in rows}
audit=[r for r in json.loads((out/'trace_audit.json').read_text(encoding='utf-8')) if r['case_id'] in ids]
assert all(r['status']=='PASS' for r in audit)
counts=Counter(r['status'] for r in rows)
assert (len(rows),counts['PASS'],counts['INCONCLUSIVE'],len(audit))==(1767,1762,5,50)
delivery=out/'delivery_32';delivery.mkdir(exist_ok=True)
backup=HERE/'history'/('conclusion_'+datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y%m%d_%H%M%S'));backup.mkdir(parents=True)
for name in ('交付测试结论.md','修复后测试结论.md'):
    if (HERE/name).exists():shutil.copy2(HERE/name,backup/name)

def dump(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
def link(label,path):return f'[{label}](<{path.resolve().as_posix()}>)'

with (delivery/'验收结果.jsonl').open('w',encoding='utf-8') as f:
    for row in rows:f.write(json.dumps(row,ensure_ascii=False)+'\n')
fields=['case_id','stage','status','completed','total','tick','elapsed','terminal','error']
with (delivery/'验收结果.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
dump(delivery/'轨迹审计.json',audit)
groups={stage:dict(Counter(r['status'] for r in rows if r['stage']==stage)) for stage in sorted(allowed)}
dump(delivery/'范围统计.json',dict(max_robots=32,records=len(rows),counts=dict(counts),groups=groups,unit_tests=25,traces=len(audit),trace_ticks=sum(r['ticks'] for r in audit),plans=sum(r['plans'] for r in audit),service_transitions=sum(r['service_transitions'] for r in audit)))
lines=['# AWCS 交付测试结论（最多 32 台）','',
'测试日期：2026-10-20（香港时间）。本报告覆盖任务分配、路径规划、执行保护及 4、16、32 台配置，规模上限为 32 台。','',
'**结论：核心正确性检查和 4/16 台主场景通过；32 台及有限动态任务场景存在预算内未完成项，按实际结果单独披露。**','',
'## 1. 范围与汇总','',
'本范围内记录 **1,767 项检查：1,762 项通过、0 项断言失败、5 项未完成**；另有最终版本的 **25 项针对性回归测试全部通过**。检查记录不等同于独立业务场景数，重复进程联通检查不用于扩大场景覆盖率。','',
'| 范围 | 完成通过 | 未完成 | 单次规划预算 |','| --- | ---: | ---: | --- |',
'| 4/16 台生成地图主场景 | 28/28 | 0 | 3 秒 |',
'| 16 台有限动态任务流 | 1/3 | 2 | 3 秒 |',
'| 32 台规模场景 | 5/8 | 3 | 3 秒 |',
'| 联动方式对照（4 台） | 9/9 | 0 | 3 秒 |',
'| 完整旧模式与滚动模式（4 台） | 2/2 | 0 | 按各模式实现 |','',
'32 台每例包含 64 项搬运任务；动态流每例包含 60 项任务。规划预算是单次搜索参数，与整例运行时限不同。旧模式使用实现内的搜索预算，不作为严格等预算性能对照。','',
'## 2. 核心检查与修复验证','',
'**1,715 项核心检查全部通过**，包括独立穷举对照任务匹配、单机器人时空动态规划对照、预约与路线检查、任务归属和执行保护。结论限定于所测输入；匹配子问题的最优性不等于任务流与全部路径的联合全局最优。','',
'最终版本新增的 25 项回归覆盖：完整剩余路线复核、32 步执行区间到期、重查不延长期限、新增任务、强制改派、取消与紧急升级、地图阻塞、载货与连续装卸、过期规划结果、进程异常、人工暂停和规划模式切换。真实控制器与独立规划进程的小场景检查通过。','',
'修复仅在完整模式、没有待分配任务且当前全部剩余路线校验通过时启用。验证失败仍暂停；滚动模式不通过此机制获得新的执行证书。','',
'## 3. 路线与实际执行审计','',
f'本报告范围内重新审计 **{len(audit)} 份轨迹、{sum(r["ticks"] for r in audit):,} 个实际执行时间步、{sum(r["plans"] for r in audit):,} 份记录方案和 {sum(r["service_transitions"] for r in audit):,} 次装卸完成转换**。','',
'所检方案及实际执行未发现穿越障碍、非法移动、同格冲突、对向换位、装卸中移动或越过执行证书期限的情况。未完成用例已执行的前缀也纳入审计。安全检查通过表示所检路线与执行符合约束，不表示任务必定排空。','',
'## 4. 未完成项与补充对照','',
'以下为本轮初次回归记录，不用补跑结果替换：','',
'| 场景 | 机器人数量 | 完成任务 | 最终时间步 |','| --- | ---: | ---: | ---: |']
for r in rows:
    if r['status']=='PASS':continue
    n=(r['inputs'] if isinstance(r.get('inputs'),dict) else {})['robots']
    lines.append(f'| {r["case_id"].removeprefix("FIX-")} | {n} 台 | {r["completed"]}/{r["total"]} | {r["tick"]} |')
lines += ['',
'五项均在当次规划预算内未形成新方案而安全停止，未触发成功的路线复用。INCONCLUSIVE 表示当次配置未完成任务，不是数学无解证明，也不等同于发生碰撞或业务约束违规。','',
'| 相同输入的补充对照 | 修复前代码 | 修复代码 |','| --- | --- | --- |']
controls=json.loads((out/'baseline_controls_summary.json').read_text(encoding='utf-8'))
assert len(controls)==5
for c in controls:
    a,b=c['before'],c['after']
    lines.append(f'| {c["case_id"]} | {a["status"]}，{a["completed"]}/{a["total"]} | {b["status"]}，{b["completed"]}/{b["total"]} |')
lines += ['',
'动态用例对修复前后代码各补跑一次；规模用例保留本轮修复代码记录，另补跑修复前代码。对照显示存在预算与搜索结果波动；一次补跑完成不作为稳定性保证。本报告保留全部初次未完成项，不宣称整体全部通过。','',
'## 5. 可用于项目提交的结论','',
'> AWCS 在最多 32 台的测试范围内，通过了 1,715 项任务分配、路径规划与执行保护核心检查，以及最终版本的 25 项针对性回归测试。4/16 台的 28 个主场景全部完成；32 台规模场景完成 5/8，有限动态任务流完成 1/3，其余用例在规划预算内安全停止，已单独披露。范围内 50 份轨迹复审未发现所检路线及执行的冲突、装卸或证书约束违规。结论适用于所测版本、地图、任务和预算，不代表任意任务流下的全局最优、长期无死锁或所有配置均能完成。','',
'## 6. 证据与版本','',
'- '+link('本范围验收结果 CSV',delivery/'验收结果.csv')+'；'+link('逐项 JSONL',delivery/'验收结果.jsonl')+'。',
'- '+link('范围内轨迹审计',delivery/'轨迹审计.json')+'；'+link('范围统计',delivery/'范围统计.json')+'。',
'- '+link('最终 25 项回归日志',out/'cleanup_unittest.stderr.txt')+'；'+link('修复前后补充对照',out/'baseline_controls_summary.json')+'。',
'- '+link('矩阵测试版本指纹',out/'source_hashes_after_fix.json')+'；'+link('最终代码版本指纹',out/'source_hashes_cleanup.json')+'；'+link('收尾差异说明',out/'cleanup_integrity.json')+'。','',
'矩阵与轨迹审计完成后，最终版本补充了正常规划成功时的状态提示更新，以及直接切换旧模式后的执行期限清理；新增对应回归，最终为 25/25 通过。收尾没有修改任务匹配、路径搜索及完整路线复用算法。原始逐项日志与历史报告保留，交付范围以本报告及筛选后的验收记录为准。','',
'测试通过项目虚拟环境运行，未接入外部模型服务；本结论不覆盖模型语义准确率、实体机器人控制或长期生产运行。']
text='\n'.join(lines)+'\n'
assert not re.search(r'64\s*台|P6-64|ACTOR64|EXPERIMENT64|128/128',text)
for p in (HERE/'交付测试结论.md',HERE/'修复后测试结论.md',delivery/'交付测试报告.md'):p.write_text(text,encoding='utf-8')
print(json.dumps(dict(updated=['交付测试结论.md','修复后测试结论.md'],max_robots=32,counts=dict(counts),traces=len(audit),ticks=sum(r['ticks'] for r in audit)),ensure_ascii=True))
