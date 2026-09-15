from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        s = get_settings()
        # Supabase pooler (:6543) runs pgbouncer in transaction mode, which does
        # not support prepared statements. asyncpg must disable its statement
        # cache or every connect fails with DuplicatePreparedStatementError
        # (see Render build dep-dakkk8dbedkc73eldic0).
        connect_args = {}
        if s.DATABASE_URL.startswith("postgresql+asyncpg"):
            connect_args = {"statement_cache_size": 0}
        _engine = create_async_engine(
            s.DATABASE_URL, pool_pre_ping=True, future=True, connect_args=connect_args
        )
    return _engine


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(), class_=AsyncSession, expire_on_commit=False
        )
    return _session_factory


async def get_session():
    factory = get_session_factory()
    async with factory() as session:
        yield session
