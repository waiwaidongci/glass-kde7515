from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from src.controllers.dependencies import Actor, Admin, Db, Writer
from src.schemas.retests import RetestCreate, RetestInfo, RetestSign
from src.services import retests
from src.utils.csv_files import write_rows

router = APIRouter(prefix='/retests')


@router.get('', response_model=list[RetestInfo])
def list_all(session: Db, actor: Actor):
    return retests.list_jobs(session, actor)


@router.post('', response_model=RetestInfo, status_code=201)
def create(payload: RetestCreate, session: Db, actor: Writer):
    return retests.create_job(session, payload, actor)


@router.get('/{job_id}')
def detail(job_id: int, session: Db, actor: Actor):
    return retests.detail(session, job_id, actor)


@router.post('/{job_id}/sign', response_model=RetestInfo)
def sign(job_id: int, payload: RetestSign, session: Db, actor: Admin):
    return retests.sign_job(session, job_id, payload, actor)


@router.get('/{job_id}/export')
def export(job_id: int, session: Db, actor: Actor):
    job, items = retests.get_job(session, job_id, actor)
    if job.status != 'signed':
        raise HTTPException(409, '签发后可下载正式复测 CSV')
    columns = ['item_id', 'bench', 'raw_diameter_mm', 'calibrated_diameter_mm', 'plan_ids', 'reason']
    rows = [{key: getattr(item, key) if key != 'plan_ids' else ','.join(map(str, item.plan_ids))
             for key in columns} for item in items]
    return Response(write_rows(columns, rows), media_type='text/csv',
                    headers={'Content-Disposition': f'attachment; filename="retest-{job_id}.csv"'})
