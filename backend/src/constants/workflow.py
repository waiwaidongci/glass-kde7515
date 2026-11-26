from enum import StrEnum


class Role(StrEnum):
    ADMIN = 'admin'
    ANALYST = 'analyst'
    VIEWER = 'viewer'


class RunStatus(StrEnum):
    COMPLETED = 'completed'
    FAILED = 'failed'


class Decision(StrEnum):
    APPROVED = 'approved'
    REJECTED = 'rejected'


class RetestStatus(StrEnum):
    DRAFT = 'draft'
    STALE = 'stale'
    SIGNED = 'signed'
