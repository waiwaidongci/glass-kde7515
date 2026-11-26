from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .settings import DATABASE_URL


class Base(DeclarativeBase):
    pass


engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Session = sessionmaker(bind=engine, expire_on_commit=False)

# 签发、校准更正等需要“先锁后读”的写事务：SQLite 下用 BEGIN IMMEDIATE
# 开启即取写锁，避免延迟事务在旧快照上判断，随后被并发写入覆盖口径。
# 等待锁的超时放宽到 30 秒，让并发的另一端先提交而不是直接抛锁错误。
if engine.dialect.name == 'sqlite':
    immediate_engine = create_engine(
        DATABASE_URL, pool_pre_ping=True,
        connect_args={'timeout': 30, 'isolation_level': 'IMMEDIATE'})
else:
    immediate_engine = engine
ImmediateSession = sessionmaker(bind=immediate_engine, expire_on_commit=False)


@event.listens_for(engine, 'connect')
@event.listens_for(immediate_engine, 'connect')
def configure_sqlite(connection, _):
    if engine.dialect.name == 'sqlite':
        connection.execute('PRAGMA foreign_keys = ON')


def session_scope():
    with Session() as session:
        yield session
