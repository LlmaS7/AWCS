from harness import *
from locations import build_locations

def prepare(directory):
    directory=Path(directory); directory.mkdir(parents=True,exist_ok=True)
    fixtures=[]
    archive=PROJECT/'.temp/testing/datasets/maps'
    for idx,(shape,seed,target) in enumerate([('rectangle',20261018,3),('rooms',20261019,1),('l',20261018,5)],1):
        path=archive/f'{shape}_{seed}.json'
        replacement=not path.exists()
        if replacement:
            from map_studio.generator import generate
            generated=generate(width=64,height=48,robots=16,seed=seed,shape=shape)
            definition=generated.get('map',generated) if isinstance(generated,dict) else generated[0]
        else:definition=read(path)
        definition=deepcopy(definition); definition['locations']={'shelves':[],'deliveries':[
            {'id':'D1','name':'1号配送点','aliases':['西侧收货区']},
            {'id':'D2','name':'2号配送点','aliases':['复核台']}]}
        rows=definition['grid']['rows'];used=set()
        order=[target]+[i for i in range(1,len(definition['points']['pickups'])+1) if i!=target]
        mapping=[]
        for pidx in order:
            x,y=definition['points']['pickups'][pidx-1]
            adjacent=[(a,b) for a,b in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)) if 0<=b<len(rows) and 0<=a<len(rows[b]) and rows[b][a]=='R' and (a,b) not in used]
            if not adjacent:continue
            cell=adjacent[0];used.add(cell);mapping.append(pidx)
            n=len(mapping);name='四号货架' if n==1 else f'登记货架{n}'
            aliases=['4号货架','四号架','蓝色货架'] if n==1 else (['东侧货架'] if idx==3 and n in (2,3) else [f'货架别名{n}'])
            definition['locations']['shelves'].append({'id':f'S{n}','name':name,'aliases':aliases,'pickup_id':f'P{pidx:02}', 'cells':[list(cell)]})
            if len(mapping)==3:break
        if len(mapping)<3:raise RuntimeError('insufficient shelf-adjacent pickup fixture')
        locations=build_locations(definition)
        scenario={'version':'0.4_preview','seed':seed,'map_definition':definition,'robot_count':4,'events':[],
                  'planning_profile':{'mode':'scalable_full','coupling':'off','seconds':3.0,'candidates':4,'window':32,'execute':4}}
        scenario_path=directory/f'M{idx:02}.json';write(scenario_path,scenario)
        fixtures.append({'id':f'M{idx:02}','scenario':str(scenario_path),'source':str(path),'replacement':replacement,
                         'sha256':digest(scenario_path),'pickup':f'P{mapping[0]:02}','other':f'P{mapping[1]:02}',
                         'locations':locations,'shape':shape,'seed':seed})
    write(directory/'manifest.json',fixtures);return fixtures
