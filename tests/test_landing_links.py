import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "landing" / "dist"
LEGAL_PAGES = ("privacy/index.html", "terms/index.html", "ru/privacy/index.html", "ru/terms/index.html")
SECTION_LINKS = ("how", "auth", "numbers", "faq")


def page(name: str) -> str:
    if not DIST.exists():
        pytest.skip("landing/dist is not built")
    return (DIST / name).read_text(encoding="utf-8")


def hrefs(html: str) -> list[str]:
    return re.findall(r'href="([^"]*)"', html)


def ids(html: str) -> set[str]:
    return set(re.findall(r'id="([^"]*)"', html))


@pytest.mark.parametrize("name", LEGAL_PAGES)
def test_legal_pages_have_no_anchor_that_points_nowhere(name):
    html = page(name)
    present = ids(html)
    dangling = [href for href in hrefs(html) if href.startswith("#") and href[1:] not in present]
    assert not dangling, f"{name}: anchors to sections it does not have: {dangling}"


@pytest.mark.parametrize("name", LEGAL_PAGES)
def test_legal_pages_send_section_links_to_the_home_page_of_their_locale(name):
    html = page(name)
    home = "/ru" if name.startswith("ru/") else "/"
    for section in SECTION_LINKS:
        assert f'href="{home}#{section}"' in html, f"{name}: no link to {home}#{section}"


@pytest.mark.parametrize("name", ["index.html", "ru/index.html"])
def test_the_home_page_links_to_its_own_sections_and_they_exist(name):
    html = page(name)
    home = "/ru" if name.startswith("ru/") else "/"
    present = ids(html)
    for section in SECTION_LINKS:
        assert f'href="{home}#{section}"' in html, f"{name}: no link to {home}#{section}"
        assert section in present, f"{name}: links to #{section} but has no such id"
