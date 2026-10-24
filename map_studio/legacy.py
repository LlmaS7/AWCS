"""Seeded warehouse/irregular maps with adjacent spawn prefixes and service bays."""
from random import Random


def generate(width=64, height=64, robots=32, seed=20261018, irregular=True):
    if width<robots+6 or height<24:
        raise ValueError('地图须容纳相邻起点及独立通道')
    rng = Random(seed)
    rows = [['#' if x in (0,width-1) or y in (0,height-1) else '.'
             for x in range(width)] for y in range(height)]
    pickups,shelves = [],[]
    for y in range(7,height-8,7):
        for x in range(4,width-7,8):
            rw = rng.randint(3,5) if irregular else 4
            rh = rng.randint(2,3) if irregular else 3
            cells = []
            for dy in range(rh):
                for dx in range(rw):
                    if irregular and dx==rw-1 and dy==rh-1 and rng.random()<.6:
                        continue
                    rows[y+dy][x+dx] = 'R'
                    cells.append([x+dx,y+dy])
            if len(pickups)<128:
                pickups.append([x,y-1])
                i = len(pickups)
                shelves.append({'id':f'S{i:02}','name':f'{i}号货架','aliases':[],
                                'pickup_id':f'P{i:02}','cells':cells})
    starts = [[x,2] for x in range(2,robots+2)]
    deliveries = [[x,height-4] for x in range(4,width-4,max(4,(width-8)//8))]
    # Retain one slot per spawn, plus four small off-aisle waiting bays.
    # 32 robots -> 40 slots; 64 robots -> 80. No whole-perimeter parking.
    bay_size = max(1,(robots+15)//16)
    parks = starts + [[1,height//2+i] for i in range(bay_size)]
    parks += [[width-2,height//2+i] for i in range(bay_size)]
    for center in (width//3,2*width//3):
        parks += [[center-bay_size//2+i,height-2] for i in range(bay_size)]
    return {'format':'sditadc-map','version':1,
            'name':f'{"不规则" if irregular else "规整"}协作仓库 {width}×{height} · {robots}台'+('（实验）' if robots>32 else ''),
            'grid':{'width':width,'height':height,'rows':[''.join(row) for row in rows]},
            'points':{'starts':starts,'parking':parks,'pickups':pickups,'deliveries':deliveries},
            'robots':{'default_count':min(8,robots),'max_count':robots},
            'random_obstacles':{'count':24 if irregular else 0,'region':[2,5,width-2,height-6]},
            'locations':{'shelves':shelves},
            'metadata':{'generator':'awcs-grid-v2','seed':seed,'experimental':robots>32,
                        'parking_layout':'spawn-plus-four-waiting-bays',
                        'note':'起点相邻，静态随机障碍保持连通；非多机可解证明'}}
