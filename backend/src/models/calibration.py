from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.config.database import Base


class CalibrationPlan(Base):
    """按台修正口径的校准方案。晚到记录更新同一方案时版本号递增。"""

    __tablename__ = 'calibration_plans'

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(140))
    dataset_id: Mapped[int] = mapped_column(ForeignKey('datasets.id'), index=True)
    bench_offsets: Mapped[dict] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[int] = mapped_column(ForeignKey('accounts.id'))
    created_at: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[str] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
