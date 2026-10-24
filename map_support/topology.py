"""Iterative low-link analysis; connectivity is NOT a multi-agent solvability proof."""
from dataclasses import dataclass
from hashlib import sha256


@dataclass(frozen=True)
class Topology:
    map_hash: str
    free_cells: int
    cutpoints: frozenset
    bridges: tuple
    corridors: tuple
    dead_ends: frozenset

    def parking_risk(self, p):
        return int(p in self.cutpoints)

    def public(self):
        return {'map_hash': self.map_hash, 'free_cells': self.free_cells,
                'cutpoints': len(self.cutpoints), 'bridges': len(self.bridges),
                'corridors': len(self.corridors), 'dead_ends': len(self.dead_ends),
                'longest_corridor': max((len(c) for c in self.corridors), default=0),
                'note': '拓扑风险诊断，不是多机可解证明'}


def analyze(warehouse):
    graph = {p: warehouse.neighbors(p) for y in range(warehouse.height)
             for x in range(warehouse.width) if warehouse.is_open(p := (x,y))}
    discovery, low, parent, children = {}, {}, {}, {}
    cuts, bridges = set(), []
    clock = 0
    for root in graph:
        if root in discovery:
            continue
        discovery[root] = low[root] = clock
        clock += 1
        parent[root] = None
        children[root] = 0
        stack = [(root, iter(graph[root]))]
        while stack:
            p, it = stack[-1]
            q = next(it, None)
            if q is not None:
                if q not in discovery:
                    parent[q] = p
                    children[p] += 1
                    children[q] = 0
                    discovery[q] = low[q] = clock
                    clock += 1
                    stack.append((q, iter(graph[q])))
                elif q != parent[p]:
                    low[p] = min(low[p], discovery[q])
            else:
                stack.pop()
                q = parent[p]
                if q is None:
                    if children[p] > 1:
                        cuts.add(p)
                else:
                    low[q] = min(low[q], low[p])
                    if parent[q] is not None and low[p] >= discovery[q]:
                        cuts.add(q)
                    if low[p] > discovery[q]:
                        bridges.append((q,p))
    used, corridors = set(), []
    edge = lambda a,b: tuple(sorted((a,b)))
    for p, neighbors in graph.items():
        if len(neighbors) == 2:
            continue
        for q in neighbors:
            if edge(p,q) in used:
                continue
            path, previous, current = [p], p, q
            used.add(edge(p,q))
            while True:
                path.append(current)
                if len(graph[current]) != 2:
                    break
                nxt = next(v for v in graph[current] if v != previous)
                if edge(current,nxt) in used:
                    break
                used.add(edge(current,nxt))
                previous, current = current, nxt
            if len(path) >= 4:
                corridors.append(tuple(path))
    identity = repr((warehouse.width, warehouse.height, sorted(warehouse.blocked))).encode()
    return Topology(sha256(identity).hexdigest(), len(graph), frozenset(cuts),
                    tuple(bridges), tuple(corridors),
                    frozenset(p for p,ns in graph.items() if len(ns)==1))
