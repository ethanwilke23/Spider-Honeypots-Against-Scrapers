"""
Tests for the HONEYPOT_VARIANT switch.

They use a small FastAPI app with the site and honeypot routers only, so no
database is needed.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.honeypots.routes import (
    DYNAMIC_GRAPH_BASE_PATH,
    PROMPT_INJECTION_TRAP_PATH,
    SEMANTIC_TRAP_PATH,
    is_honeypot_path,
)
from app.honeypots.routes import router as honeypots_router
from app.honeypots.specs import DYNAMIC_LINK_GRAPH_TRAP, SEMANTIC_TRAP
from app.site.routes import router as site_router

BLOG_POST_WITH_HIDDEN_LINK = "/blog/vendor-negotiations-post-merger"

# setting -> variants that should be active
EXPECTED_ACTIVE = {
    "all": {"semantic", "prompt_injection", "link_graph"},
    "none": set(),
    "semantic": {"semantic"},
    "prompt_injection": {"prompt_injection"},
    "link_graph": {"link_graph"},
}


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(site_router)
    app.include_router(honeypots_router)
    return TestClient(app)


def use_setting(monkeypatch, setting):
    monkeypatch.setattr("app.honeypots.active.active_setting", lambda: setting)


@pytest.mark.parametrize("setting", EXPECTED_ACTIVE)
def test_honeypot_pages_are_served_only_for_active_variants(client, monkeypatch, setting):
    use_setting(monkeypatch, setting)
    active = EXPECTED_ACTIVE[setting]

    assert (client.get(SEMANTIC_TRAP_PATH).status_code == 200) == ("semantic" in active)
    assert (client.get(PROMPT_INJECTION_TRAP_PATH).status_code == 200) == ("prompt_injection" in active)
    assert (client.get(f"{DYNAMIC_GRAPH_BASE_PATH}/1").status_code == 200) == ("link_graph" in active)


@pytest.mark.parametrize("setting", EXPECTED_ACTIVE)
def test_discovery_points_appear_only_for_active_variants(client, monkeypatch, setting):
    use_setting(monkeypatch, setting)
    active = EXPECTED_ACTIVE[setting]

    home = client.get("/").text
    assert (SEMANTIC_TRAP_PATH in home) == ("semantic" in active)

    blog = client.get(BLOG_POST_WITH_HIDDEN_LINK).text
    assert (PROMPT_INJECTION_TRAP_PATH in blog) == ("prompt_injection" in active)

    robots = client.get("/robots.txt").text
    assert (DYNAMIC_GRAPH_BASE_PATH in robots) == ("link_graph" in active)


@pytest.mark.parametrize("setting", EXPECTED_ACTIVE)
def test_harmless_robots_entry_and_sitemap_never_change(client, monkeypatch, setting):
    use_setting(monkeypatch, setting)
    robots = client.get("/robots.txt").text
    assert "Disallow: /search-cache/" in robots
    assert "Sitemap: /sitemap.xml" in robots

    sitemap = client.get("/sitemap.xml").text
    for trap_path in (SEMANTIC_TRAP_PATH, PROMPT_INJECTION_TRAP_PATH, DYNAMIC_GRAPH_BASE_PATH):
        assert trap_path not in sitemap


def test_legitimate_pages_work_in_every_condition(client, monkeypatch):
    for setting in EXPECTED_ACTIVE:
        use_setting(monkeypatch, setting)
        for path in ("/", "/product", "/pricing", "/blog", "/contact", "/blog/closing-the-books-faster"):
            assert client.get(path).status_code == 200


def test_inactive_variant_paths_are_not_logged_as_trap_hits(monkeypatch):
    use_setting(monkeypatch, "none")
    assert is_honeypot_path(SEMANTIC_TRAP_PATH) is None
    assert is_honeypot_path(PROMPT_INJECTION_TRAP_PATH) is None
    assert is_honeypot_path(f"{DYNAMIC_GRAPH_BASE_PATH}/3") is None

    use_setting(monkeypatch, "semantic")
    assert is_honeypot_path(SEMANTIC_TRAP_PATH) == SEMANTIC_TRAP.variant_id
    assert is_honeypot_path(PROMPT_INJECTION_TRAP_PATH) is None
    assert is_honeypot_path(f"{DYNAMIC_GRAPH_BASE_PATH}/3") is None

    use_setting(monkeypatch, "link_graph")
    assert is_honeypot_path(f"{DYNAMIC_GRAPH_BASE_PATH}/3") == DYNAMIC_LINK_GRAPH_TRAP.variant_id


def test_default_setting_keeps_all_variants_active(client):
    # The autouse fixture in conftest.py sets "all".
    assert client.get(SEMANTIC_TRAP_PATH).status_code == 200
    assert client.get(PROMPT_INJECTION_TRAP_PATH).status_code == 200
    assert client.get(f"{DYNAMIC_GRAPH_BASE_PATH}/{DYNAMIC_LINK_GRAPH_TRAP.max_depth}").status_code == 200
    assert client.get(f"{DYNAMIC_GRAPH_BASE_PATH}/{DYNAMIC_LINK_GRAPH_TRAP.max_depth + 1}").status_code == 404


def test_invalid_setting_is_rejected():
    from pydantic import ValidationError

    from app.config import Settings

    with pytest.raises(ValidationError):
        Settings(honeypot_variant="everything")