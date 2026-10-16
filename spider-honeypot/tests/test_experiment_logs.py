"""Unit tests for the log export helpers. No database is used."""
from datetime import datetime, timedelta, timezone

from app.honeypots.specs import SEMANTIC_TRAP
from experiment.logs import WINDOW_MARGIN, build_export, run_window, summary_row

START = datetime(2026, 10, 15, 9, 0, 0, tzinfo=timezone.utc)

ENTRY = {
    "label": "playwright_baseline__semantic__r01",
    "agent": "playwright_baseline",
    "condition": "semantic",
    "repetition": 1,
    "session_id": "agent-session",
    "started_at": START.isoformat(),
    "finished_at": (START + timedelta(seconds=5)).isoformat(),
}


def _row(id_, session="agent-session", trap=None, depth=None, seconds=1):
    return {
        "id": id_, "session_id": session, "timestamp": (START + timedelta(seconds=seconds)).isoformat(),
        "method": "GET", "path": "/", "user_agent": "x", "trap_variant": trap, "graph_depth": depth,
    }


def test_window_runs_from_start_to_finish_plus_margin():
    start, end = run_window(ENTRY)
    assert start == START
    assert end == START + timedelta(seconds=5) + WINDOW_MARGIN


def test_requests_are_flagged_by_whether_they_belong_to_the_agent_session():
    export = build_export(ENTRY, [_row(1), _row(2, session="robots-fetch")])
    assert [r["in_agent_session"] for r in export["requests"]] == [True, False]


def test_session_flag_is_unknown_when_the_agent_has_no_session_id():
    export = build_export({**ENTRY, "session_id": None}, [_row(1)])
    assert export["requests"][0]["in_agent_session"] is None


def test_trap_hits_are_counted_and_unexpected_ones_flagged():
    own = SEMANTIC_TRAP.variant_id
    export = build_export(ENTRY, [_row(1), _row(2, trap=own), _row(3, trap="some-other-variant")])
    assert export["trap_hit_count"] == 2
    assert export["unexpected_trap_hit_request_ids"] == [3]


def test_any_trap_hit_is_unexpected_in_the_control_condition():
    export = build_export({**ENTRY, "condition": "none"}, [_row(1, trap=SEMANTIC_TRAP.variant_id)])
    assert export["unexpected_trap_hit_request_ids"] == [1]


def test_summary_row_reports_counts_first_hit_and_deepest_page():
    own = SEMANTIC_TRAP.variant_id
    export = build_export(ENTRY, [_row(1), _row(2, trap=own, depth=3, seconds=2), _row(3, trap=own, depth=7, seconds=3)])
    row = summary_row(export)
    assert row["requests"] == 3 and row["trap_hits"] == 2
    assert row["max_graph_depth"] == 7
    assert row["first_trap_hit_at"] == export["requests"][1]["timestamp"]


def test_summary_row_is_blank_when_there_are_no_hits():
    row = summary_row(build_export(ENTRY, [_row(1)]))
    assert row["trap_hits"] == 0 and row["first_trap_hit_at"] == "" and row["max_graph_depth"] == ""


def _event(id_, type_, session="agent-session", **payload):
    return {"id": id_, "session_id": session, "timestamp": START.isoformat(), "event_type": type_,
            "path": "/", "client_time": None, "payload": payload}


def test_exports_include_page_events_flagged_by_session():
    export = build_export(ENTRY, [_row(1)], [_event(1, "view"), _event(2, "view", session="other")])
    assert export["client_event_count"] == 2
    assert [e["in_agent_session"] for e in export["client_events"]] == [True, False]


def test_exports_without_events_still_work():
    export = build_export(ENTRY, [_row(1)])
    assert export["client_event_count"] == 0 and export["client_events"] == []


def test_summary_counts_clicks_untrusted_clicks_and_dwell_time():
    events = [_event(1, "view"), _event(2, "click", trusted=True), _event(3, "click", trusted=False),
              _event(4, "leave", dwell_ms=1500), _event(5, "leave", dwell_ms=500)]
    row = summary_row(build_export(ENTRY, [_row(1)], events))
    assert (row["client_events"], row["clicks"], row["untrusted_clicks"], row["total_dwell_ms"]) == (5, 2, 1, 2000)