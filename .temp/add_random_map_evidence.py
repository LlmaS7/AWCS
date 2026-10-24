from pathlib import Path
import re,json,ast,xml.etree.ElementTree as ET
root=Path.cwd();folder=root/'.report'/'演示视频_20261022';hp=folder/'04_关键技术与测试_录屏讲解.html';mp=folder/'05_关键技术与测试_配套讲稿.md'
page=hp.read_text(encoding='utf-8');md=mp.read_text(encoding='utf-8');report=(root/'.report'/'AWCS_测试报告.html').read_text(encoding='utf-8')
notes=json.loads(re.search(r'const\s+notes\s*=\s*(.*?);\s*\n',page,re.S)[1])
# Preserve any edits made directly to the current narration.
sections=re.findall(r'## 第 (\d+) 页 · (.*?)\n(.*?)(?=\n## |\Z)',md,re.S)
for index,title,body in sections:
 i=int(index)-1
 spoken=re.search(r'^> (.+)$',body,re.M)
 if spoken:notes[i][3]=spoken[1]
notes[5][0]='在随机地图上测试算法'
notes[5][2]='先介绍左侧两张真实测试地图和随机种子，再看右侧通过情况，最后带过下方轨迹检查。'
notes[5][3]='再来看算法测试。我们用地图生成器，按七类布局、两组随机种子，生成了十四张不同地图，覆盖不同的货架、通道和障碍分布。地图随机生成，种子固定下来，也方便重复测试。每张图分别用四台和十六台机器人运行，二十八个主场景全部完成。一千七百一十五项核心检查也全部通过。三十二台的八组测试完成了五组，另外三组在规定时间内没算出新方案，系统安全暂停。五十份运行轨迹的复查中，没有发现检查范围内的碰撞、穿过障碍或装卸异常。'
durations=[18,31,39,41,27,38,46]
for i,duration in enumerate(durations):notes[i][1]=duration
assert sum(durations)==240
maps=[]
for seed in [20261018,20261019]:
 key=f'random-{seed}'
 match=re.search(r'data-map="'+key+r'"[^>]*>.*?(<svg\b.*?</svg>)',report,re.S)
 assert match,key
 svg=match[1];ET.fromstring(svg)
 maps.append(f'<figure><div class="tested-map-svg">{svg}</div><figcaption>随机组合布局 <span>种子 {seed}</span></figcaption></figure>')
 data=json.loads((root/'.temp'/'testing'/'datasets'/'maps'/f'random_{seed}.json').read_text(encoding='utf-8-sig'))
 print('Map evidence:',key,'JSON keys:',list(data)[:8],'SVG bytes:',len(svg.encode('utf-8')))
inner='''<div class="eyebrow">06 / ALGORITHM TESTING</div><h1>在随机生成的地图上，验证调度表现</h1><p class="subtitle">7 类布局 × 2 组随机种子 = 14 张测试地图 · 固定种子，方便复现</p>
<div class="random-test-layout">
 <article class="panel random-map-panel"><div class="random-map-heading"><h2>实际测试地图</h2><span class="pill">不同种子，不同布局</span></div><div class="tested-map-pair">'''+''.join(maps)+'''</div><p class="map-shape-list">覆盖规整、L 形、T 形、U 形、庭院、组合房间、随机组合布局</p></article>
 <div class="six-results"><div class="six-stat-grid"><article class="stat-card"><div class="mini">任务分配 / 路径规划 / 执行检查</div><strong>1,715<span> 项</span></strong><h2>核心检查全部通过</h2></article><article class="stat-card"><div class="mini">14 张随机生成地图 · 4 / 16 台</div><strong>28<span> / 28</span></strong><h2>主场景全部完成</h2></article></div><article class="panel six-scale"><div class="mini">32 台规模测试 · 每例 64 项任务 · 单次规划预算 3 秒</div><div class="test-row"><h2>8 组测试，完成 5 组</h2><strong>5 / 8</strong></div><div class="segments"><i></i><i></i><i></i><i></i><i></i><i class="incomplete"></i><i class="incomplete"></i><i class="incomplete"></i></div><p class="fine">其余 3 组在预算内安全暂停；保留初次测试结果。</p></article></div>
</div>
<div class="audit-band"><div><strong>50</strong><span>份轨迹</span></div><div><strong>16,634</strong><span>实际执行时间步</span></div><p>轨迹检查未发现碰撞、穿过障碍、装卸异常或执行步数超限。<br><span>运行是否安全、任务是否完成，分别检查。</span></p></div>
<div class="bottom">图示来自已有报告中的真实测试地图；随机生成布局，固定种子复现测试。</div>'''
pattern=r'(<section class="slide" id="slide6"[^>]*>).*?(</section>)'
page,count=re.subn(pattern,lambda m:m[1]+inner+m[2],page,count=1,flags=re.S);assert count==1
page=re.sub(r'const\s+notes\s*=\s*.*?;\s*\n',lambda m:'const notes='+json.dumps(notes,ensure_ascii=False)+';\n',page,count=1,flags=re.S)
css='''
.random-test-layout{display:grid;grid-template-columns:1fr 1.08fr;gap:24px;margin-top:25px}.random-map-panel{padding:18px 22px}.random-map-heading{display:flex;justify-content:space-between;align-items:center;margin-bottom:15px;gap:12px}.random-map-heading h2{font-size:24px;margin:0}.random-map-heading .pill{font-size:15px;padding:6px 12px}.tested-map-pair{display:grid;grid-template-columns:1fr 1fr;gap:16px}.tested-map-pair figure{margin:0;min-width:0}.tested-map-svg{background:#edf1f4;border-radius:9px;overflow:hidden;padding:7px}.tested-map-svg svg{display:block;width:100%;height:183px;shape-rendering:crispEdges}.tested-map-pair figcaption{margin-top:9px;font-size:16px;line-height:1.6;color:var(--ink)}.tested-map-pair figcaption span{display:block;font:14px/1.6 Consolas,'Microsoft YaHei',monospace;color:var(--muted)}.map-shape-list{font-size:14px;line-height:1.6;margin-top:14px;color:var(--muted)}.six-results{display:flex;flex-direction:column;gap:18px}.six-stat-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.six-stat-grid .stat-card{padding:17px 20px}.six-stat-grid .stat-card .mini{font-size:13px;line-height:1.6;letter-spacing:0}.six-stat-grid .stat-card>strong{font-size:51px;line-height:1.1;letter-spacing:-2px;margin:11px 0 8px}.six-stat-grid .stat-card>strong span{font-size:23px;letter-spacing:0}.six-stat-grid .stat-card h2{font-size:22px;margin:6px 0 0}.six-scale{padding:16px 22px}.six-scale .mini{font-size:14px;line-height:1.6}.six-scale .test-row{margin-top:9px}.six-scale .test-row h2{font-size:23px;margin:0}.six-scale .test-row>strong{font-size:37px}.six-scale .segments{height:13px;margin-top:10px}.six-scale .fine{font-size:15px;line-height:1.6;margin-top:12px}#slide6 .audit-band{margin-top:21px;padding:18px 23px}#slide6 .audit-band p{font-size:17px}#slide6 .audit-band p span{font-size:16px}#slide6 .bottom{font-size:16px}
'''
page=page.replace('</style>',css+'</style>',1);hp.write_text(page,encoding='utf-8')
# Only change the requested narration plus its timing references in the existing Markdown.
newsection=f'## 第 6 页 · {notes[5][0]}\n\n**画面与操作**：{notes[5][2]}\n\n**讲解词（约 {notes[5][1]} 秒）**\n\n> {notes[5][3]}\n'
md,count=re.subn(r'## 第 6 页 · .*?(?=\n## 第 7 页)',lambda m:newsection,md,count=1,flags=re.S);assert count==1
for i,n in enumerate(notes,1):
 md=re.sub(r'\| '+str(i)+r' \| [^\n]+',lambda m:f'| {i} | {n[0]} | {n[1]} 秒 |',md,count=1)
 pattern=r'(## 第 '+str(i)+r' 页 · .*?\*\*讲解词（约 )\d+( 秒）\*\*)'
 md=re.sub(pattern,lambda m:m[1]+str(n[1])+m[2],md,count=1,flags=re.S)
mapnote='- 随机地图：7 类布局分别使用种子 `20261018`、`20261019`，共 14 张地图。第 6 页两幅地图直接取自原测试报告的 `random-20261018`、`random-20261019` 图示，对应 `.temp/testing/datasets/maps/random_20261018.json` 与 `random_20261019.json`。固定种子用于复现已生成的随机布局，不表示每轮重新抽取新地图。\n'
md=md.replace('## 源码定位',mapnote+'\n## 源码定位',1);mp.write_text(md,encoding='utf-8')
# Keep the local generator in sync without rebuilding or overwriting direct edits.
bp=root/'.temp'/'build_technical_video.py';build=bp.read_text(encoding='utf-8');tree=ast.parse(build)
node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='notes' for t in n.targets))
lines=build.splitlines(keepends=True);lines[node.lineno-1:node.end_lineno]=['notes='+repr([tuple(n) for n in notes])+'\n'];build=''.join(lines)
a=build.index("slides.append(head(6,");b=build.index("slides.append(head(7,",a)
build=build[:a]+"slides.append("+repr(inner)+")\n"+build[b:]
build=build.replace("body=r'''",'css+='+repr(css)+'\n'+"body=r'''",1)
bp.write_text(build,encoding='utf-8');compile(build,str(bp),'exec')
# Confirm the real map drawings are embedded and the previous omissions are preserved.
assert all(f'种子 {seed}' in page for seed in [20261018,20261019])
assert '16 台有限动态流' not in page and 'TECHNOLOGY' not in page
assert all(n[3] in md for n in notes)
print(json.dumps({'seconds':sum(n[1] for n in notes),'durations':[n[1] for n in notes],'page6_chars':len(notes[5][3]),'embedded_test_maps':len(maps),'bytes':hp.stat().st_size,'page5_preserved':notes[4][3]},ensure_ascii=False))
