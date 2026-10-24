from pathlib import Path
import json,gzip,hashlib,html,csv
from collections import Counter
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
BATCH=ROOT/'.temp/testing/runs/fix64_20261020_170454'
OUT=ROOT/'.report'
SHAPES={'rectangle':'规整仓库','l':'L 形仓库','t':'T 形仓库','u':'U 形仓库','courtyard':'庭院布局','rooms':'组合房间','random':'随机组合'}
COLORS={'~':'#edf1f4','.':'#ffffff','#':'#273e50','R':'#b9c6cf','O':'#c58042'}
PHASES=['idle','parking','to_pickup','picking','to_delivery','unloading']

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def esc(v):return html.escape(str(v),quote=True)
def shape_svg(m,route=None,hero=False):
    rows=m['rows'];w=len(rows[0]);h=len(rows);parts=[f'<svg viewBox="-1 -1 {w+2} {h+2}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{esc(m["label"])}，布局种子{m["seed"]}的实际测试地图"><title>{esc(m["label"])} · {m["seed"]}</title>']
    parts.append(f'<rect x="-1" y="-1" width="{w+2}" height="{h+2}" fill="#edf1f4"/>')
    for y,row in enumerate(rows):
        x=0
        while x<w:
            end=x+1
            while end<w and row[end]==row[x]:end+=1
            if row[x]!='~':parts.append(f'<rect x="{x}" y="{y}" width="{end-x}" height="1" fill="{COLORS[row[x]]}"/>')
            x=end
    for x,y in m['points']['parking']:parts.append(f'<rect x="{x+.14}" y="{y+.14}" width=".72" height=".72" rx=".16" fill="#e5ddf5" stroke="#8973b5" stroke-width=".12"/>')
    for x,y in m['points']['pickups']:parts.append(f'<circle cx="{x+.5}" cy="{y+.5}" r=".36" fill="#1863b4"/>')
    for x,y in m['points']['deliveries']:parts.append(f'<rect x="{x+.13}" y="{y+.13}" width=".74" height=".74" fill="#a35d16"/>')
    if route:
        for rid,color in ((2,'#db742d'),(7,'#028b7b')):
            path=route['paths'][str(rid)];keep=[]
            for p in path:
                if not keep or p!=keep[-1]:keep.append(p)
            points=' '.join(f'{x+.5},{y+.5}' for x,y in keep)
            parts.append(f'<polyline points="{points}" fill="none" stroke="white" stroke-width="1.1" stroke-linejoin="round" opacity=".85"/>')
            parts.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width=".55" stroke-linecap="round" stroke-linejoin="round"/>')
    for i,(x,y) in enumerate(m['points']['starts'][:16]):parts.append(f'<circle cx="{x+.5}" cy="{y+.5}" r=".39" fill="#097f72" stroke="white" stroke-width=".12"/>')
    parts.append('</svg>');return ''.join(parts)

def pack_replay(folder,m,ident,label):
    result=read(folder/'result.json');final=read(folder/'final_state.json')
    frames=[]
    with gzip.open(folder/'trace.jsonl.gz','rt',encoding='utf-8') as f:
        for line in f:
            r=json.loads(line);bots=[]
            for b in r['robots']:bots.extend((b[1],b[2],PHASES.index(b[3]),b[5] or 0,int(b[4]),b[7]))
            frames.append([r['tick'],sum(t[1]=='completed' for t in r['tasks']),sum(t[1]=='pending' for t in r['tasks']),bots])
    assert len(frames)==result['actual_steps_checked'] and frames[-1][1]==result['completed']
    return dict(id=ident,mapId=m['id'],label=label,n=result['inputs']['robots'],total=result['total'],tick=result['tick'],status=result['status'],frames=frames,tasks={str(t['id']):dict(pickup=t['pickup'],delivery=t['delivery'],priority=t['priority']) for t in final['tasks']},caseId=result['case_id'])

def main():
    OUT.mkdir(exist_ok=True)
    maps=[];replays=[];cards=[]
    for shape,label in SHAPES.items():
        for seed in (20261018,20261019):
            folders=[BATCH/'cases'/f'FIX-GEN-{shape}-{seed}-{n}' for n in (4,16)]
            definitions=[read(p/'actual_map.json') for p in folders];results=[read(p/'result.json') for p in folders]
            assert definitions[0]['grid']['rows']==definitions[1]['grid']['rows']
            assert all(r['status']=='PASS' for r in results)
            m=dict(id=f'{shape}-{seed}',label=label,shape=shape,seed=seed,taskSeed=results[1]['inputs']['seed'],rows=definitions[1]['grid']['rows'],points=definitions[1]['points'],width=96,height=64,parameters=definitions[1]['metadata']['parameters'],results=[dict(n=r['inputs']['robots'],completed=r['completed'],total=r['total'],tick=r['tick'],elapsed=round(r['elapsed'],3),caseId=r['case_id']) for r in results])
            maps.append(m);replays.append(pack_replay(folders[1],m,m['id'],f'{label} · {str(seed)[-4:]} · 16 台'))
            cards.append(f'''<button class="map-card" data-map="{m['id']}" data-shape="{shape}" aria-haspopup="dialog"><span class="map-plate">{shape_svg(m)}</span><span class="map-caption"><strong>{label}</strong><span class="seed">种子 {seed}</span></span><span class="map-verdict"><span>4 台 · 8/8</span><span>16 台 · 32/32</span><span class="zoom-hint">放大查看 ↗</span></span></button>''')
    assert len({hashlib.sha256('\n'.join(m['rows']).encode()).hexdigest() for m in maps})==14
    native=BATCH/'cases/FIX-SCALE32-fleet_64x64-20262018';definition=read(native/'actual_map.json')
    fleet=dict(id='fleet-32',label='规模验证示例',shape='fleet',seed=20262018,taskSeed=20262018,rows=definition['grid']['rows'],points=definition['points'],width=definition['grid']['width'],height=definition['grid']['height'],parameters={},results=[])
    maps.append(fleet);replays.append(pack_replay(native,fleet,fleet['id'],'规模验证示例 · 32 台'))
    rows=[json.loads(l) for l in (BATCH/'delivery_32/验收结果.jsonl').read_text(encoding='utf-8').splitlines()]
    core=[r for r in rows if r['stage'] in ('P0','P1','P2','P3','P5')]
    assert len(core)==1715 and all(r['status']=='PASS' for r in core)
    assert sum(r['case_id'].startswith('A-random-') for r in core)==1200
    assert sum(r['case_id'].startswith('SIPP-oracle-') for r in core)==200
    table=[];case_data=[]
    for r in rows:
        if r['stage'] not in ('P4-main','P4-dynamic','P6-32','P6-coupling','P6-mode'):continue
        s=r['inputs'];kind={'P4-main':'随机地图','P4-dynamic':'动态任务','P6-32':'规模验证','P6-coupling':'联动方式','P6-mode':'规划模式'}[r['stage']]
        cid=r['case_id'].removeprefix('FIX-')
        if r['stage']=='P4-main':
            shape,seed,n=cid.removeprefix('GEN-').rsplit('-',2)
            label=f'{SHAPES[shape]} · 布局种子 {seed} · {n} 台'
        elif r['stage']=='P4-dynamic':label=SHAPES[cid.removeprefix('DYNAMIC-')]
        elif r['stage']=='P6-32':
            source,seed=cid.removeprefix('SCALE32-').rsplit('-',1)
            name={**SHAPES,'fleet_64x64':'标准仓库','irregular_96x64':'不规则仓库'}[source]
            label=f'{name} · 任务种子 {seed}'
        elif r['stage']=='P6-coupling':
            mode,repetition=cid.removeprefix('COUPLING-').rsplit('-',1)
            label={'off':'静态 ETA','estimated':'占用估计','candidate':'候选联动'}[mode]+f' · 第 {int(repetition)+1} 次'
        else:label={'legacy_full':'旧完整模式','rolling':'滚动窗口'}[cid.removeprefix('MODE-')]
        data=dict(id=r['case_id'],category=kind,n=s['robots'],label=label,status=r['status'],completed=r['completed'],total=r['total'],tick=r['tick'],seconds=round(r['elapsed'],2),budget=s['plan_seconds'])
        case_data.append(data)
        status='完成' if r['status']=='PASS' else '预算内未完成'
        table.append(f'<tr data-category="{kind}" data-status="{r["status"]}" data-n="{s["robots"]}"><td><strong>{kind}</strong><small>{esc(label)}</small></td><td>{s["robots"]} 台</td><td>{r["completed"]}/{r["total"]}</td><td><span class="status {"pass" if r["status"]=="PASS" else "pending"}">{status}</span></td><td>{r["tick"]}</td></tr>')
    assert len(table)==50
    summary=read(BATCH/'delivery_32/范围统计.json')
    data=dict(maps=maps,replays=replays,cases=case_data,summary=summary,date='2026-10-20',phaseLabels=['空闲','返回停车','前往取货','装货中','送货中','卸货中'],sourceVersion='矩阵测试版本；最终收尾版本补充状态更新与期限清理',unitTests=25)
    selected=next(m for m in maps if m['id']=='rooms-20261018')
    with gzip.open(BATCH/'cases/FIX-GEN-rooms-20261018-16/plans.jsonl.gz','rt',encoding='utf-8') as f:first_plan=json.loads(next(f))
    template=(HERE/'template.html').read_text(encoding='utf-8')
    css=(HERE/'report.css').read_text(encoding='utf-8');js=(HERE/'report.js').read_text(encoding='utf-8')
    encoded=json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
    content=template.replace('__CSS__',css).replace('__JS__',js).replace('__REPORT_DATA__',encoded).replace('__MAP_CARDS__','\n'.join(cards)).replace('__HERO_MAP__',shape_svg(selected,first_plan,True)).replace('__CASE_ROWS__','\n'.join(table))
    assert not any(p in content for p in ('__CSS__','__JS__','__REPORT_DATA__','__MAP_CARDS__'))
    assert not __import__('re').search(r'64\s*台|P6-64|ACTOR64|EXPERIMENT64|128/128',content)
    report=OUT/'AWCS_测试报告.html';report.write_text(content,encoding='utf-8')
    # A reusable vector atlas, with the same actual maps shown in the report.
    atlas=['<svg xmlns="http://www.w3.org/2000/svg" width="1580" height="560" viewBox="0 0 1580 560"><rect width="1580" height="560" fill="#f7f9fb"/><g font-family="Microsoft YaHei,Arial,sans-serif" fill="#172e40"><text x="36" y="52" font-size="27" font-weight="700">AWCS · 随机地图测试图集</text><text x="36" y="83" font-size="15" fill="#4d6578">7 类布局 × 2 个生成种子 = 14 张不同地图；每张分别完成 4 台与 16 台搬运测试，共 28/28 场景。</text>']
    for i,(shape,label) in enumerate(SHAPES.items()):
        x=36+i*217
        atlas.append(f'<text x="{x}" y="125" font-size="17" font-weight="700">{label}</text>')
        for j,seed in enumerate((20261018,20261019)):
            m=next(m for m in maps if m['id']==f'{shape}-{seed}');svg=shape_svg(m).replace('<svg viewBox=',f'<svg x="{x}" y="{148+j*185}" width="200" height="138" viewBox=',1)
            atlas.extend((svg,f'<text x="{x}" y="{309+j*185}" font-size="13" fill="#51687a">布局种子 {seed} · 4/16 台完成</text>'))
    atlas.append('<text x="36" y="537" font-size="13" fill="#51687a">图示直接取自归档实际网格；固定种子用于复现。地图图集不等于任意布局上的可解性证明。</text></g></svg>')
    (OUT/'测试地图总览.svg').write_text(''.join(atlas),encoding='utf-8')
    (OUT/'测试报告使用说明.md').write_text('# 测试报告使用说明\n\n双击 AWCS_测试报告.html 即可离线打开，无需启动项目或联网。\n\n- 阅读模式：滚动查看完整报告。\n- 讲解视图：按章节展示，左右方向键切换，Esc 返回阅读模式。\n- 讲解提示：显示每节可直接口述的提示。\n- 随机地图：筛选布局、点击放大、查看两种规模的实际结果，或跳转该地图回放。\n- 轨迹回放：播放/暂停、拖动时间线、选择机器人和播放速度，观察归档真实轨迹。\n- 打印：通过浏览器打印保存为 PDF；动画以当前画面呈现。\n- 所有地图、样式与回放数据均已内嵌，分享 HTML 文件即可。另附测试地图总览.svg，便于放入讲解材料。\n\n数据沿用现有归档，未重新运行规划测试。随机地图为 7 类布局、2 个固定生成种子，共 14 张；每张测试 4/16 台。32 台与动态任务结果分开呈现。\n',encoding='utf-8')
    (HERE/'data_validation.json').write_text(json.dumps(dict(distinct_random_maps=14,shapes=7,seeds=2,main_cases=28,main_pass=28,replay_datasets=len(replays),business_runs=len(table),core_checks=len(core),record_count=len(rows),scope_max_robots=max(c['n'] for c in case_data),html_bytes=report.stat().st_size),indent=2),encoding='utf-8')
    print(json.dumps(dict(report=str(report),bytes=report.stat().st_size,maps=14,replays=len(replays)),ensure_ascii=True))
if __name__=='__main__':main()
