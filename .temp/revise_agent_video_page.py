from pathlib import Path
import ast,re
root=Path.cwd();p=root/'.temp'/'build_technical_video.py';s=p.read_text(encoding='utf-8');tree=ast.parse(s)
n=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='notes' for t in n.targets))
notes=ast.literal_eval(n.value)
notes[6]=('Agent 测试情况与问题修复',46,'先介绍上方测试结果，再用下方两张卡片简要说明 D07 和修复后的表现。','最后看业务助手的测试。下单、查询、提级和装货前取消等常用操作，六十段测试全部通过。整体测试已运行一百五十七段，其中一百四十六段通过，其余结果列在这里。测试中发现的 D07，是用户清空对话后，只说“刚才那个，取消掉”，模型却把查到的唯一任务 T001 直接取消了。我们因此在执行前加了一道检查：用户明确给出编号，或在界面关联了目标任务，才能取消；查询结果不能代替用户选择。修复后三轮复测中，模糊指令都会先追问，明确编号和界面关联的任务也都能正常取消。另用模拟的错误调用，确认程序会拦住未指定目标的操作。以上就是我们的项目介绍，谢谢。')
lines=s.splitlines(keepends=True);lines[n.lineno-1:n.end_lineno]=['notes='+repr(notes)+'\n'];s=''.join(lines)
start=s.index("slides.append(head(7,");end=s.index("css=r'''",start)
slide='''slides.append(head(7,'AGENT TESTING','Agent 测试：常用操作与问题修复','既检查任务有没有真正执行，也核对助手的回答与实际状态是否一致。')+\'\'\'
<div class="agent-overview">
 <article class="panel everyday"><div class="mini">常用业务操作 · A、B 两组</div><div class="everyday-score"><strong>60 <span>/ 60 段</span></strong><span class="pill">全部通过</span></div><p>下单、地点识别、查询、提级、装货前取消</p></article>
 <article class="panel matrix-summary"><div class="summary-heading"><h2>原主矩阵</h2><span>已执行 <b>157 / 180</b> 段</span></div><div class="agent-counts"><div><strong>146</strong><span>通过</span></div><div class="count-fail"><strong>10</strong><span>失败</span></div><div><strong>1</strong><span>未完结</span></div><div><strong>23</strong><span>未运行</span></div></div><p class="fine">以上为 10 月 21 日原测试成绩；D07 修复后的专项复测单独报告。</p></article>
</div>
<div class="agent-lessons">
 <article class="panel incident"><div class="lesson-label orange">测试发现的问题 · D07</div><h2>没说清是哪一单，却取消了任务</h2><p>清空对话、没有关联任务时，用户说：</p><blockquote>“刚才那个，取消掉。”</blockquote><p>模型查询后，把唯一的 T001 直接取消了。<br><strong>查到任务，不等于用户选中了它。</strong></p></article>
 <article class="panel resolution"><div class="lesson-label teal">怎么解决</div><h2>取消前，先由程序核对目标</h2><p>只允许取消本轮明确给出编号，或界面关联的任务。<br>查询结果、旧对话不能扩大范围；有未指定的目标，整批不执行。</p><div class="retest-strip"><span>修复后三轮真实模型复测</span><strong>三类检查各 3 / 3 通过</strong></div><p class="fine">模糊指令先追问；明确编号、界面关联均正常取消。<br>另用离线模拟的错误调用，验证程序会在执行前拦截。</p></article>
</div>
<div class="agent-batch-note">D07 真实模型复测中主动澄清，无任务写入；原主矩阵尚有未完成项，专项通过不等于全量验收通过。</div>
\'\'\')
'''
s=s[:start]+slide+s[end:]
s=s.replace('<div class="edition">TECHNOLOGY <b>×</b> EVIDENCE</div>','').replace('<span class="footer-label">架构 · 业务 · 分配 · 路径 · 执行 · 验证</span>','')
# Remove obsolete presentation rules for the replaced seventh page.
s=re.sub(r'\.d07-case-grid\{.*?(?=\n)', '', s)
newcss='''
css+=r\'\'\'
.footer{display:grid;grid-template-columns:1fr auto 1fr}.footer .dots{grid-column:2}.footer .page{grid-column:3;justify-self:end}
.agent-overview{display:grid;grid-template-columns:.9fr 1.2fr;gap:22px;margin-top:26px}.agent-overview .panel{padding:21px 26px}.everyday-score{display:flex;align-items:center;justify-content:space-between;margin:11px 0 13px;gap:14px}.everyday-score>strong{font:59px Consolas,monospace;color:var(--lime)}.everyday-score>strong span{font-size:28px}.everyday p{font-size:19px;line-height:1.6}.summary-heading{display:flex;align-items:center;justify-content:space-between}.summary-heading h2{font-size:23px;margin:0}.summary-heading>span{font-size:19px;color:var(--muted)}.summary-heading b{color:var(--ink);font-weight:500}.agent-counts{display:grid;grid-template-columns:repeat(4,1fr);gap:15px;margin:15px 0 12px}.agent-counts>div{display:flex;align-items:baseline;gap:12px}.agent-counts strong{font:39px Consolas,monospace;color:var(--lime)}.agent-counts span{font-size:17px;color:var(--muted)}.agent-counts .count-fail strong{color:var(--orange)}.matrix-summary .fine{font-size:14px}
.agent-lessons{display:grid;grid-template-columns:1fr 1.15fr;gap:22px;margin-top:22px}.agent-lessons .panel{padding:22px 26px}.lesson-label{font-size:17px;letter-spacing:.5px}.agent-lessons h2{font-size:26px;margin:10px 0 14px}.agent-lessons p{font-size:20px;line-height:1.65}.incident blockquote{font-size:24px;line-height:1.5;margin:12px 0;padding:10px 16px;background:#f4b6810a;border-left:3px solid var(--orange)}.incident p strong{font-weight:500;color:var(--orange)}.retest-strip{display:flex;justify-content:space-between;gap:18px;align-items:center;margin:18px 0 13px;padding:14px 17px;background:#c5ed6b09;border:1px solid #465b42;border-radius:10px}.retest-strip span{font-size:17px;color:var(--muted)}.retest-strip strong{font-size:21px;color:var(--lime);font-weight:500;white-space:nowrap}.resolution .fine{font-size:16px;line-height:1.65}.agent-batch-note{font-size:15px;line-height:1.6;color:var(--muted);margin-top:17px}
\'\'\'
'''
s=s.replace("body=r'''",newcss+"\nbody=r'''")
p.write_text(s,encoding='utf-8');exec(compile(s,str(p),'exec'),{'__file__':str(p),'__name__':'__main__'})
folder=root/'.report'/'演示视频_20261022';page=(folder/'04_关键技术与测试_录屏讲解.html').read_text(encoding='utf-8')
assert 'TECHNOLOGY' not in page
assert '架构 · 业务 · 分配 · 路径 · 执行 · 验证' not in page
seven=re.search(r'<section class="slide" id="slide7".*?</section>',page,re.S)[0]
assert '当前范围' not in seven and 'scope-band' not in seven
assert seven.index('60 <span>')<seven.index('测试发现的问题')
assert all(x in seven for x in ['146','157 / 180','未运行','T001','三类检查各 3 / 3 通过'])
md=folder/'05_关键技术与测试_配套讲稿.md'
with md.open('a',encoding='utf-8') as f:f.write('\n## 制作检查记录\n\n已检查 7 页结构、本地链接、脚本语法、240 秒预算及页内外讲稿一致性。第七页按“测试结果—问题与解决”顺序展示；当前环境尚未完成浏览器显示验收。\n')
print('Page 7 reordered, narration updated, requested labels removed.')
