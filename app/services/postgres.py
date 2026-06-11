from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.models.postgres import Base

engine: AsyncEngine | None = None
async_session: async_sessionmaker[AsyncSession] | None = None


async def get_postgres_engine(close: bool = False) -> AsyncEngine | None:
    """Initialize or dispose of the shared async Postgres engine."""
    global engine, async_session

    if close:
        if engine is not None:
            await engine.dispose()
            engine = None
            async_session = None
        return None

    if engine is None:
        engine = create_async_engine(settings.DATABASE_URL, future=True, echo=False)
        async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        except SQLAlchemyError:
            await engine.dispose()
            engine = None
            async_session = None
            raise

    return engine


def get_async_session() -> AsyncSession:
    """Return a new async database session."""
    if async_session is None:
        raise RuntimeError("Postgres engine has not been initialized")
    return async_session()
