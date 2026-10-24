"""Dependency-free controlled grid generator. No simulation, UI or credentials.

The immutable JSON snapshot is the product; rerunning a seed also requires the
same generator version and parameters. Integration validates business identities
with the consumer's own map_format module (in a separate process).
"""
from collections import deque
from random import Random

VERSION = 'awcs-outline-v1'
SHAPES = {'rectangle': '规整仓库', 'l': 'L 形仓库', 't': 'T 形仓库',
          'u': 'U 形仓库', 'courtyard': '庭院仓库', 'rooms': '组合房间', 'random': '随机组合'}


def adjacent(p):
    x, y = p
    return ((x-1,y), (x+1,y), (x,y-1), (x,y+1))


def integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name} 须为 {low}～{high} 的整数')
    return value


def connected(rows, start):
    width, height = len(rows[0]), len(rows)
    seen, todo = {start}, deque([start])
    while todo:
        for x,y in adjacent(todo.popleft()):
            if 0 <= x < width and 0 <= y < height and rows[y][x] == '.' and (x,y) not in seen:
                seen.add((x,y)); todo.append((x,y))
    return seen


def generate(width=64, height=64, robots=16, seed=20261018, shape='l',
             aisle=3, density=65, obstacles=20):
    width = integer(width, '宽度', 48, 128)
    height = integer(height, '高度', 40, 96)
    robots = integer(robots, '机器人上限', 1, 64)
    seed = integer(seed, '种子', 0, 2147483647)
    aisle = integer(aisle, '货架间净通道宽度', 2, 6)
    density = integer(density, '货架候选填充率', 25, 85)
    obstacles = integer(obstacles, '随机障碍数量', 0, 80)
    if shape not in SHAPES:
        raise ValueError('未知轮廓')
    rng = Random(seed)
    params = dict(width=width, height=height, robots=robots, seed=seed, shape=shape,
                  aisle=aisle, density=density, obstacles=obstacles)
    footprint = {(x,y) for y in range(2,height-2) for x in range(2,width-2)}
    if shape == 'l':
        footprint = {(x,y) for x,y in footprint if x < int(width*.57) or y >= int(height*.43)}
    elif shape == 't':
        footprint = {(x,y) for x,y in footprint if y < int(height*.43) or int(width*.25) <= x < int(width*.75)}
    elif shape == 'u':
        footprint = {(x,y) for x,y in footprint if not (int(width*.34) <= x < int(width*.66) and y < int(height*.55))}
    elif shape == 'courtyard':
        footprint = {(x,y) for x,y in footprint if not (int(width*.38) <= x < int(width*.62) and int(height*.34) <= y < int(height*.58))}
    elif shape in ('rooms','random'):
        a,b = (rng.randint(24,35)/100, rng.randint(65,76)/100) if shape == 'random' else (.40,.60)
        top_end = rng.randint(38,46)/100 if shape == 'random' else .43
        bottom_start = rng.randint(52,60)/100 if shape == 'random' else .56
        footprint = {(x,y) for x,y in footprint if (int(width*a) <= x < int(width*b))
                     or (x < int(width*.65) and y < int(height*top_end))
                     or (x >= int(width*.24) and y >= int(height*bottom_start))}
    rows = [['~']*width for _ in range(height)]
    for x,y in footprint:
        rows[y][x] = '.' if all(q in footprint for q in adjacent((x,y))) else '#'

    # Adjacent prefix, possibly two or three serpentine rows, in a clear apron.
    # Reserve an approach on both sides; idle vehicles never start in rack aisles.
    starts = None
    preferred = [height-5,5] + list(range(height-6,5,-1))
    for y in preferred:
        run = []
        candidates = []
        for x in range(4,width-3):
            if all(rows[yy][x] == '.' for yy in range(max(0,y-3),min(height,y+3))):
                run.append(x)
            else:
                if len(run) >= 8: candidates.append(run)
                run = []
        if len(run) >= 8: candidates.append(run)
        for run in sorted(candidates, key=len, reverse=True):
            if len(run)*3 < robots: continue
            starts = []
            for index in range(3):
                xs = run if index%2 == 0 else list(reversed(run))
                starts.extend((x,y-index) for x in xs)
            starts = starts[:robots]
            break
        if starts: break
    if not starts:
        raise ValueError('轮廓没有足够大的相邻出发区，请增加尺寸或降低机器人上限')

    protected = set(starts)
    def guard(points, radius=1):
        for x,y in points:
            for dy in range(-radius,radius+1):
                for dx in range(-radius,radius+1):
                    protected.add((x+dx,y+dy))
    guard(starts,2)
    floor = {(x,y) for x,y in footprint if rows[y][x] == '.'}
    candidates = sorted(p for p in floor if p not in protected
                        and all(q in floor for q in adjacent(p)))
    deliveries = []
    for i in range(1,7):
        tx,ty = width*i/7,height-6
        available = [p for p in candidates if p not in protected]
        if not available: break
        point = min(available, key=lambda p:(abs(p[0]-tx)+abs(p[1]-ty),p))
        deliveries.append(point);guard([point],2)

    parking = list(starts)
    bay = max(1,(robots+15)//16)
    for target in ((5,height//3),(width-6,height//3),(5,height-8),(width-6,7)):
        groups = []
        for x,y in candidates:
            for dx,dy in ((1,0),(0,1)):
                group = [(x+dx*i,y+dy*i) for i in range(bay)]
                if all(p in floor and p not in protected and all(q in floor for q in adjacent(p)) for p in group):
                    groups.append(group)
        if not groups: raise ValueError('待命区不足，请增加尺寸或减少机器人数量')
        group = min(groups,key=lambda g:(abs(g[0][0]-target[0])+abs(g[0][1]-target[1]),g))
        parking.extend(group);guard(group,1)

    # Explicit cross aisles stay clear where they intersect the footprint.
    for x,y in floor:
        if abs(x-width//2) <= aisle//2 or abs(y-height//2) <= aisle//2:
            protected.add((x,y))
    pickups,shelves = [],[]
    for y in range(7,height-7,3+aisle):
        for x in range(5,width-7,4+aisle):
            if len(pickups) >= 128 or rng.randrange(100) >= density: continue
            rw,rh = rng.choice((3,4)),rng.choice((2,3))
            cells = [(xx,yy) for yy in range(y,y+rh) for xx in range(x,x+rw)]
            border = [(xx,yy) for yy in range(y-1,y+rh+1) for xx in range(x-1,x+rw+1)]
            if any(p not in floor or p in protected or rows[p[1]][p[0]] != '.' for p in border): continue
            for xx,yy in cells: rows[yy][xx] = 'R'
            pickup = (x,y-1);pickups.append(pickup);guard([pickup],1)
            i = len(pickups)
            shelves.append(dict(id=f'S{i:02}',name=f'{i}号货架',aliases=[],pickup_id=f'P{i:02}',
                                cells=[list(p) for p in cells]))
    if not pickups: raise ValueError('当前参数未形成有效货架，请增加尺寸或调整种子')
    if len(connected(rows,starts[0])) != sum(row.count('.') for row in rows):
        raise ValueError('货架布局未通过连通检查，请调整参数')

    # Freeze clutter here, instead of changing geometry on every simulation seed.
    clutter = [p for p in sorted(floor) if p not in protected and rows[p[1]][p[0]] == '.'
               and all(q in floor for q in adjacent(p))]
    rng.shuffle(clutter)
    actual = 0
    open_count = sum(row.count('.') for row in rows)
    for x,y in clutter:
        if actual >= obstacles: break
        rows[y][x] = 'O'
        if len(connected(rows,starts[0])) == open_count-1:
            actual += 1;open_count -= 1
        else: rows[y][x] = '.'
    return dict(format='sditadc-map',version=1,
                name=f'{SHAPES[shape]} {width}×{height} · {robots}台'+('（实验）' if robots>32 else ''),
                grid=dict(width=width,height=height,rows=[''.join(row) for row in rows]),
                points={kind:[list(p) for p in group] for kind,group in
                        [('starts',starts),('parking',parking),('pickups',pickups),('deliveries',deliveries)]},
                robots=dict(default_count=min(robots,16),max_count=robots),
                random_obstacles=dict(count=0),locations=dict(shelves=shelves),
                metadata=dict(generator=VERSION,seed=seed,parameters=params,obstacles_placed=actual,
                              experimental=robots>32,parking_layout='spawn-plus-four-small-bays',
                              note='静态连通检查；多机器人可解性须另行试运行，有限试运行不是通用保证'))
