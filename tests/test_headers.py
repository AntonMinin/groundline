import base64
import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ("frontend", "landing")
REQUIRED = (
    "default-src",
    "script-src",
    "style-src",
    "img-src",
    "font-src",
    "connect-src",
    "object-src",
    "base-uri",
    "form-action",
    "frame-ancestors",
)
DEFAULT_API_URL = "https://api.groundline.antonmb.com"


def response_headers(project: str) -> dict[str, str]:
    config = json.loads((ROOT / project / "vercel.json").read_text(encoding="utf-8"))
    rules = [rule for rule in config["headers"] if rule["source"] == "/(.*)"]
    assert rules, f"{project}: no rule covering every path"
    return {header["key"]: header["value"] for header in rules[0]["headers"]}


def directives(policy: str) -> dict[str, list[str]]:
    parsed = {}
    for part in policy.split(";"):
        name, *values = part.split()
        parsed[name] = values
    return parsed


@pytest.mark.parametrize("project", PROJECTS)
def test_the_policy_is_enforced_and_not_also_sent_as_report_only(project):
    headers = response_headers(project)
    assert "Content-Security-Policy" in headers
    assert "Content-Security-Policy-Report-Only" not in headers
    assert sum(key.lower().startswith("content-security-policy") for key in headers) == 1


@pytest.mark.parametrize("project", PROJECTS)
def test_every_directive_of_the_policy_is_present(project):
    policy = directives(response_headers(project)["Content-Security-Policy"])
    assert set(REQUIRED) <= set(policy), f"{project}: missing {set(REQUIRED) - set(policy)}"
    assert policy["object-src"] == ["'none'"]
    assert policy["frame-ancestors"] == ["'none'"]
    assert policy["base-uri"] == ["'self'"]
    assert policy["form-action"] == ["'self'"]
    assert "'unsafe-inline'" not in policy["script-src"]


def test_connect_src_carries_the_api_origin():
    origin = urlsplit(os.environ.get("VITE_API_URL", DEFAULT_API_URL))
    expected = f"{origin.scheme}://{origin.netloc}"
    policy = directives(response_headers("frontend")["Content-Security-Policy"])
    assert expected in policy["connect-src"]
    assert "'self'" in policy["connect-src"]


def inline_scripts(dist: Path) -> dict[str, list[str]]:
    """Executable inline scripts in the built HTML, as {sha256 source expression: [pages]}.

    JSON-LD blocks are excluded: the browser never executes them, so script-src does not
    govern them - production confirmed this by not blocking any of them.
    """
    found: dict[str, list[str]] = {}
    for page in sorted(dist.rglob("*.html")):
        html = page.read_text(encoding="utf-8")
        for attributes, body in re.findall(r"<script((?:(?!\ssrc=)[^>])*)>([\s\S]*?)</script>", html):
            if "ld+json" in attributes or not body.strip():
                continue
            digest = base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode()
            found.setdefault(f"'sha256-{digest}'", []).append(str(page.relative_to(dist)))
    return found


@pytest.mark.parametrize("project", PROJECTS)
def test_script_src_matches_the_inline_scripts_in_the_build_exactly(project):
    dist = ROOT / project / "dist"
    if not dist.exists():
        pytest.skip(f"{project}/dist is not built")

    found = inline_scripts(dist)
    hashes = {value for value in directives(response_headers(project)["Content-Security-Policy"])["script-src"]
              if value.startswith("'sha256-")}

    unallowed = {h: found[h] for h in found if h not in hashes}
    assert not unallowed, f"{project}: inline scripts the policy would block: {unallowed}"
    assert not hashes - set(found), f"{project}: script-src carries hashes nothing builds: {hashes - set(found)}"


@pytest.mark.parametrize("project", PROJECTS)
def test_the_supporting_headers_are_still_sent(project):
    headers = response_headers(project)
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "camera=()" in headers["Permissions-Policy"]
