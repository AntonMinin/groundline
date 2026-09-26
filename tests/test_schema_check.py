import os
import subprocess
import sys

import pytest

from app.db import schema_check
from tests.conftest import ROOT


def test_the_code_knows_its_head_and_history():
    head, known = schema_check.code_revisions()
    assert head in known and "0001" in known


@pytest.mark.parametrize(
    "database, expected",
    [("0008", "current"), ("0007", "behind"), (None, "behind"), ("0009", "ahead")],
)
def test_verdict(database, expected):
    assert schema_check.verdict(database, "0008", {"0001", "0007", "0008"}) == expected


async def test_the_application_role_can_read_the_revision(migrated_db):
    head, _ = schema_check.code_revisions()
    assert await schema_check.database_revision(os.environ["DATABASE_URL"]) == head


async def test_an_unmigrated_database_reads_as_no_revision():
    url = os.environ["DATABASE_URL"].rsplit("/", 1)[0] + "/postgres"
    assert await schema_check.database_revision(url) is None


def test_start_refuses_code_newer_than_the_database(migrated_db, monkeypatch):
    head, known = schema_check.code_revisions()
    monkeypatch.setattr(schema_check, "code_revisions", lambda: ("9999", known | {"9999"}))
    assert schema_check.main() == 1
    monkeypatch.setattr(schema_check, "code_revisions", lambda: (head, known))
    assert schema_check.main() == 0


def test_the_module_runs_as_the_start_script_calls_it(migrated_db):
    result = subprocess.run([sys.executable, "-m", "app.db.schema_check"], cwd=ROOT, env=os.environ, capture_output=True)
    assert result.returncode == 0, result.stderr
