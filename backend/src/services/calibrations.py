"""校准方案的建档、更新与版本管理。

晚到的校准记录若改动了某方案，该方案版本递增；引用旧版本且尚未签发的
复测清单随即失效，需要按当前有效方案重算后才能签发。方案绑定具体测径
台账，按台修正量在建档时就对照台账台集合校验。
"""

from sqlalchemy import select

from src.config.database import ImmediateSession
from src.constants.workflow import RetestStatus
from src.domain.calibration import normalize_offsets
from src.models.calibration import CalibrationPlan
from src.models.retest import RetestJob
from src.services.catalog import get_dataset
from src.utils.time import utc_stamp


def plan_info(plan):
    return {
        'id': plan.id, 'label': plan.label, 'dataset_id': plan.dataset_id,
        'bench_offsets': plan.bench_offsets, 'version': plan.version,
        'created_at': plan.created_at, 'updated_at': plan.updated_at, 'note': plan.note,
    }


def list_plans(session, dataset_id=None):
    statement = select(CalibrationPlan).order_by(CalibrationPlan.id)
    if dataset_id is not None:
        statement = statement.where(CalibrationPlan.dataset_id == dataset_id)
    return [plan_info(plan) for plan in session.scalars(statement)]


def get_plan(session, plan_id):
    plan = session.get(CalibrationPlan, plan_id)
    if plan is None:
        raise LookupError('找不到校准方案')
    return plan


def _validate_against_dataset(rows, offsets):
    benches = {row['bench'] for row in rows}
    unknown = set(offsets) - benches
    if unknown:
        raise ValueError('校准方案包含台账中不存在的测径台：' + '、'.join(sorted(unknown)))
    missing = benches - set(offsets)
    if missing:
        raise ValueError('校准方案缺少测径台修正量：' + '、'.join(sorted(missing)))


def create_plan(session, payload, actor):
    dataset = get_dataset(session, payload.dataset_id)
    offsets = normalize_offsets(payload.bench_offsets)
    _validate_against_dataset(dataset.rows, offsets)
    now = utc_stamp()
    plan = CalibrationPlan(label=payload.label, dataset_id=dataset.id, bench_offsets=offsets,
                           version=1, created_by=actor.id, created_at=now, updated_at=now,
                           note=payload.note)
    session.add(plan)
    session.flush()
    return plan_info(plan)


def update_plan(session, plan_id, payload, actor):
    plan = session.get(CalibrationPlan, plan_id)
    if plan is None:
        raise LookupError('找不到校准方案')
    dataset = get_dataset(session, plan.dataset_id)
    offsets = normalize_offsets(payload.bench_offsets)
    _validate_against_dataset(dataset.rows, offsets)

    # IMMEDIATE 事务先取写锁：与签发票据互斥，晚到记录不会覆盖正在签发的判断。
    with ImmediateSession() as tx:
        locked = tx.get(CalibrationPlan, plan_id, with_for_update=True)
        now = utc_stamp()
        locked.bench_offsets = offsets
        locked.label = payload.label
        locked.note = payload.note
        locked.version += 1
        locked.updated_at = now

        # 引用该方案且仍未签发的清单立即失效。两个 IMMEDIATE 写事务在
        # SQLite 上串行执行：若签发先提交，这里复查到 signed 即跳过，
        # 晚到的更正不追溯作废已按当时有效方案完成的交接。
        invalidated = []
        for job in tx.scalars(select(RetestJob).where(RetestJob.status != RetestStatus.SIGNED)).all():
            if str(plan_id) in job.plan_fingerprint or plan_id in job.plan_fingerprint:
                job.status = RetestStatus.STALE
                invalidated.append(job.id)
        tx.commit()
    session.expire_all()
    return {**plan_info(session.get(CalibrationPlan, plan_id)), 'invalidated_job_ids': invalidated}


def current_fingerprint(session, dataset_id=None):
    """当前有效方案的版本指纹，可按台账过滤。"""
    statement = select(CalibrationPlan).order_by(CalibrationPlan.id)
    if dataset_id is not None:
        statement = statement.where(CalibrationPlan.dataset_id == dataset_id)
    plans = session.scalars(statement).all()
    return {str(plan.id): plan.version for plan in plans}
