import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://groundline_app:groundline_app@localhost:5433/groundline_test"
)
os.environ["MIGRATION_DATABASE_URL"] = os.environ.get(
    "TEST_MIGRATION_DATABASE_URL", "postgresql+asyncpg://groundline:groundline@localhost:5433/groundline_test"
)
os.environ["JWT_SECRET"] = "test-secret-that-is-long-enough-for-validation"
os.environ["PRELOAD_MODELS"] = "false"
os.environ["EMBEDDING_PROVIDER"] = "local"
os.environ["RERANK_PROVIDER"] = "local"
os.environ["COOKIE_SECURE"] = "false"
os.environ["COOKIE_DOMAIN"] = ""
os.environ["RESEND_API_KEY"] = ""
os.environ["DEV_MODE"] = "false"
os.environ["OTP_MAX_PER_IP_PER_HOUR"] = "1000"
os.environ["LANGFUSE_TRACING_ENABLED"] = "false"
os.environ["LANGFUSE_PUBLIC_KEY"] = ""
os.environ["LANGFUSE_SECRET_KEY"] = ""

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
async def migrated_db():
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, capture_output=True, text=True, env=os.environ
    )
    if result.returncode != 0:
        pytest.skip(f"Test database unavailable: {result.stderr.strip().splitlines()[-1:]}")

    from sqlalchemy import text

    from app.db.session import SessionLocal

    async with SessionLocal() as session:
        await session.execute(text("DELETE FROM otp_codes"))
        await session.execute(text("DELETE FROM users"))
        await session.commit()


@pytest.fixture
async def make_user(migrated_db):
    from app.db.models import User
    from app.db.session import SessionLocal

    async def factory() -> User:
        async with SessionLocal() as session:
            user = User(email=f"user-{uuid.uuid4().hex}@example.com")
            session.add(user)
            await session.commit()
            return user

    return factory


@pytest.fixture
async def client(migrated_db):
    import httpx

    from app.api.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers={"X-Requested-With": "groundline"}
    ) as http:
        yield http


def auth_headers(user_id) -> dict:
    from app.auth.service import create_token

    return {"Cookie": f"groundline_session={create_token(user_id)}"}


def fake_embedding(seed: int) -> list[float]:
    vector = [0.0] * 1024
    vector[seed % 1024] = 1.0
    return vector


async def seed_document(user_id, text: str, seed: int, size_bytes: int = 10):
    from app.db.models import Chunk, Document
    from app.db.session import tenant_session

    async with tenant_session(user_id) as session:
        document = Document(user_id=user_id, filename="secret.md", chunk_count=1, size_bytes=size_bytes)
        session.add(document)
        await session.flush()
        session.add(
            Chunk(
                user_id=user_id,
                document_id=document.id,
                chunk_index=0,
                page=None,
                content=text,
                embedding=fake_embedding(seed),
            )
        )
        await session.commit()
        return document
