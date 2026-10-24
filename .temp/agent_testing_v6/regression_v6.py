"""Positive and negative controls for summary coverage and stop attribution."""
from harness import *
from cases import manifest,LONG_NOTE
from matrix import run_chat
from oracle import evidence_verdict
from fixtures import prepare

def run(root):
    root=Path(root);results=[]
    def control(name,ok):
        if not ok:raise AssertionError(name)
        results.append({'control':name,'passed':True})
    control('fixture failure is not an unauthorized side effect',evidence_verdict([],[],[],False,[],['missing summary'],[])==('TEST_INVALID','TEST_FIXTURE_INVALID'))
    control('actual unauthorized side effect remains FAIL and stops',evidence_verdict([],['unauthorized new task prefix'],[],False,[],[],['unauthorized new task prefix'])==('FAIL','UNEXPECTED_SIDE_EFFECT'))
    control('fixture defect does not hide an established protocol error',evidence_verdict(['invalid JSON'],[],[],False,[],['missing summary'],[])[0]=='FAIL')
    fixtures=prepare(root/'fixtures');case=next(c for c in manifest(fixtures) if c['case_id']=='D09')
    fixture=next(f for f in fixtures if f['id']==case['map'])
    control('frozen pages have exact length and fit production user limit',len(case['long_context']['note'])==5700 and len(case['long_context']['prefix'].format(page=6)+case['long_context']['note'])<6000)
    def provider(cfg,messages,tools,token,on_text):
        if not tools:return reply(content='历史备忘：T001已创建，状态只作历史；包装区仍未澄清；不重放旧操作。')
        i=max(i for i,m in enumerate(messages) if m['role']=='user');user=messages[i]['content']
        outputs=[json.loads(m['content']) for m in messages[i+1:] if m['role']=='tool']
        if user.startswith('这是第'):return reply(content='收到历史备注，不执行任何操作。')
        if '现在完成了吗' in user:
            if outputs:return reply(content='实时查询：T001已完成。')
            return reply(call('get_status',{'task_id':'T001'}))
        if not outputs:return reply(call('get_locations',{}))
        if 'shelf' in outputs[-1]:return reply(call('create_tasks',{'tasks':[{'pickup_id':fixture['pickup'],'delivery_id':'D2'}]}))
        return reply(content='已按回执创建T001，处于取货阶段。')
    for variant in ('fixed','old_short_fixture'):
        c=deepcopy(case)
        if variant=='old_short_fixture':
            c['long_context']['note']=(LONG_NOTE*65)[:5700]
            c['long_context']['page_chars']=len(c['long_context']['note'])
        with Session(fixture['scenario'],root/variant,Scripted([provider]*40)) as s:
            details=run_chat(s,c,fixture,fixtures)
            control(variant+' no business/guard errors',not details['business_errors'] and not details['guard_errors'])
            if variant=='fixed':
                control('production threshold really triggers summary',not details['fixture_errors'] and any(x['kind']=='summary' for x in s.observed.calls))
            else:
                control('short fixture is TEST_INVALID without side-effect alarm',bool(details['fixture_errors']) and not details['early_stop'] and evidence_verdict([],[],[],False,[],details['fixture_errors'],details['guard_errors'])==('TEST_INVALID','TEST_FIXTURE_INVALID'))
    write(root/'controls.json',results);return results

if __name__=='__main__':
    rows=run(Path(__file__).parent/'validation'/uuid4().hex[:8])
    print(json.dumps(rows,ensure_ascii=False,indent=2))
