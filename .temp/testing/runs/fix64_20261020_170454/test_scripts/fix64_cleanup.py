"""Apply and check final status/legacy lease cleanup after the frozen matrix ends."""
from pathlib import Path
import sys,json,subprocess,os,shutil,hashlib,re
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
from run_suite import dump
from fix64_suite import fingerprint

def main(out):
    out=Path(out).resolve()
    assert (out/'修复后测试报告.md').exists(),'Complete and archive the matrix before cleanup'
    before=fingerprint();snapshot=out/'source_snapshot'
    for name in ('simulation.py','controller.py','coordination/recovery.py','tests/test_plan_recovery.py'):
        assert (snapshot/name).read_bytes()==(ROOT/name).read_bytes(),'matrix snapshot differs from cleanup input'
    shutil.copy2(out/'unit_test_summary.json',out/'unit_test_summary_matrix.json')
    p=ROOT/'simulation.py';s=p.read_text(encoding='utf-8')
    old="if self.message.startswith(('已安全暂停','连续无执行进展','重新规划中')):"
    assert s.count(old)==1;s=s.replace(old,"if self.message.startswith(('已安全暂停','连续无执行进展','重新规划中','重规划未成功')):")
    old='''        self.dirty = False
        self.failed_attempts = 0
        if self.message.startswith(("重新规划中", "已安全暂停", "连续无执行进展")):
'''
    new='''        self.dirty = False
        self.failed_attempts = 0
        self.plan_valid_until = None
        self.metrics['planning_status'] = 'success'
        if self.message.startswith(("重新规划中", "已安全暂停", "连续无执行进展", "重规划未成功")):
'''
    assert s.count(old)==1;s=s.replace(old,new);p.write_text(s,encoding='utf-8')
    p=ROOT/'tests/test_plan_recovery.py';s=p.read_text(encoding='utf-8')
    marker='\n\nclass ControllerRecoveryTests(unittest.TestCase):'
    addition='''
    def test_successful_replan_clears_retention_status_message(self):
        from coordination.coordinator import solve
        sim = scene(); self.assertTrue(sim.apply_proposal(failed()))
        sim.dirty = True
        proposal = solve(sim); self.assertTrue(proposal.success)
        self.assertTrue(sim.apply_proposal(proposal))
        self.assertIsNone(sim.plan_valid_until)
        self.assertEqual(sim.metrics['planning_status'], 'success')
        self.assertEqual(sim.message, '安全路线已更新，可继续执行')

    def test_direct_legacy_success_clears_retained_deadline(self):
        sim = scene(); self.assertTrue(sim.apply_proposal(failed()))
        sim.profile = PlanningProfile(mode='legacy_full'); sim.dirty = True
        self.assertTrue(sim.ensure_plan()); self.assertIsNone(sim.plan_valid_until)
        self.assertEqual(sim.metrics['planning_status'], 'success')
        for _ in range(RETAIN_STEPS+5):
            self.assertTrue(sim.ensure_plan()); self.assertTrue(sim.step())
        self.assertTrue(all(t.status=='completed' for t in sim.tasks.values()))
        self.assertFalse(sim.dirty)

    def test_controller_mode_switch_clears_retained_deadline(self):
        from controller import Controller
        sim = scene(); self.assertTrue(sim.apply_proposal(failed()))
        with patch('controller.Simulation', return_value=sim):c = Controller(paused=True)
        c.start()
        try:
            view = c.submit('planning', {'mode':'legacy_full'}).result(timeout=20)
            self.assertIsNone(view['plan_valid_until'])
            self.assertEqual(view['metrics']['planning_status'], 'success')
            self.assertTrue(view['paused'])
            self.assertEqual(view['message'], '安全路线已更新，可继续执行')
        finally:c.stop(save_on_exit=False)
'''
    assert s.count(marker)==1;s=s.replace(marker,'\n'+addition+marker);p.write_text(s,encoding='utf-8')
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONIOENCODING':'utf-8'}
    done=subprocess.run([str(ROOT/'.venv/Scripts/python.exe'),'-B','-m','unittest','discover','-s','tests','-v'],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=90)
    (out/'cleanup_unittest.stdout.txt').write_text(done.stdout,encoding='utf-8');(out/'cleanup_unittest.stderr.txt').write_text(done.stderr,encoding='utf-8')
    assert done.returncode==0,done.stderr
    match=re.search(r'Ran (\d+) tests in ([\d.]+)s',done.stderr);assert match
    unit=dict(command='.venv/Scripts/python.exe -B -m unittest discover -s tests -v',tests_run=int(match[1]),passed=int(match[1]),failed=0,elapsed_seconds=float(match[2]),version='final cleanup; see source_hashes_cleanup.json')
    assert unit['tests_run']==25;dump(out/'unit_test_summary.json',unit)
    final=fingerprint();dump(out/'source_hashes_cleanup.json',final)
    changed=[n for n in set(before)|set(final) if before.get(n)!=final.get(n)]
    assert set(changed)=={'simulation.py','tests/test_plan_recovery.py'}
    dump(out/'cleanup_integrity.json',dict(matrix_manifest='source_hashes_after_fix.json',final_manifest='source_hashes_cleanup.json',changed=changed,scope='successful-plan status message; direct legacy mode clears obsolete execution lease; three regression cases added',route_recovery_module_unchanged=before['coordination/recovery.py']==final['coordination/recovery.py'],controller_unchanged=before['controller.py']==final['controller.py']))
    for name in ('simulation.py','controller.py','coordination/recovery.py','tests/test_plan_recovery.py'):
        target=out/'source_snapshot_final'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,target)
    (out/'tracked_changes_final.diff').write_text(subprocess.check_output(['git','diff','--binary'],cwd=ROOT).decode('utf-8'),encoding='utf-8')
    text=(out/'修复后测试报告.md').read_text(encoding='utf-8')
    text=text.replace('22 项','25 项').replace('| 新增持久回归测试 | 22 |','| 新增持久回归测试 | 25 |')
    text=text.replace('源码在本轮测试期间保持一致；','源码在大矩阵测试期间保持一致；随后完成状态提示和直接旧模式的期限清理，详见下节；')
    text+='''
## 7. 最终收尾版本

大矩阵及轨迹审计完成后，修正了正常规划成功时仍显示路线复用提示的问题，并清理直接从恢复模式切到 legacy_full 后残留的执行期限，防止到期后每步重复规划。另增三项回归：成功状态更新、直接旧模式运行超过原期限、真实控制器切换模式并保持人工暂停。最终持久测试为 25/25，通过日志见 cleanup_unittest.stderr.txt。

64 台、原规模和核心大矩阵数据对应 source_hashes_after_fix.json / source_snapshot/；最终代码对应 source_hashes_cleanup.json / source_snapshot_final/。收尾没有改变完整模式路线复用、任务匹配、路径搜索、异步控制器或独立安全校验算法；不将大矩阵的冻结版本与最终文件指纹混为同一份文件。cleanup_integrity.json 记录两版本差异。此前的大矩阵和轨迹不重复累计，原始结果保持不动。
'''
    (out/'修复后测试报告.md').write_text(text,encoding='utf-8');(HERE/'修复后测试结论.md').write_text(text,encoding='utf-8')
    facts=json.loads((out/'postfix_facts.json').read_text(encoding='utf-8'));facts['unit']=unit;facts['cleanup_integrity']='cleanup_integrity.json';dump(out/'postfix_facts.json',facts)
    shutil.copy2(__file__,out/'test_scripts'/'fix64_cleanup.py')
    dump(out/'test_hashes_final.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((out/'test_scripts').glob('*.py'))})
    print(json.dumps(dict(unit=unit,cleanup_changed=changed),ensure_ascii=False),flush=True)
if __name__=='__main__':main(sys.argv[1])
