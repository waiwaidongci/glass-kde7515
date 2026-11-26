"""按复测名额在多个校准方案的待查集合间做最大化最低覆盖率的选择。

输入为每个方案编号到待查测件编号集合的映射，以及下一班复测名额上限。
选择规则（确定性、可复算）：

1. 仅考虑存在待查件的方案；若没有任何方案有待查件，交空单。
2. 逐名额贪心：每一步选择一个尚未入选的测件，使所有待查方案的
   已覆盖占比最小值尽可能大；占比向量按方案编号升序参与并列判定。
3. 提升幅度相同时，取可使覆盖率向量字典序最优的测件；仍相同则取
   测件编号最靠前者。
4. 名额用尽，或所有待查测件都已入选时结束。

即便各方案的待查集合互不相交，名额也会按同一比较口径在方案间轮流
分配，使最低覆盖率随名额逐步抬高，而不是空转。

返回入选测件编号（升序）和每个待查方案的覆盖统计，便于交班复核。
"""


def build_retest_plan(pending_by_plan, quota):
    if not isinstance(quota, int) or isinstance(quota, bool) or quota <= 0:
        raise ValueError('复测名额须为正整数')

    pending_by_plan = {
        plan_id: set(ids)
        for plan_id, ids in pending_by_plan.items()
        if ids
    }
    if not pending_by_plan:
        return {'quota': quota, 'items': [], 'plan_coverage': [], 'min_coverage_pct': None}

    plan_ids = sorted(pending_by_plan)
    sizes = {plan_id: len(pending_by_plan[plan_id]) for plan_id in plan_ids}
    universe = sorted(set().union(*pending_by_plan.values()))
    # 增量维护各方案已覆盖件数，避免每个名额都重算集合交集。
    covered_count = {plan_id: 0 for plan_id in plan_ids}
    chosen = set()
    while len(chosen) < quota and len(chosen) < len(universe):
        best_key = None
        best_item = None
        for item_id in universe:
            if item_id in chosen:
                continue
            trial = tuple(
                (covered_count[plan_id] + (1 if item_id in pending_by_plan[plan_id] else 0))
                / sizes[plan_id]
                for plan_id in plan_ids
            )
            # 先比最小覆盖率，再比覆盖率向量字典序，最后比测件编号。
            key = (min(trial), trial)
            if best_key is None or key > best_key or (key == best_key and item_id < best_item):
                best_key = key
                best_item = item_id
        chosen.add(best_item)
        for plan_id in plan_ids:
            if best_item in pending_by_plan[plan_id]:
                covered_count[plan_id] += 1

    items = sorted(chosen)
    plan_coverage = []
    for plan_id in plan_ids:
        covered = covered_count[plan_id]
        plan_coverage.append({
            'plan_id': plan_id,
            'pending_count': sizes[plan_id],
            'covered_count': covered,
            'coverage_pct': round(100 * covered / sizes[plan_id], 6),
        })
    return {
        'quota': quota,
        'items': items,
        'plan_coverage': plan_coverage,
        'min_coverage_pct': round(min(row['coverage_pct'] for row in plan_coverage), 6),
    }
