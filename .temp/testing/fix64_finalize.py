from pathlib import Path
import sys,json,hashlib,shutil
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def main(out):
    out=Path(out).resolve();text=(out/'修复后测试报告.md').read_text(encoding='utf-8')
    facts=read(out/'postfix_facts.json');groups=facts['groups'];controls=read(out/'baseline_controls_summary.json')
    count=lambda stage:groups.get(stage,{}).get('PASS',0)
    quote=f'> AWCS 已接入完整模式下的安全剩余路线复用，并通过 25 项针对性回归及 1,715 项核心检查。四个原 64 台停滞现场均通过真实控制器与规划子进程恢复至 128/128；从初始状态测试时，8 秒和 10 秒预算均完成 2/6，仍有早期搜索未完成项。4/16 台主集完成 {count("P4-main")}/28，32 台本轮完成 {count("P6-32")}/8，有限动态流完成 {count("P4-dynamic")}/3；未完成项与修复前对照单独披露。已审计的方案和实际轨迹未发现冲突或装卸约束违规。本轮未达到所有配置通过，64 台及预算敏感场景仍按实验范围交付，不保证任意任务流下全局最优或长期无死锁。'
    old=next(l for l in text.splitlines() if l.startswith('> AWCS'))
    text=text.replace(old,quote)
    lines=['','## 8. 未完成回归项的修复前对照','',
    '额外对照直接在独立进程中加载本批次 baseline/simulation.py，任务匹配、搜索与校验模块保持相同。读取同一冻结地图、任务清单与 3 秒规划预算，未编辑正式源文件。动态用例对原代码和当前代码各补跑一次；32 台对照读取本轮矩阵作为当前代码结果，另补跑原代码。表中补跑结果不替换或删除初次矩阵的未完成项。','',
    '| 场景 | 原代码对照 | 完成任务 | 修复代码对照 | 完成任务 |','| --- | --- | ---: | --- | ---: |']
    for r in controls:lines.append(f'| {r["case_id"]} | {r["before"]["status"]} | {r["before"].get("completed","-")}/{r["before"].get("total","-")} | {r["after"]["status"]} | {r["after"].get("completed","-")}/{r["after"].get("total","-")} |')
    lines += ['',
    '初次矩阵中上述五项均没有触发成功的安全路线复用（retained_plans 为零或未设置）。对照只陈述该次预算下的实际结果，不将一次补跑通过作为稳定性保证，也不把一次超时当作数学无解。具体耗时、末态与逐步独立检查见 baseline_controls/ 和 baseline_controls_summary.json。','',
    '下一步应针对首次规划和仍有待分配任务时的预算分配、搜索顺序及增量规划做独立改进与验证；本次保守恢复策略不会绕过 pending 任务调度，也没有放宽滚动证书或碰撞规则。','']
    text+='\n'.join(lines)
    (out/'修复后测试报告.md').write_text(text,encoding='utf-8');(HERE/'修复后测试结论.md').write_text(text,encoding='utf-8')
    for name in ('fix64_baseline_control.py','fix64_finalize.py'):
        shutil.copy2(HERE/name,out/'test_scripts'/name)
    (out/'test_hashes_final.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((out/'test_scripts').glob('*.py'))},indent=2),encoding='utf-8')
    print(json.dumps(dict(matrix=facts['counts'],unit=facts['unit'],controls=len(controls),traces=facts['trace_count']),ensure_ascii=False),flush=True)
if __name__=='__main__':main(sys.argv[1])
