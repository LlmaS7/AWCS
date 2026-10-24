"""Polynomial lexicographic matching, including unassigned dummy columns.

The dynamically derived integer radices dominate the COMPLETE lower objective
ranges. No fixed penalty may let ETA override a task priority or a preference.
"""


def match(slots, tasks, cost, preference=None):
    from scheduler import minimum_assignment
    tasks = sorted(tasks, key=lambda t: t.id)
    # 字典序目标：5～1级分配数量、可选偏好惩罚、预计完成时间、创建时刻。
    dimensions = 8 if preference else 7
    zero = (0,) * dimensions
    if not slots or not tasks:
        return {}, zero
    vectors = []
    for slot in slots:
        row = []
        for task in tasks:
            eta = cost(slot, task)
            # 不符合人工指定等约束的关系不可选，不能用距离优势抵消业务约束。
            if eta is None or eta >= 10**6:
                row.append(None)
                continue
            if not isinstance(eta, int):
                raise ValueError('Matching ETA must be an integer number of ticks')
            value = [0] * dimensions
            # 求解目标取最小值；某级每多分配一项，该级计数减一。
            value[5-task.priority] = -1
            # 各级分配数量相同后，再比较偏好，最后比较 ETA 和创建时刻。
            if preference:
                value[5] = preference(slot, task)
            value[-2:] = [eta, task.created_at]
            row.append(tuple(value))
        # 每行对应一个机器人槽位；补足空分配列，允许机器人暂时不接任务。
        vectors.append(row + [zero] * len(slots))
    # 按行平移不改变最优匹配，再计算整个匹配在各目标维度上的变化上界。
    lows = [tuple(min(v[d] for v in row if v is not None) for d in range(dimensions))
            for row in vectors]
    ranges = [sum(max(v[d] for v in row if v is not None)-low[d]
                  for row, low in zip(vectors, lows)) for d in range(dimensions)]
    # 从低位向高位构造权重，保证高位改善一单位能压过全部低位变化。
    # 因此长距离不会挤掉高等级任务，无需人为猜测固定优先级系数。
    weights = [1] * dimensions
    for d in range(dimensions-2, -1, -1):
        weights[d] = weights[d+1] * (ranges[d+1]+1)
    encode = lambda v, low: sum((a-b)*w for a,b,w in zip(v,low,weights))
    finite = [[None if v is None else encode(v,low) for v in row]
              for row,low in zip(vectors,lows)]
    # 禁用代价高于任意全可行匹配的总代价；空分配列保证始终有可行选择。
    forbidden = 1 + sum(max(c for c in row if c is not None) for row in finite)
    # 匈牙利算法求整个矩阵的匹配；最优性仅针对本轮给定约束和代价。
    columns = minimum_assignment([[forbidden if c is None else c for c in row] for row in finite])
    pairs, score = {}, [0] * dimensions
    for i,j in enumerate(columns):
        # 空分配列不生成任务归属；score 保留未编码的分层目标，便于诊断。
        if j >= len(tasks):
            continue
        value = vectors[i][j]
        if value is None:
            raise AssertionError('A forbidden matching edge was selected')
        pairs[slots[i].robot_id] = tasks[j].id
        score = [a+b for a,b in zip(score,value)]
    return pairs, tuple(score)
