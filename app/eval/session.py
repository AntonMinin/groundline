import asyncio
import sys
from datetime import UTC, datetime

from sqlalchemy import select

from app.auth.service import create_token
from app.config import CURRENT_TERMS_VERSION
from app.db.models import User
from app.db.session import SessionLocal


async def main(email: str) -> None:
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, role="eval", terms_accepted_at=datetime.now(UTC), terms_version=CURRENT_TERMS_VERSION)
            session.add(user)
            await session.commit()
    print(create_token(user.id, user.token_version))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "eval@groundline.local"))
