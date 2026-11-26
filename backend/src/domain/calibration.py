"""按台校准修正、超差峰识别与谷间待查测件。

每套校准方案按测径台给出修正量，分析口径与既有 KDE 流程保持一致：
1. 沿用台账原有的场次 fit / holdout 分组，用修正后的拟合场次做核中心重选带宽；
2. 固定入选带宽后，用全批修正口径重构 KDE，解析导数定位峰谷；
3. 峰位落在公差区间之外的为超差峰，该峰相邻两谷之间（边界峰的外侧取无穷）
   的全部实测测件，列为这套方案的待查件。
"""

import math

import numpy as np

from .kde import GaussianKDE, select_bandwidth
from .measurements import DIAMETER_MAX, DIAMETER_MIN
from .modes import find_turning_points


OFFSET_MIN = -5.0
OFFSET_MAX = 5.0


def normalize_offsets(offsets):
    if not isinstance(offsets, dict) or not offsets:
        raise ValueError('校准方案必须至少给出一个测径台的修正量')
    checked = {}
    for bench, offset in offsets.items():
        if not isinstance(bench, str) or not bench.strip():
            raise ValueError('测径台编号不能为空')
        if type(offset) not in (int, float) or not math.isfinite(offset) or not OFFSET_MIN <= offset <= OFFSET_MAX:
            raise ValueError(f'测径台 {bench} 的修正量须为 {OFFSET_MIN:g} 至 {OFFSET_MAX:g} mm 的有限数值')
        checked[bench.strip()] = float(offset)
    return checked


def apply_offsets(rows, offsets):
    benches = {row['bench'] for row in rows}
    unknown = set(offsets) - benches
    if unknown:
        raise ValueError('校准方案包含台账中不存在的测径台：' + '、'.join(sorted(unknown)))
    missing = benches - set(offsets)
    if missing:
        raise ValueError('校准方案缺少测径台修正量：' + '、'.join(sorted(missing)))
    calibrated = [
        {**row, 'raw_diameter_mm': row['diameter_mm'],
         'diameter_mm': row['diameter_mm'] + offsets[row['bench']]}
        for row in rows
    ]
    for row in calibrated:
        if not DIAMETER_MIN <= row['diameter_mm'] <= DIAMETER_MAX:
            raise ValueError(f"测件 {row['id']} 修正后口径 {row['diameter_mm']:g} mm 超出可记录范围")
    return calibrated


def analyze_calibration(rows, offsets, settings):
    """返回一套校准方案的带宽、峰谷、超差峰与谷间待查测件。"""
    offsets = normalize_offsets(offsets)
    calibrated = apply_offsets(rows, offsets)
    samples = np.array([row['diameter_mm'] for row in calibrated])
    fit_mask = np.array([row['split'] == 'fit' for row in calibrated])
    fit = samples[fit_mask]
    holdout = samples[~fit_mask]

    candidates, chosen_index = select_bandwidth(
        fit, holdout, settings['bandwidth_min_mm'], settings['bandwidth_max_mm'])
    chosen = candidates[chosen_index]
    model = GaussianKDE(samples, chosen.bandwidth)
    points, grid_spacing = find_turning_points(model)

    lower, upper = settings['tolerance_lower_mm'], settings['tolerance_upper_mm']
    valley_locations = [point.location for point in points if not point.is_peak]
    boundaries = [-math.inf, *valley_locations, math.inf]
    # 与 reporting.mode_evidence 相同的分箱口径：第 i 个峰对应第 i 个谷间区间。
    basin_counts = np.histogram(samples, bins=boundaries)[0]
    basin_index = np.digitize(samples, np.asarray(valley_locations)) if valley_locations else np.zeros(len(samples), int)

    peaks = [point for point in points if point.is_peak]
    basin_members = [[] for _ in peaks]
    for row, index in zip(calibrated, basin_index):
        basin_members[index].append(row)

    modes = []
    pending_ids = []
    for index, (peak, members) in enumerate(zip(peaks, basin_members)):
        is_outside = peak.location < lower or peak.location > upper
        member_ids = sorted(row['id'] for row in members)
        modes.append({
            'mode': index + 1,
            'peak_mm': peak.location,
            'peak_density': peak.density,
            'left_valley_mm': valley_locations[index - 1] if index > 0 else None,
            'right_valley_mm': valley_locations[index] if index < len(valley_locations) else None,
            'basin_observed_count': int(basin_counts[index]),
            'tolerance_position': '低于下限' if peak.location < lower else ('高于上限' if peak.location > upper else '公差内'),
            'is_outside_peak': is_outside,
            'basin_item_ids': member_ids,
        })
        if is_outside:
            pending_ids.extend(member_ids)

    return {
        'offsets': dict(sorted(offsets.items())),
        'tolerance_lower_mm': lower,
        'tolerance_upper_mm': upper,
        'bandwidth_candidates': [
            {'candidate': index + 1, 'bandwidth_mm': item.bandwidth,
             'mean_log_density': item.mean_log_density,
             'selected': index == chosen_index}
            for index, item in enumerate(candidates)
        ],
        'selected_bandwidth_mm': chosen.bandwidth,
        'selected_candidate': chosen_index + 1,
        'grid_spacing_mm': grid_spacing,
        'modes': modes,
        'pending_ids': sorted(set(pending_ids)),
        'calibrated_rows': calibrated,
    }
