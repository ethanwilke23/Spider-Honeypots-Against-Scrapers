"""
Unit tests for the Playwright baseline crawler's link handling.

crawl() itself is not unit-tested because it needs a real browser; run
`python -m agents.playwright_baseline.run` against a running server instead.
"""
from agents.playwright_baseline.crawler import normalize_link


def test_normalize_link_resolves_relative_paths():
    assert normalize_link("http://127.0.0.1:8000", "/product") == "/product"
    # Links on the decoy site are absolute paths such as href="/blog/x".
    assert normalize_link("http://127.0.0.1:8000/blog", "/blog/vendor-negotiations-post-merger") == (
        "/blog/vendor-negotiations-post-merger"
    )


def test_normalize_link_rejects_cross_origin():
    assert normalize_link("http://127.0.0.1:8000", "https://evil.example.com/steal") is None


def test_normalize_link_handles_empty_and_none():
    assert normalize_link("http://127.0.0.1:8000", "") is None


def test_normalize_link_strips_query_and_fragment():
    assert normalize_link("http://127.0.0.1:8000", "/blog?utm_source=x#section") == "/blog"


def test_normalize_link_root_path_defaults_correctly():
    assert normalize_link("http://127.0.0.1:8000", "http://127.0.0.1:8000") == "/"