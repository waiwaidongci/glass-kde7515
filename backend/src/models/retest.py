from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.config.database import Base


class RetestJob(Base):
    """一份复测清单（草稿或已签发）。未签发时可随校准方案更新而失效。"""

    __tablename__ = 'retest_jobs'

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey('datasets.id'), index=True)
    quota: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), index=True)
    settings: Mapped[dict] = mapped_column(JSON)
    # 生成时各方案的版本指纹：{方案编号: 版本}，签发前据此判断是否已被晚到记录更正。
    plan_fingerprint: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('accounts.id'))
    created_at: Mapped[str] = mapped_column(String(32))
    signed_by: Mapped[int | None] = mapped_column(ForeignKey('accounts.id'), nullable=True)
    signed_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sign_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class RetestItem(Base):
    """清单中的复测测件，保留入选时的方案归属与修正口径证据。"""

    __tablename__ = 'retest_items'

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey('retest_jobs.id'), index=True)
    item_id: Mapped[str] = mapped_column(String(64), index=True)
    bench: Mapped[str] = mapped_column(String(24))
    raw_diameter_mm: Mapped[float] = mapped_column(Float)
    calibrated_diameter_mm: Mapped[float] = mapped_column(Float)
    plan_ids: Mapped[list] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(String(120))
