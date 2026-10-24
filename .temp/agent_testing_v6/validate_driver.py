"""Synthetic end-to-end controls for the actual real-model case driver."""
from harness import *
from fixtures import prepare
from matrix import run_chat,document_run
from cases import manifest
from checks import extraction

def validate(root):
    fs=prepare(root/'fixtures');cases=manifest(fs);results=[]
    specs=[('A01','correct'),('A01','wrong_pickup'),('B03','correct'),('C02','correct'),('C02','wrong_forced'),('D03','correct'),('F01','correct'),('F09','wrong_delivery')]
    for n,(k,mode) in enumerate(specs):
        c=next(c for c in cases if c['case_id']==k);f=next(f for f in fs if f['id']==c['map']);p=f['pickup']
        if k=='A01':script=[reply(call('get_locations',{})),reply(call('create_tasks',{'tasks':[{'pickup_id':f['other'] if mode=='wrong_pickup' else p,'delivery_id':'D2'}]})),reply(content='已按回执创建。')]
        elif k=='B03':script=[reply(call('raise_task_priorities',{'changes':[{'task_id':'T001','mode':'increment'}]})),reply(content='已提升一级。')]
        elif k=='C02':script=[reply(call('get_status',{})),reply(call('assign_task' if mode=='wrong_forced' else 'set_task_preference',{'task_id':'T001','robot_id':'R3'})),reply()]
        elif k=='D03':script=[reply(call('cancel_tasks',{'task_ids':['T002']})),reply()]
        else:
            def generate(cfg,messages,tools,token,on_text,c=c,mode=mode):
                data=json.loads(messages[1]['content']);rows=[]
                for t in c['document']['truth']:
                    block=next(b for b in data['blocks'] if t['marker'] in b['text'])
                    r=extraction(t['pickup_id'],block['id'],t['count'],t['quantity_kind']);r.update(delivery_id='D1' if mode=='wrong_delivery' else t['delivery_id'],priority=t['priority']);rows.append(r)
                excluded=[{'source_ids':[b['id']],'reason':'注入备注不执行'} for b in data['blocks'] if '注入备注' in b['text']]
                return reply(call('propose_import_draft',{'candidates':rows,'excluded':excluded}))
            script=[generate]
        with Session(f['scenario'],root/f'{n}_{k}_{mode}',Scripted(script)) as s:
            out=document_run(s,c,f) if k.startswith('F') else run_chat(s,c,f,fs)
            errors=out['business_errors']+out.get('process_errors',[])
            expected=mode!='correct';ok=bool(errors)==expected
            record={'case':k,'mode':mode,'expected_error':expected,'passed':ok,'actual_errors':errors}
            results.append(record);print(json.dumps(record,ensure_ascii=False),flush=True)
    write(root/'controls.json',results)
    return results

if __name__=='__main__':
    root=Path(__file__).parent/'driver_validation'/uuid4().hex[:8]
    controls=validate(root)
    raise SystemExit(0 if all(c['passed'] for c in controls) else 1)
