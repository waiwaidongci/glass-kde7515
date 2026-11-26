import json

from sqlalchemy import func, select

from migrations.bootstrap import bootstrap
from src.config.database import Session
from src.constants.workflow import Role
from src.domain.project import SPEC, demo_rows
from src.models.account import Account
from src.models.calibration import CalibrationPlan
from src.models.dataset import Dataset
from src.services.calibrations import normalize_offsets
from src.services.catalog import add_dataset
from src.utils.security import hash_password
from src.utils.time import utc_stamp


DEMO_PLANS = (
    ('校准方案一：整体回零基线', {'JY-A': 0.0, 'JY-B': 0.0, 'JY-C': 0.0}, '演示基线，无待查件。'),
    ('校准方案二：全场下偏修正', {'JY-A': -0.3, 'JY-B': -0.3, 'JY-C': -0.3}, '下侧超差峰，谷间测件进入待查。'),
    ('校准方案三：JY-C 上偏修正', {'JY-A': 0.0, 'JY-B': 0.0, 'JY-C': 0.45}, '按台口径修正，JY-C 上侧风险。'),
)


def seed():
    with Session.begin() as session:
        owner = None
        for role in Role:
            email = f'{role.value}@demo.local'
            account = session.scalar(select(Account).where(Account.email == email))
            if account is None:
                account = Account(email=email, role=role, password_hash=hash_password('Demo-2611!'))
                session.add(account)
                session.flush()
            if role == Role.ADMIN:
                owner = account.id
        name = SPEC['dataset_name']
        dataset = session.scalar(select(Dataset).where(Dataset.name == name))
        if not dataset:
            dataset = add_dataset(session, name, demo_rows(), owner)
        existing_plans = session.scalars(select(CalibrationPlan)).all()
        if not existing_plans:
            now = utc_stamp()
            for label, offsets, note in DEMO_PLANS:
                session.add(CalibrationPlan(
                    label=label, dataset_id=dataset.id,
                    bench_offsets=normalize_offsets(offsets), version=1,
                    created_by=owner, created_at=now, updated_at=now, note=note))
        return {'accounts': session.scalar(select(func.count()).select_from(Account)),
                'datasets': session.scalar(select(func.count()).select_from(Dataset)),
                'calibration_plans': session.scalar(select(func.count()).select_from(CalibrationPlan)),
                'demo_rows': len(dataset.rows), 'checksum': dataset.checksum}


if __name__ == '__main__':
    bootstrap()
    print(json.dumps(seed(), ensure_ascii=False))
