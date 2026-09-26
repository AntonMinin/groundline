import asyncio
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings

ROOT = Path(__file__).resolve().parents[2]


def code_revisions() -> tuple[str, set[str]]:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "app" / "db" / "migrations"))
    script = ScriptDirectory.from_config(config)
    return script.get_current_head(), {revision.revision for revision in script.walk_revisions()}


def verdict(database: str | None, head: str, known: set[str]) -> str:
    if database == head:
        return "current"
    if database is None or database in known:
        return "behind"
    return "ahead"


async def database_revision(url: str) -> str | None:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            return await connection.scalar(text("SELECT version_num FROM alembic_version"))
    except DBAPIError:
        return None
    finally:
        await engine.dispose()


def main() -> int:
    head, known = code_revisions()
    database = asyncio.run(database_revision(settings.database_url))
    state = verdict(database, head, known)
    if state == "behind":
        print(
            f"schema check: the database is at {database or 'no revision'}, this code needs {head}. "
            "Run the migrate job in CI before deploying this version.",
            file=sys.stderr,
        )
        return 1
    if state == "ahead":
        print(f"schema check: the database is at {database}, newer than this code ({head}); starting anyway")
    return 0


if __name__ == "__main__":
    sys.exit(main())
