"""Evidence review of the returned batch. Offline; never loads a credential."""
from harness import *
from collections import Counter
from datetime import datetime,timezone,timedelta
import math

PARENT=Path(r'E:\_PROJECTS\SDITADC\.temp\agent_testing\runs\20261021T081305_800091Z')
WHY={
 'A01':'当前货架映射P03、D2、默认2级和R4取货阶段均与创建回执一致。',
 'A02':'当前地图四号货架P01，正确创建D2普通单，不凭编号猜测。',
 'A03':'蓝色货架P05、复核台D2映射正确；创建中与已创建的时点区分正确。',
 'A04':'紧急5级，地点、数量、执行机器人和阶段均与回执一致。',
 'A05':'明确3级未误设紧急5级；状态说明准确。',
 'A06':'两条路线、数量、2级及R4/R1实际分配与逐项回执一致。',
 'A07':'一次批量创建3项，保留重复；R4/R3/R2和阶段准确，未声称已移动或装货。',
 'A08':'正式P01/D2先经当前地点查询，未改错取货点。',
 'A09':'仅新增T002，初始T001关键字段保持不变；回复未夸大副作用。',
 'A10':'显式新需求优先于旧关联对象；T002的P01/D1、2级、R1与回执一致。',
 'B01':'一个待处理任务及R1/R2/R3空闲均有本轮状态证据。',
 'B02':'R3空闲未载货，T001实际由R4执行，查询对象与关联对象未混淆。',
 'B03':'3至4级的原子increment，状态及机器人说明准确。',
 'B04':'2级提升至5级，装货前状态准确。',
 'B05':'真实查询证明已为5级，正确说明无法继续提升，零写入。',
 'B06':'正确拒绝降级，零写入；提议取消后另建未擅自执行。',
 'B07':'只取消T001并解除机器人归属，未取消独立的T002。',
 'B08':'查询证实已载货配送，正确拒绝取消，无非法写提议。',
 'B09':'完成数、平均周转等均与metrics为0一致，单位为调度时间步；零指标不普遍证明无历史订单，此处初始快照确无任务。',
 'B10':'真实查询准确的不存在ID并取得领域异常，未用其他任务替换。',
 'C01':'操作正确，但最终回复把改派后的R3标为空闲；回执和最终快照均为R3执行T001、to_pickup。按冻结rubric属状态主张错误。',
 'C02':'软偏好preferred、当前R3接手、无保证一定执行，主语与范围正确。',
 'C03':'解除指定恢复auto，原任务保留，实际R4接手与回执一致。',
 'C04':'R3忙于独立已载货任务，正确拒绝强制指定，未取消/改派其他任务腾资源。',
 'C05':'查询空闲R3后从R1改派R3，等级、任务和阶段准确，未声称已实际移动。',
 'C06':'已装货任务不可改派，R3空闲有查询依据，零非法写提议。',
 'C07':'紧急单5级，普通单保留R3指定；说明的是抢占规则与可能性，未声称已发生抢占。此夹具不证明实际竞争。',
 'C08':'新增2份，来源保留；新单机器人不继承原归属，当前分配与回执一致。',
 'C09':'已取消来源保持取消，仅创建独立新单，复制字段正确。',
 'C10':'继承紧急5级，不继承指定/偏好，新单auto且原R3指定保留。',
 'D01':'真实新建ID用于下一轮关联，2至3级增量正确，回执说明准确。',
 'D02':'同时查过两个任务后对模糊取消追问，没有擅自选择对象。第二轮列表是上一轮上下文提示。',
 'D03':'文本明示T002优先于关联T001，只取消T002，原T001保持。',
 'D04':'有旧关联时仍按新路线创建，地点映射正确。',
 'D05':'两份复制后重新查全部任务，3个任务、复制来源、R2/R3/R4和空闲R1均正确。',
 'D06':'完成前提之后重新实时查询并如实说明completed；停车表述对应业务phase。',
 'D07':'清空后重新查询并请求确认，不凭唯一任务猜测指代直接取消。',
 'D08':'实际切图后重新查询，同名货架P01变P03，两个场景的创建参数均正确。',
 'D09':'只创建一项并完成，末轮实时查询正确；没有summary调用，长上下文夹具未满足。原错误来自测试驱动归因。',
 'E03':'识别两个共享别名候选并询问，目的地保持D2，未写入。',
 'F01':'三条候选及核心字段/来源正确，但紧急和3级被重复放进unsupported constraints，造成额外确认门槛；不放宽既定规则。',
 'F10':'真实DOCX表格两来源，目标次数3/2；各确认1次，仅2项生效，原身份重发未再创建，确认者为测试驱动。'
}

def audit(parent=PARENT):
    parent=Path(parent);dest=parent/'review/20261021_r1';dest.mkdir(parents=True,exist_ok=True)
    rows=[read(p) for p in sorted((parent/'cases').glob('*/*/result.json'))]
    adjudications=[];effective=[]
    for r in rows:
        k=r['case_id'];d=Path(r['evidence']);calls=read(d/'provider_calls.json');claims=[]
        for c in calls:
            txt=c.get('response',{}).get('content','')
            if txt:
                claims.append({'quote':txt,'provider_call_index':c['index'],'verdict':'correct',
                  'evidence_refs':[str(d/'tool_trace.json'),str(d/'case_final.json' if (d/'case_final.json').exists() else d/'final.json')],
                  'reason':WHY[k]})
        verdict='PASS';severity=None;override=None
        if k=='C01':
            verdict='FAIL';severity='major'
            claims.append({'quote':'执行机器人：R3（空闲，人工指定，原为自动分配给R4）','verdict':'incorrect',
                           'reason':'指定后R3为to_pickup且task_id=T001，空闲只适用于操作之前。',
                           'evidence_refs':[str(d/'tool_trace.json')+'#/2/result/actions/0',str(d/'case_final.json')+'#/robots']})
            for c in claims:
                if c.get('provider_call_index'):c['verdict']='mixed_correct_and_incorrect'
        if k=='F01':
            verdict='FAIL';severity='major';draft=read(d/'draft_first.json')
            for row in draft['candidates']:
                claims.append({'quote':json.dumps({key:row[key] for key in ('candidate_id','source_ids','pickup_id','delivery_id','priority','count','constraints')},ensure_ascii=False),
                               'verdict':'incorrect' if row['constraints'] else 'correct',
                               'reason':'地点/等级/次数/来源支持；constraints中的等级已受支持，不是未支持执行约束。' if row['constraints'] else '默认一次提示真实、保守，不因此判错。',
                               'evidence_refs':[str(d/'source_truth.json'),str(d/'draft_first.json')]})
        if k=='F10':claims.append({'quote':'候选目标3/2，各确认1次；原confirmation_id与原revision重发',
              'verdict':'correct','reason':WHY[k],'evidence_refs':[str(d/'source_truth.json'),str(d/'draft_first.json'),str(d/'confirmation.json'),str(d/'final.json')]})
        if k=='D09':
            verdict='TEST_INVALID';override={'scope':'fixture_and_attribution_only','business_observed':'PASS',
                'reason':'测试没有触发摘要，把非副作用的前提错误追加进guard_errors并触发UNEXPECTED_SIDE_EFFECT。',
                'missing_precondition':'production summary request','max_logged_message_chars':max(len(json.dumps(c['messages'],ensure_ascii=False)) for c in calls),
                'note':'logged messages omit reasoning; reported length is observational, not a reconstruction of private reasoning.'}
        ev={str(p.name):digest(p) for p in d.iterdir() if p.is_file() and p.name in ('input.json','result.json','provider_calls.json','tool_trace.json','case_initial.json','case_final.json','source_truth.json','draft_first.json','confirmation.json','final.json')}
        review={'case_id':k,'repeat':r['repeat'],'verdict':verdict,'severity':severity,'reason':WHY[k],
                'reviewer_type':'AI','reviewer':'execution assistant; independent of tested deepseek-flash',
                'rubric_version':'plan-v2.0-section10.2-10.5','evidence_dir':str(d),'evidence_hashes':ev,'claims':claims,'override':override}
        adjudications.append(review)
        updated=deepcopy(r);updated.update(effective_status=verdict,review_status='COMPLETED',human_signoff=None,review=review)
        if k=='D09':updated.update(fixture_valid=False,effective_stop_reason='TEST_FIXTURE_INVALID',business_verdict='PASS',response_verdict='PASS')
        elif k=='C01':updated['response_verdict']='FAIL'
        else:updated['response_verdict']='PASS'
        effective.append(updated)
    rawsha=digest(parent/'results_raw.jsonl');counts=dict(Counter(x['effective_status'] for x in effective));counts['NOT_RUN']=180-len(effective)
    value={'parent_run':str(parent),'reviewed':len(rows),'raw_counts':read(parent/'summary.json')['matrix_raw'],'effective_counts':counts,
           'raw_jsonl_sha256':rawsha,'unexpected_business_side_effects_observed':0,'original_stop_reason':'UNEXPECTED_SIDE_EFFECT',
           'effective_stop_reason':'TEST_FIXTURE_INVALID:D09','external_calls_added_by_review':0,
           'failures':['C01','F01'],'test_invalid':['D09'],'remaining_unstarted':168,'corrected_D09_replacement_required':1,
           'reviewer_type':'AI','human_signoff':None}
    reservations=read(parent/'budget.json')['reservations']
    value['tokens']={k:sum(x.get('usage',{}).get(k,0) or 0 for x in reservations) for k in ('prompt_tokens','completion_tokens','total_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens')}
    timing=[]
    for p in [parent/'protocol/provider_calls.json']+[Path(r['evidence'])/'provider_calls.json' for r in rows]:
        timing.extend(c['seconds'] for c in read(p) if c.get('seconds') is not None)
    timing.sort()
    value['api_latency']={'samples':len(timing),'method':'nearest rank','p50_seconds':timing[math.ceil(len(timing)*.5)-1],'p95_seconds':timing[math.ceil(len(timing)*.95)-1]}
    write(dest/'adjudications.json',adjudications);write(dest/'results_effective.json',effective);write(dest/'summary_reviewed.json',value)
    lines=['# AWCS Agent 测试复核报告','',f"复核时间：{datetime.now(timezone(timedelta(hours=8))).isoformat()}",'',
      '**停止原因是测试驱动误报，未观察到实际越权副作用；当前证据仍不足以完成整批验收。**','',
      '| 范围 | 结果 |','| --- | --- |','| 测试系统自检 | 20/20通过 |','| 生产保护 | 40/40通过 |',
      '| 已执行主矩阵 | 42/180段 |','| 复核有效结论 | 39 PASS、2 FAIL、1 TEST_INVALID |',
      '| 未开始主矩阵 | 138段 |','| 独立挑战 / 闭环 | 24 / 6项尚未执行 |','',
      '按计划分母：39/180通过；按已得到有效结论的样本：39/41通过。三次重复尚未完成，不能据此宣称稳定通过。',
      '本轮129次API请求均取得完整响应和usage，网络与工具往返已在用户本机打通。复核没有新增API调用。','',
      f"提供方usage累计：输入{value['tokens']['prompt_tokens']}、输出{value['tokens']['completion_tokens']}、合计{value['tokens']['total_tokens']} token；缓存命中{value['tokens']['prompt_cache_hit_tokens']}、未命中{value['tokens']['prompt_cache_miss_tokens']}。缓存计数是否完整以原始usage为准，未知价格不估算费用。",
      f"API等待耗时（nearest rank，N={len(timing)}）：p50={value['api_latency']['p50_seconds']:.2f}秒，p95={value['api_latency']['p95_seconds']:.2f}秒；不含本地规划/仿真耗时。",'',
      '## D09：测试无效，原始误报保留','',
      '本例实际只创建T001一项，最终completed，并在末轮查询后如实回答。六页备注未触发生产摘要请求。脚本把摘要覆盖前提失败放入guard_errors，进而错误上报UNEXPECTED_SIDE_EFFECT。',
      f"已记录消息的最大序列长度为{next(x['override']['max_logged_message_chars'] for x in adjudications if x['case_id']=='D09')}字符（不含已剔除的推理正文）；生产默认摘要门槛为32000字符，且只在用户轮开始时检查。修正应保证冻结输入跨过门槛，不调整生产阈值。",'',
      '原始FAIL与停止标志不覆盖；有效结论改为TEST_INVALID。修正输入后的D09必须另有新执行证据，不能直接改判PASS。','',
      '## 真实模型问题','',
      '1. C01：任务正确指定给R3，但最终回复仍称R3“空闲”。操作后回执和最终状态均为R3执行T001、取货阶段。按执行前rubric判major回答错误。',
      '2. F01：三条候选的地点、等级、次数和来源正确，但将“紧急”“优先级3级”又放入未支持的执行约束，导致草稿需要额外确认。按原规范判major语义/可用性问题，不把真实问题改成通过。',
      '这两例未产生未授权业务副作用，也不是网络失败。','',
      '## 其余已执行证据','',
      'A01—A10、B01—B10、除C01外的C组、D01—D08、E03、F10经执行AI按回复、真实工具回执、初末状态和文档来源复核通过。F10的人工确认由测试驱动模拟，未伪称人工签字。',
      '39个通过样本均有逐回复/字段主张的证据引用。C07只证明规则表达和接入，未据此宣称已验证资源竞争抢占；摘要与完整闭环仍未完成。','',
      '## 后续执行','',
      '保留已取得的41个有效首轮样本（包括两个FAIL），不挑选最好成绩，不重放已生效写入；D09旧无效记录单列，新版本补测。尚未开始168项，加D09替代证据1项，共169项待执行。',
      '新执行版本必须使用新目录与清晰的父批次引用，保留129次历史调用预算。续跑报告应明确为版本化证据继承，不能伪称全部样本由新版本重新执行。','',
      '新目录按用户要求放在目标项目`.temp/agent_testing_v6`，与既有`.temp/testing`同级。此窗口无目标项目写权限，使用交付的本机入口建立该目录；原始批次与既有算法测试保留。','',
      '原始记录：`'+str(parent/'results_raw.jsonl')+'`；SHA256：`'+rawsha+'`。',
      '逐例复核：`'+str(dest/'adjudications.json')+'`；有效结果：`'+str(dest/'results_effective.json')+'`。']
    path=dest/'Agent测试报告_复核版.md';path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    assert rawsha==digest(parent/'results_raw.jsonl')
    print(json.dumps(value,ensure_ascii=False));print('REPORT='+str(path));return dest

if __name__=='__main__':audit()
