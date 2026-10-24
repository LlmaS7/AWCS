from harness import *
from cases import document_case
from matrix import execute,document_run
from checks import docx

def instantiate(case,f):
    case=deepcopy(case);variant=case['variant']
    if not variant.startswith('doc_'):return case
    if variant=='doc_corrupt':return case
    template='F10' if variant=='doc_remaining' else ('F08' if variant=='doc_deadline' else 'F01')
    spec=document_case(template,f);spec['filename']=case['case_id']+'.txt';spec['confirmation']='extract_only'
    if variant=='doc_duplicate':
        first=spec['truth'][0];spec['truth']=[first,{**first,'marker':'需求乙','text':'需求乙：四号货架送二号配送点。'}]
    elif variant=='doc_delivery':
        spec['truth']=spec['truth'][:2]
        spec['truth'][0]['text']='需求甲：四号货架送二号配送点，备注：与一号配送点无关。'
        spec['truth'][1].update(priority=2,text='需求乙：登记货架2送一号配送点，备注：与二号配送点无关。')
    elif variant=='doc_deadline':
        spec['truth'][0].update(priority=5,text='需求甲：四号货架送二号配送点，紧急，下午4点前到。',constraints=['下午4点'])
        spec['confirmation']='block_constraints'
    elif variant=='doc_override':
        spec['truth']=spec['truth'][:1];spec['truth'][0]['delivery_id']='D1'
        spec['instruction']='仅将需求甲的目的地改为一号配送点，其他字段保持原文。'
    elif variant=='doc_remaining':spec['confirmation']='each_one_retry_original'
    spec['lines']=[r['text'] for r in spec['truth']]+spec['excluded'];spec['text']='\n'.join(spec['lines'])
    case.update(kind='document',document=spec);return case

def extra_document_check(s,case):
    variant=case.get('variant');errors=[]
    if variant=='doc_override':
        d=s.ai.imports.draft()['draft']
        if not d or any(not r['overrides'] for r in d['candidates']):errors.append('explicit instruction override not recorded')
    if variant=='doc_remaining':
        d=s.ai.imports.draft()['draft']
        if d['state']!='ready':return ['first partial confirmation not completed']
        data={'draft_id':d['draft_id'],'expected_revision':d['revision'],'confirmation_id':uuid4().hex,
              'selections':[{'candidate_id':r['candidate_id'],'count':r['remaining']} for r in d['candidates'] if r['remaining']]}
        record=s.ai.imports.commit(data);s.wait(record['request_id']);tasks=s.snapshot()['tasks']
        if len(tasks)!=5:errors.append('remaining confirmation not exactly 5 total trips')
        sources=[(r['source']['candidate_id'],r['source']['occurrence_index']) for r in tasks]
        if len(set(sources))!=5:errors.append('duplicate occurrence identity')
        write(s.directory/'remaining_confirmation.json',{'actor':'test_harness_confirmation','payload':data,'operation':record})
    return errors
