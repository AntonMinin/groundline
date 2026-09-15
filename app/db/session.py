from collections.abc import AsyncIterator
from uuid import UUID

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from app.config import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


@event.listens_for(Session, "after_begin")
def _apply_tenant(session: Session, transaction, connection) -> None:
    user_id = session.info.get("user_id")
    if user_id is not None:
        connection.execute(text("SELECT set_config('app.user_id', :user_id, true)"), {"user_id": str(user_id)})


def tenant_session(user_id: UUID) -> AsyncSession:
    return SessionLocal(info={"user_id": user_id})


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
