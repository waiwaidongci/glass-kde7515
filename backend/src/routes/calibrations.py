from fastapi import APIRouter, Query

from src.controllers.dependencies import Actor, Db, Writer
from src.schemas.calibrations import CalibrationCreate, CalibrationInfo
from src.services import calibrations

router = APIRouter(prefix='/calibrations')


@router.get('', response_model=list[CalibrationInfo])
def list_all(session: Db, actor: Actor, dataset_id: int | None = Query(None, gt=0)):
    return calibrations.list_plans(session, dataset_id)


@router.post('', response_model=CalibrationInfo, status_code=201)
def create(payload: CalibrationCreate, session: Db, actor: Writer):
    info = calibrations.create_plan(session, payload, actor)
    session.commit()
    return info


@router.get('/{plan_id}', response_model=CalibrationInfo)
def detail(plan_id: int, session: Db, actor: Actor):
    return calibrations.plan_info(calibrations.get_plan(session, plan_id))


@router.put('/{plan_id}', response_model=CalibrationInfo)
def update(plan_id: int, payload: CalibrationCreate, session: Db, actor: Writer):
    updated = calibrations.update_plan(session, plan_id, payload, actor)
    session.commit()
    return {key: value for key, value in updated.items() if key != 'invalidated_job_ids'}
