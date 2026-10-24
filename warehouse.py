"""Reproducible shelves, static clutter, service bays and off-aisle parking."""
from collections import deque, OrderedDict
from array import array
from copy import deepcopy
from random import Random
from config import DEFAULT_MAP
from map_format import load_map, validate_map, robot_limits, integer
from models import Position
from locations import build_locations


class Warehouse:
    def __init__(self, seed: int, map_id=DEFAULT_MAP, definition=None, robot_count=None):
        self.seed = seed
        self.map_id = map_id
        self.definition = validate_map(definition) if definition is not None else load_map(map_id)
        self.name = self.definition["name"]
        self.locations = build_locations(self.definition)
        grid = self.definition["grid"]
        self.width, self.height = grid["width"], grid["height"]
        cells = [(x, y, c) for y, row in enumerate(grid["rows"]) for x, c in enumerate(row)]
        self.walls = {(x, y) for x, y, c in cells if c == "#"}
        self.voids: set[Position] = {(x, y) for x, y, c in cells if c == "~"}
        self.shelves: set[Position] = {(x, y) for x, y, c in cells if c == "R"}
        self.obstacles: set[Position] = {(x, y) for x, y, c in cells if c == "O"}
        points = self.definition["points"]
        for group in ("parking", "starts", "pickups", "deliveries"):
            setattr(self, group, [tuple(p) for p in points[group]])
        self.default_robots, self.max_robots = robot_limits(self.definition)
        self.robot_count = integer(self.default_robots if robot_count is None else robot_count,
                                   "机器人数量", 1, self.max_robots)
        self.start_pool = self.starts
        self.starts = self.start_pool[:self.robot_count]
        self.blocked = self.walls | self.shelves | self.obstacles | self.voids
        # Protect endpoints and their immediate approaches.
        protected = set(self.parking + self.pickups + self.deliveries)
        protected |= {q for p in list(protected) for q in self.adjacent(p)}
        clutter = self.definition.get("random_obstacles", {})
        count = clutter.get("count", 0)
        left, top, right, bottom = clutter.get("region", [0, 0, self.width, self.height])
        excluded = self.blocked | protected
        candidates = [(x, y) for y in range(top, bottom) for x in range(left, right)
                      if (x, y) not in excluded] if count else []
        rng = Random(seed)
        rng.shuffle(candidates)
        self.random_count = 0
        for p in candidates:
            if self.random_count >= count:
                break
            self.blocked.add(p)
            if len(self.reachable(self.starts[0])) == self.width * self.height - len(self.blocked):
                self.obstacles.add(p)
                self.random_count += 1
            else:
                self.blocked.remove(p)
        self._distances = OrderedDict()
        self._topology = None

    @property
    def topology(self):
        if self._topology is None:
            from map_support.topology import analyze
            self._topology = analyze(self)
        return self._topology

    def export_map(self):
        """Freeze the realized geometry, including seeded clutter, for durable replay."""
        result = deepcopy(self.definition)
        rows = [list(row) for row in result["grid"]["rows"]]
        for x, y in self.obstacles:
            rows[y][x] = "O"
        result["grid"]["rows"] = ["".join(row) for row in rows]
        result["random_obstacles"] = {"count": 0}
        return result

    @staticmethod
    def adjacent(p):
        x, y = p
        return ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y))

    def is_open(self, p):
        return 0 <= p[0] < self.width and 0 <= p[1] < self.height and p not in self.blocked

    def neighbors(self, p):
        return [q for q in self.adjacent(p) if self.is_open(q)]

    def reachable(self, start):
        distances = {start: 0}
        queue = deque([start])
        while queue:
            p = queue.popleft()
            for q in self.neighbors(p):
                if q not in distances:
                    distances[q] = distances[p] + 1
                    queue.append(q)
        return distances

    def distance(self, start, goal):
        if not self.is_open(start) or not self.is_open(goal):
            return 10**6
        if goal not in self._distances:
            values = array('i', [-1]) * (self.width*self.height)
            values[goal[1]*self.width+goal[0]] = 0
            queue = deque([goal])
            while queue:
                p = queue.popleft()
                value = values[p[1]*self.width+p[0]]+1
                for q in self.neighbors(p):
                    index = q[1]*self.width+q[0]
                    if values[index]<0:
                        values[index] = value
                        queue.append(q)
            self._distances[goal] = values
            # A memory budget, not a goal count that thrashes on large fleets.
            limit = max(16,min(512,(32*1024*1024)//(4*self.width*self.height)))
            if len(self._distances)>limit:
                self._distances.popitem(last=False)
        self._distances.move_to_end(goal)
        value = self._distances[goal][start[1]*self.width+start[0]]
        return value if value>=0 else 10**6

