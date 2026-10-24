"""Inclusive integer time intervals; persistent endpoints use infinity.

An edge key (p,q) describes the FORBIDDEN direction of travel at arrival time.
Reserving an actual p->q move therefore blocks the reverse q->p edge.
"""
from bisect import bisect_right

INF = 10**12


def merged(values):
    result = []
    for a,b in sorted(values):
        if result and a <= result[-1][1]+1:
            result[-1] = (result[-1][0], max(result[-1][1],b))
        else:
            result.append((a,b))
    return result


class Reservations:
    def __init__(self):
        # 顶点表登记格子占用区间；边表登记禁止通行的方向及到达时间。
        self.vertices = {}
        self.edges = {}
        self._safe = {}

    def clone(self):
        other = Reservations()
        other.vertices = {p: list(v) for p,v in self.vertices.items()}
        other.edges = {p: list(v) for p,v in self.edges.items()}
        return other

    def block(self, p, start, end):
        self.vertices[p] = merged(self.vertices.get(p,[]) + [(start,end)])
        # 占用变化后，之前计算的安全区间补集失效。
        self._safe.clear()

    def block_edge(self, p, q, start, end):
        self.edges[p,q] = merged(self.edges.get((p,q),[]) + [(start,end)])

    def add_path(self, path, persistent=True):
        # 将连续停留合并成闭区间预约，移动与等待都会占用格子。
        begin = 0
        for t in range(1,len(path)+1):
            if t == len(path) or path[t] != path[begin]:
                self.block(path[begin],begin,t-1)
                begin = t
            if t < len(path) and path[t-1] != path[t]:
                # 本车在 t 时刻从 A 到 B，禁止后车同一步从 B 到 A，避免对向换位。
                self.block_edge(path[t],path[t-1],t,t)
        # 到达停车终点后仍占据该格，不能把已完成路线的机器人视为消失。
        if persistent:
            self.block(path[-1],len(path)-1,INF)

    def safe_intervals(self, p, horizon):
        key = p,horizon
        if key in self._safe:
            return self._safe[key]
        # 对占用闭区间取补集，得到规划范围 [0, horizon] 内可停留的安全区间。
        intervals, start = [], 0
        for a,b in self.vertices.get(p,[]):
            if a > start:
                intervals.append((start,min(horizon,a-1)))
            start = max(start,b+1)
            if start > horizon:
                break
        if start <= horizon:
            intervals.append((start,horizon))
        self._safe[key] = [(a,b) for a,b in intervals if 0<=a<=b<=horizon]
        return self._safe[key]

    def next_edge_time(self, p, q, t):
        # 若到达时刻命中禁行边区间，推迟到区间结束后；调用方再校验格子安全性。
        for a,b in self.edges.get((p,q),[]):
            if t < a:
                break
            if t <= b:
                t = b+1
        return t

    @classmethod
    def from_constraints(cls, constraints):
        result = cls()
        for c in constraints:
            if c[0]=='v':
                result.block(c[2],c[1],c[1])
            else:
                result.block_edge(c[2],c[3],c[1],c[1])
        return result
