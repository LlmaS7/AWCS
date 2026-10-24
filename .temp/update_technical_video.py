from pathlib import Path
import ast
root=Path.cwd(); path=root/'.temp'/'build_technical_video.py'
s=path.read_text(encoding='utf-8-sig'); tree=ast.parse(s)
node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='notes' for t in n.targets))
notes=ast.literal_eval(node.value)
seconds=[18,34,42,45,27,28,46]
notes=[(n[0],seconds[i],n[2],n[3]) for i,n in enumerate(notes)]
notes[5]=(notes[5][0],28,'先读核心检查与主场景数字，再指向 32 台结果和轨迹审计。','已有算法测试中，一千七百一十五项核心检查通过，覆盖独立穷举匹配对照、时空动态规划对照及执行保护。十四张生成地图上，四台和十六台机器人的二十八个主场景全部完成。三十二台规模场景完成八组中的五组，其余三组在预算内安全停止。五十份轨迹、共一万六千六百三十四个执行时间步的复审，未发现所检冲突或装卸等约束违规。')
notes[6]=('Agent 验证：D07 问题与修复',46,'按左、中、右讲清“原反例 → 执行前校验 → 专项复测”；底部保留历史成绩与验收范围。','业务助手的常规操作，A、B 两组共六十段全部通过。测试也发现了 D07 模糊指代误取消：清空会话且没有关联任务时，用户说“刚才那个，取消掉”，模型自行查询，把唯一任务 T001 当成用户指定对象并实际取消。问题在于，查到对象并不等于用户授权。修复后，服务层只接受本轮明确编号，或无编号时的界面关联对象；在提交前检查整批目标，发现未指定对象就整批拒绝。三轮真实模型复测中，模糊指代均主动澄清且未写入，明确编号与界面关联取消各三次生效；另用离线强制错误调用验证执行前拦截。新版本全量验收仍未完成。AWCS 用于仓储调度仿真与布局验证。谢谢。')
lines=s.splitlines(keepends=True)
lines[node.lineno-1:node.end_lineno]=['notes='+repr(notes)+'\n']
s=''.join(lines)
dynamic='<div class="test-row second"><div><h2>16 台有限动态流</h2><p>每例 60 项任务</p></div><strong>1 / 3</strong></div><div class="segments"><i></i><i class="incomplete"></i><i class="incomplete"></i></div>'
assert dynamic in s;s=s.replace(dynamic,'')
s=s.replace('规模与动态流 · 单次规划预算 3 秒','32 台规模验证 · 单次规划预算 3 秒')
s=s.replace('其余 5 例未完成；保留初次结果，不以补跑覆盖。','其余 3 例在预算内安全停止。<br>保留初次结果，不以补跑覆盖。')
s=s.replace('32 台为 5/8、16 台有限动态流为 1/3；未完成的五个场景预算内安全停止。轨迹复审包含其已执行前缀，未发现所检约束违规不代表任意未来任务都能完成。','第 6 页仅展示 32 台规模场景 5/8，其余 3 例预算内安全停止；动态流结果不在本段展开。50 份轨迹、16,634 个时间步仍沿用原审计的完整统计范围，不缩称为仅来自本页展示场景；未发现所检约束违规不代表任意未来任务都能完成。')
start=s.index("slides.append(head(7,");end=s.index("css=r'''",start)
newslide='''slides.append(head(7,'AGENT EVIDENCE','D07：从误取消反例，到执行前校验','常规操作 A、B 两组 60 / 60 段通过；针对测试发现的模糊指代问题补充保护。')+\'\'\'
<div class="d07-case-grid">
 <article class="panel case-problem"><span class="case-number orange">01 / 原问题</span><h2>把查询结果误当成用户授权</h2><p class="case-context">清空会话 · 未关联任务 · 系统仅有 T001</p><blockquote>“刚才那个，取消掉。”</blockquote><div class="case-chain">查询到 T001 <span>→</span> 自行选中 <span>→</span> 实际取消</div><p class="case-detail">任务真实变为 cancelled。<br>对象、阶段合法，但取消目标未明确。</p><div class="case-verdict">正确行为：先澄清目标，再执行。</div></article>
 <article class="panel case-fix"><span class="case-number teal">02 / 修复措施</span><h2>服务层执行前检查对象来源</h2><ol class="fix-list"><li><b>冻结本轮目标</b><span>明确 T 编号优先；无编号时取本轮界面关联对象。</span></li><li><b>查询不能扩大授权</b><span>查询结果、旧对话和摘要不新增可取消对象。</span></li><li><b>整批预检查</b><span>只要含未指定目标，整批不执行；要求补充明确指令。</span></li></ol><p class="fine">约束目标来源，不替代完整的自然语言意图判定。</p></article>
 <article class="panel case-retest"><span class="case-number">03 / 修复后复测</span><h2>真实模型三轮专项验证</h2><div class="d07-row"><div><strong>模糊指代，无关联</strong><p>主动澄清；无写入</p></div><b>3 / 3</b></div><div class="d07-row"><div><strong>明确任务编号</strong><p>实际取消，回执与终态一致</p></div><b>3 / 3</b></div><div class="d07-row"><div><strong>本轮界面关联</strong><p>实际取消，回执与终态一致</p></div><b>3 / 3</b></div><p class="fine">真实模型 guard_rejections = 0。<br>另以离线强制错误调用，验证后端执行前拦截。</p></article>
</div>
<div class="case-history">原主矩阵：146 PASS / 10 FAIL / 1 未完结；另 23 段未运行。D07 专项不改写原成绩。</div>
<div class="scope-band"><span class="orange">当前范围</span><p>新版本全量验收尚未完成；部分状态表述、文档约束归类和复杂任务流仍需完善。<br><b>应用定位：仓储调度仿真 · 布局实验 · 教学验证</b></p></div>\'\'\')
'''
s=s[:start]+newslide+s[end:]
extra_css='''
css+=r\'\'\'
:fullscreen #toolbar,.fullscreen-view #toolbar{display:none!important}
.scale-panel{display:flex;flex-direction:column;justify-content:center}.scale-panel .test-row{margin-top:24px}.scale-panel .segments{margin-top:17px;height:17px}.scale-panel .legend{margin-top:23px}.scale-panel .fine{margin-top:16px;line-height:1.7}
.d07-case-grid{display:grid;grid-template-columns:1fr 1.08fr 1fr;gap:20px;margin-top:26px}.d07-case-grid .panel{padding:22px 24px}.case-number{font:16px Consolas,'Microsoft YaHei',monospace;letter-spacing:1px;color:var(--lime)}.case-number.orange{color:var(--orange)}.case-number.teal{color:var(--teal)}.d07-case-grid h2{font-size:25px;line-height:1.45;margin:12px 0 17px}.case-context{font-size:16px;line-height:1.65}.case-problem blockquote{margin:18px 0;padding:15px 16px;border-left:3px solid var(--orange);background:#f4b6810a;font-size:24px}.case-chain{font-size:18px;color:var(--orange);line-height:1.7}.case-chain span{color:var(--muted);padding:0 5px}.case-detail{font-size:18px;margin-top:18px;line-height:1.7}.case-verdict{font-size:19px;color:var(--teal);margin-top:21px;padding-top:16px;border-top:1px solid var(--line)}.fix-list{margin:0;padding-left:24px}.fix-list li{padding-left:5px;margin-bottom:15px;font-size:19px;color:var(--teal)}.fix-list b{font-weight:500;color:var(--ink);display:block;margin-bottom:4px}.fix-list span{display:block;color:var(--muted);font-size:17px;line-height:1.7}.case-fix .fine{font-size:14px;margin-top:3px}.case-retest .d07-row{padding:11px 0}.case-retest .d07-row strong{font-size:19px}.case-retest .d07-row p{font-size:15px}.case-retest .d07-row b{font-size:29px;white-space:nowrap}.case-retest .fine{font-size:14px;line-height:1.75;margin-top:17px}.case-history{font-size:16px;line-height:1.7;color:var(--muted);margin-top:17px}.d07-case-grid~.scope-band{margin-top:15px;padding:15px 23px}.d07-case-grid~.scope-band p{font-size:17px}
\'\'\'
'''
s=s.replace("body=r'''",extra_css+"\nbody=r'''")
s=s.replace("addEventListener('resize',resize);resize();", "function syncFullscreen(){const browserFullscreen=Math.abs(innerHeight-screen.height)<=2&&Math.abs(innerWidth-screen.width)<=2;document.body.classList.toggle('fullscreen-view',Boolean(document.fullscreenElement)||browserFullscreen);}\naddEventListener('resize',()=>{resize();syncFullscreen();});document.addEventListener('fullscreenchange',syncFullscreen);resize();syncFullscreen();")
s=s.replace('按 <b>F</b> 全屏，再按 <b>R</b> 隐藏控制栏。','按 <b>F</b> 全屏，底部控制栏自动隐藏。')
s=s.replace('按 **F** 全屏，再按 **R** 隐藏控制栏；','按 **F** 全屏，底部控制栏自动隐藏，退出全屏后恢复；')
s=s.replace('再次按 **R** 恢复控制栏。','非全屏时按 **R** 切换控制栏；全屏时始终隐藏。')
s=s.replace('<b>R</b> 恢复控制栏，<b>H</b> 打开本说明。','退出全屏后恢复控制栏；<b>H</b> 打开本说明。')
s=s.replace('轨迹复审包含其已执行前缀','轨迹复审包含未完成场景的已执行前缀')
path.write_text(s,encoding='utf-8')
compile(s,str(path),'exec')
exec(compile(s,str(path),'exec'),{'__file__':str(path),'__name__':'__main__'})
md=root/'.report'/'演示视频_20261022'/'05_关键技术与测试_配套讲稿.md'
with md.open('a',encoding='utf-8') as f:f.write('\n## 制作检查记录\n\n已核对结构、源码与证据数字、240 秒预算、本地链接、页内外讲稿一致性，并检查脚本语法。当前环境仍未完成浏览器实际显示验收；正式录制前请打开页面试读一次。\n')
