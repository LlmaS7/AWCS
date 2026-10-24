"""Independent facts, schemas and trajectory checks (no production normalize)."""
from collections import Counter

def multiset(rows):
    return Counter((x['pickup_id'],x['delivery_id'],x.get('priority',2)) for x in rows)

def schema_errors(value,schema,path='$'):
    types=schema.get('type'); types=[types] if isinstance(types,str) else types
    if types:
        checks={'object':lambda:type(value) is dict,'array':lambda:type(value) is list,
                'integer':lambda:type(value) is int,'string':lambda:type(value) is str,
                'null':lambda:value is None,'boolean':lambda:type(value) is bool}
        if not any(checks[t]() for t in types):return [path+':type']
    errors=[]
    if 'enum' in schema and value not in schema['enum']:errors.append(path+':enum')
    if isinstance(value,dict):
        props=schema.get('properties',{})
        errors += [path+':missing:'+k for k in schema.get('required',[]) if k not in value]
        if schema.get('additionalProperties') is False: errors += [path+':unknown:'+k for k in value if k not in props]
        for k,v in value.items():
            if k in props:errors+=schema_errors(v,props[k],path+'.'+k)
    if isinstance(value,list):
        if len(value)<schema.get('minItems',0) or len(value)>schema.get('maxItems',10**9):errors.append(path+':length')
        for i,v in enumerate(value):errors+=schema_errors(v,schema.get('items',{}),path+f'[{i}]')
    if type(value) is int and not schema.get('minimum',-10**20)<=value<=schema.get('maximum',10**20):errors.append(path+':range')
    return errors

def canonical(value):
    import re
    if not isinstance(value,str):return value
    match=re.fullmatch(r'([TPRD])0*([1-9][0-9]*)',value,re.I)
    return (match[1].upper(),int(match[2])) if match else value

def query_satisfied(trace,name,args,domain_error=None):
    for t in trace:
        if t['name']!=name:continue
        if any(canonical(t.get('arguments',{}).get(k))!=canonical(v) for k,v in args.items()):continue
        if 'result' in t:return True
        if domain_error and t.get('error')==domain_error:return True
    return False

def resolve_target(explicit,associated,ambiguous=False):
    return explicit if explicit else (None if ambiguous else associated)

def claim_errors(claims,facts):
    return [c for c in claims if c.get('fact') not in facts or c.get('value')!=facts[c['fact']]]

def receipt_counts(receipt):
    return Counter(a.get('outcome','unknown') for a in receipt.get('actions',[]))

def occurrence_errors(actual,expected):
    return Counter(tuple(x) for x in actual)!=Counter(tuple(x) for x in expected)

def network_failed(calls,expected_stop=False):
    return any(c['state']=='error' and not (expected_stop and c.get('error_type')=='Stopped') for c in calls)

def evidence_verdict(protocol,business,process,network,pending,fixture_errors,guard_errors):
    established=protocol+[e for e in business if e.startswith('unauthorized') or e=='write proposal without authorization']
    if guard_errors:return 'FAIL','UNEXPECTED_SIDE_EFFECT'
    if fixture_errors:
        return ('FAIL' if established else 'TEST_INVALID'),'TEST_FIXTURE_INVALID'
    return classify(model_errors=established if network else protocol+business+process,
                    network=network,reviewed=not pending),None

def process_errors(calls,trace,policy):
    errors=[]; queried=[]
    # Provider responses give ordering including proposals rejected before tool().
    for request in calls:
        request_id=request.get('context',{}).get('request_id')
        if request_id is not None:queried=[x for x in queried if x.get('request_id')==request_id]
        for call in request.get('response',{}).get('tool_calls',[]):
            import json
            name=call['function']['name']
            try:args=json.loads(call['function']['arguments'])
            except ValueError:continue
            if name in ('get_locations','get_status','get_metrics'):
                matches=[x for x in trace if x['name']==name and x['arguments']==args and 'result' in x and (request_id is None or x.get('request_id')==request_id)]
                queried.extend(matches)
            if name=='create_tasks':
                locations=[x['result'] for x in queried if x['name']=='get_locations']
                if not locations:errors.append('missing current locations before creation')
                if policy!='direct_ids' and not any('shelf' in x for x in locations):errors.append('missing shelf mapping before creation')
            if name in ('assign_task','set_task_preference','release_task_assignment','copy_task'):
                states=[x['result'] for x in queried if x['name']=='get_status']
                tid=canonical(args.get('task_id'));rid=canonical(args.get('robot_id'))
                task_found=any(any(canonical(t['task_id'])==tid for t in state.get('tasks',[])) for state in states)
                robot_found=rid is None or any(any(canonical(r['robot_id'])==rid for r in state.get('robots',[])) for state in states)
                if not task_found or not robot_found:errors.append('missing current target/robot state before '+name)
    return errors

def audit_trajectory(frames,mapdata):
    errors=[]; blocked={tuple(p) for k in ('walls','shelves','obstacles','voids') for p in mapdata[k]}
    previous=None; ids=None
    for f in frames:
        robots={r['id']:r for r in f['robots']}; tasks={t['id']:t for t in f['tasks']}
        if ids is None:ids=set(robots)
        if set(robots)!=ids:errors.append('robot set changed')
        positions=[tuple(r['position']) for r in robots.values()]
        if len(set(positions))!=len(positions):errors.append('vertex collision')
        if previous and f['tick']!=previous['tick']+1:errors.append('tick gap')
        oldrobots={r['id']:r for r in previous['robots']} if previous else {}
        for rid,r in robots.items():
            p=tuple(r['position'])
            if p in blocked or not (0<=p[0]<mapdata['width'] and 0<=p[1]<mapdata['height']):errors.append('blocked/outside')
            if r['loaded'] != (r['phase'] in ('to_delivery','unloading')):errors.append('phase/load mismatch')
            t=tasks.get(r['task_id'])
            if r['phase'] in ('picking','unloading'):
                if not t or p!=tuple(t['pickup' if r['phase']=='picking' else 'delivery']):errors.append('wrong service point')
            if t and t['assignment_mode']=='forced' and t['assignment_robot_id']!=rid:errors.append('forced robot mismatch')
            if rid in oldrobots:
                old=oldrobots[rid]; q=tuple(old['position'])
                if abs(p[0]-q[0])+abs(p[1]-q[1])>1:errors.append('jump')
                if old['phase'] in ('picking','unloading') and old['service_left']>1:
                    if p!=q or r['task_id']!=old['task_id'] or r['phase']!=old['phase'] or r['service_left']!=old['service_left']-1:
                        errors.append('service interrupted')
                for oid,other in oldrobots.items():
                    if oid!=rid and oid in robots and p==tuple(other['position']) and tuple(robots[oid]['position'])==q and p!=q:errors.append('edge swap')
        previous=f
    return sorted(set(errors))

def classify(model_errors=(),network=False,invalid=False,complete=True,reviewed=False):
    if model_errors:return 'FAIL'
    if invalid:return 'TEST_INVALID'
    if network or not complete:return 'INCONCLUSIVE'
    return 'PASS' if reviewed else 'INCONCLUSIVE'
