"""复测清单的生成、失效重算与签发。"""

from fastapi import HTTPException
from sqlalchemy import select

from src.config.database import ImmediateSession
from src.constants.workflow import RetestStatus, Role
from src.domain.calibration import analyze_calibration
from src.domain.project import check_settings
from src.domain.retest import build_retest_plan
from src.models.calibration import CalibrationPlan
from src.models.retest import RetestItem, RetestJob
from src.services.calibrations import current_fingerprint
from src.services.catalog import get_dataset
from src.utils.time import utc_stamp


def _job_info(job):
    return {
        'id': job.id, 'dataset_id': job.dataset_id, 'quota': job.quota,
        'status': job.status, 'settings': job.settings,
        'plan_fingerprint': job.plan_fingerprint,
        'created_at': job.created_at, 'signed_at': job.signed_at,
        'signed_by': job.signed_by, 'sign_note': job.sign_note,
    }


def list_jobs(session, actor):
    statement = select(RetestJob).order_by(RetestJob.id.desc()).limit(100)
    if actor.role == Role.VIEWER:
        statement = statement.where(RetestJob.status == RetestStatus.SIGNED)
    return [_job_info(job) for job in session.scalars(statement)]


def get_job(session, job_id, actor):
    job = session.get(RetestJob, job_id)
    if job is None or (actor.role == Role.VIEWER and job.status != RetestStatus.SIGNED):
        raise LookupError('找不到可查看的复测清单')
    items = session.scalars(select(RetestItem).where(RetestItem.job_id == job_id)
                            .order_by(RetestItem.id)).all()
    return job, items


def _evaluate_plans(session, dataset_id, rows, settings):
    plans = session.scalars(
        select(CalibrationPlan).where(CalibrationPlan.dataset_id == dataset_id)
        .order_by(CalibrationPlan.id)
    ).all()
    if not plans:
        raise LookupError('该台账尚无校准方案，无法生成复测清单')
    analyses = []
    pending_by_plan = {}
    for plan in plans:
        analysis = analyze_calibration(rows, plan.bench_offsets, settings)
        pending_by_plan[plan.id] = set(analysis['pending_ids'])
        analyses.append({
            'plan_id': plan.id, 'plan_label': plan.label, 'plan_version': plan.version,
            'selected_bandwidth_mm': analysis['selected_bandwidth_mm'],
            'selected_candidate': analysis['selected_candidate'],
            'outside_peak_modes': [m['mode'] for m in analysis['modes'] if m['is_outside_peak']],
            'pending_count': len(analysis['pending_ids']),
            'pending_ids': analysis['pending_ids'],
            'modes': [{key: value for key, value in mode.items() if key != 'basin_item_ids'}
                      for mode in analysis['modes']],
        })
    return plans, analyses, pending_by_plan


def create_job(session, payload, actor):
    dataset = get_dataset(session, payload.dataset_id)
    settings = check_settings(payload.settings)
    if not isinstance(payload.quota, int) or isinstance(payload.quota, bool) or payload.quota <= 0:
        raise ValueError('复测名额须为正整数')

    plans, analyses, pending_by_plan = _evaluate_plans(session, dataset.id, dataset.rows, settings)
    allocation = build_retest_plan(pending_by_plan, payload.quota)
    fingerprint = {str(plan.id): plan.version for plan in plans}
    now = utc_stamp()

    # 同一台账只保留一份未签草稿：新建即让旧草稿失效，避免各班拿着多份口径交接。
    for old in session.scalars(select(RetestJob).where(
            RetestJob.dataset_id == dataset.id,
            RetestJob.status == RetestStatus.DRAFT)).all():
        old.status = RetestStatus.STALE

    job = RetestJob(dataset_id=dataset.id, quota=payload.quota, status=RetestStatus.DRAFT,
                    settings=settings, plan_fingerprint=fingerprint,
                    result={'allocation': allocation, 'plan_results': analyses},
                    created_by=actor.id, created_at=now)
    session.add(job)
    session.flush()

    row_index = {row['id']: row for row in dataset.rows}
    plan_index = {plan.id: plan for plan in plans}
    item_plans = {item_id: [] for item_id in allocation['items']}
    for plan_id, pending in pending_by_plan.items():
        for item_id in pending:
            if item_id in item_plans:
                item_plans[item_id].append(plan_id)
    for item_id in allocation['items']:
        source = row_index[item_id]
        related = sorted(item_plans[item_id])
        # 同一测件可能被多个方案的谷间收进，展示其中偏离台账口径最远的修正值。
        calibrated = max(
            source['diameter_mm'] + plan_index[plan_id].bench_offsets[source['bench']]
            for plan_id in related
        ) if related else source['diameter_mm']
        session.add(RetestItem(
            job_id=job.id, item_id=item_id, bench=source['bench'],
            raw_diameter_mm=source['diameter_mm'],
            calibrated_diameter_mm=calibrated,
            plan_ids=related,
            reason=f'超差峰谷间测件，涉及方案 {", ".join(map(str, related))}',
        ))
    session.commit()
    return _job_info(job)


def detail(session, job_id, actor):
    job, items = get_job(session, job_id, actor)
    current = current_fingerprint(session, job.dataset_id)
    return {
        **_job_info(job),
        'fingerprint_current': current,
        'fingerprint_matches': {str(k): v for k, v in job.plan_fingerprint.items()} == current
        if job.status != RetestStatus.SIGNED else True,
        'result': job.result,
        'items': [
            {'item_id': item.item_id, 'bench': item.bench,
             'raw_diameter_mm': item.raw_diameter_mm,
             'calibrated_diameter_mm': item.calibrated_diameter_mm,
             'plan_ids': item.plan_ids, 'reason': item.reason}
            for item in items
        ],
    }


def sign_job(session, job_id, payload, actor):
    # 先在请求会话里做存在性检查，给出稳定的 404 / 409 语义。
    preview = session.get(RetestJob, job_id)
    if preview is None:
        raise LookupError('找不到复测清单')
    if preview.status == RetestStatus.SIGNED:
        raise HTTPException(409, '该复测清单已签发，不能重复签发')
    if preview.status == RetestStatus.STALE:
        raise HTTPException(409, '校准方案已被晚到记录更新，未签结果失效，请重算后再签')

    # 独立 IMMEDIATE 事务：开启即持有写锁，并发的校准更正要么已提交
    # （指纹拦截并置 stale），要么阻塞到本事务提交后再令新草稿失效，
    # 始终以当时有效的方案为准。
    with ImmediateSession() as tx:
        job = tx.get(RetestJob, job_id, with_for_update=True)
        if job.status == RetestStatus.SIGNED:
            raise HTTPException(409, '该复测清单已签发，不能重复签发')
        current = current_fingerprint(tx, job.dataset_id)
        if job.status == RetestStatus.STALE or {str(k): v for k, v in job.plan_fingerprint.items()} != current:
            job.status = RetestStatus.STALE
            tx.commit()
            raise HTTPException(409, '签发时检测到并发的校准更正，以当时有效方案为准，请重算后再签')

        job.status = RetestStatus.SIGNED
        job.signed_by = actor.id
        job.signed_at = utc_stamp()
        job.sign_note = payload.note
        tx.commit()
    session.expire_all()
    return _job_info(session.get(RetestJob, job_id))
