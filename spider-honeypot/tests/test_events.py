"""Tests for the page-event beacon: the parser, the page script and the export. No database is used."""
import json

from fastapi.testclient import TestClient

from app.events import MAX_BODY_BYTES, parse_event
from app.main import app
from app.site.layout import EVENTS_PATH, render_page


def _body(**fields):
    base = {"type": "click", "path": "/blog", "t": 1_760_000_000_000, "data": {"tag": "A"}}
    return json.dumps({**base, **fields}).encode()


def test_a_valid_event_is_cleaned_and_returned():
    event = parse_event(_body())
    assert event["event_type"] == "click"
    assert event["path"] == "/blog"
    assert event["payload"] == {"tag": "A"}
    assert event["client_time"].year == 2025


def test_unknown_types_bad_json_and_oversized_bodies_are_dropped():
    assert parse_event(_body(type="exploit")) is None
    assert parse_event(b"not json") is None
    assert parse_event(b"[1, 2]") is None
    assert parse_event(_body(path=5)) is None
    assert parse_event(_body(data={"x": "y" * MAX_BODY_BYTES})) is None


def test_a_bad_timestamp_or_payload_is_tolerated():
    event = parse_event(_body(t="soon", data="text"))
    assert event["client_time"] is None
    assert event["payload"] == {}


def test_long_paths_are_truncated():
    assert len(parse_event(_body(path="/" + "a" * 2000))["path"]) == 512


def test_every_page_carries_the_event_script():
    html = render_page("Test", "<p>hello</p>")
    assert EVENTS_PATH in html
    assert "sendBeacon" in html


def test_a_malformed_beacon_gets_204_and_touches_no_database():
    # Without "with", the app's start-up (and its database) is not run. A bad body is dropped before any write.
    response = TestClient(app).post(EVENTS_PATH, content=b"garbage")
    assert response.status_code == 204