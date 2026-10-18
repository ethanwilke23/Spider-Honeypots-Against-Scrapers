"""Offline tests for the Claude text-browser agent: no API key, no network, no spending."""
import asyncio
import sys
import threading
import types
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from agents.claude_text_browser import agent_loop
from agents.claude_text_browser.agent_loop import SpendNotConfirmedError, run_agent
from agents.claude_text_browser.browser import Link, TextBrowser, format_view, same_site
from agents.shared.record_checks import record_problem
from agents.shared.task import get_task_instruction


def test_format_view_lists_text_then_numbered_links():
    view = format_view("http://x/a", 200, "T", "hello", [Link(1, "Blog", "http://x/blog"), Link(2, "Home", "http://x/")])
    assert "URL: http://x/a" in view and "Status: 200" in view and "Title: T" in view
    assert "[1] Blog -> http://x/blog" in view and "[2] Home -> http://x/" in view
    assert view.index("hello") < view.index("[1] Blog")


def test_format_view_cuts_long_text_and_handles_no_links():
    view = format_view("http://x/", None, "T", "a" * 20000, [])
    assert "[page text cut off]" in view and "(no links)" in view and "Status: unknown" in view
    assert len(view) < 9000


def test_same_site_compares_scheme_host_and_port():
    assert same_site("http://127.0.0.1:8000/blog", "http://127.0.0.1:8000")
    assert not same_site("http://127.0.0.1:8001/", "http://127.0.0.1:8000")
    assert not same_site("http://example.com/", "http://127.0.0.1:8000")
    assert not same_site("https://127.0.0.1:8000/", "http://127.0.0.1:8000")


def test_task_text_has_text_browser_wording_and_no_trap_hints():
    # The shared opening is identical for every agent; only the interface sentence is new.
    base = get_task_instruction("crawl4ai").lower()
    text = get_task_instruction("claude_text_browser").lower()
    assert "open_link" in text and "numbered" in text
    interface = text[text.index("you are using a text-based"):]
    for word in ("honeypot", "trap", "canary", "restricted", "internal", "confidential", "token"):
        assert word not in interface
    assert text.split("you are using a text-based")[0].strip()[:60] == base[:60]


def test_run_agent_refuses_without_confirm_spend(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-not-a-real-key")
    with pytest.raises(SpendNotConfirmedError):
        asyncio.run(run_agent("http://127.0.0.1:1"))


def test_record_check_flags_no_model_call():
    assert record_problem("claude_text_browser", {"iterations_used": 0})
    assert record_problem("claude_text_browser", {"iterations_used": 3}) is None


PAGES = {
    "/": '<html><title>Home</title><body><p>Welcome</p><a href="/blog">Blog</a>'
         '<a href="http://example.com/">Elsewhere</a><a href="/hidden" style="display:none">Hidden</a>'
         '<!-- secret comment --></body></html>',
    "/blog": '<html><title>Blog</title><body><p>Posts</p><a href="/">Home</a></body></html>',
}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = PAGES.get(self.path)
        self.send_response(200 if body else 404)
        self.send_header("Content-Type", "text/html")
        self.send_header("Set-Cookie", "hp_session=abc123; Path=/")
        self.end_headers()
        self.wfile.write((body or "<html><body>not found</body></html>").encode())

    def log_message(self, *a):
        pass


@pytest.fixture()
def site():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def _browser_or_skip(base):
    async def go():
        b = TextBrowser(base)
        try:
            return b, await b.start()
        except Exception as exc:  # Chromium not installed here
            await b.close()
            pytest.skip(f"Chromium cannot start: {exc}")
    return go


def test_browser_view_follow_link_back_and_outside_block(site):
    async def scenario():
        b, first = await _browser_or_skip(site)()
        try:
            assert "Welcome" in first and "[1] Blog -> " + site + "/blog" in first
            assert "secret comment" not in first          # HTML comments are not shown
            assert "Hidden" not in first                  # CSS-hidden links are not listed
            blog = await b.open_link(1)
            assert "Posts" in blog and b.current_url.endswith("/blog")
            back = await b.go_back()
            assert "Welcome" in back
            with pytest.raises(ValueError):
                await b.open_url("http://example.com/")
            with pytest.raises(ValueError):
                await b.open_link(99)
            assert "Posts" in await b.open_url("/blog")
            assert await b.get_session_cookie() == "abc123"
            assert len(b.pages_viewed) >= 4
        finally:
            await b.close()
    asyncio.run(scenario())


class _Block:
    def __init__(self, **kw):
        self.__dict__.update(kw)

    def model_dump(self):
        return dict(self.__dict__)


def _fake_anthropic(script, seen):
    class Messages:
        async def create(self, **kwargs):
            seen.append(kwargs)
            return types.SimpleNamespace(content=script.pop(0))

    class Client:
        def __init__(self, api_key):
            self.messages = Messages()

    return types.SimpleNamespace(AsyncAnthropic=Client)


def test_loop_follows_tool_calls_and_records(site, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-not-a-real-key")
    seen = []
    script = [
        [_Block(type="tool_use", id="t1", name="open_link", input={"number": 1})],
        [_Block(type="tool_use", id="t2", name="open_url", input={"url": "http://example.com/"})],
        [_Block(type="text", text="All done.")],
    ]
    monkeypatch.setitem(sys.modules, "anthropic", _fake_anthropic(script, seen))

    async def go():
        try:
            return await run_agent(site, confirm_spend=True, max_iterations=5)
        except Exception as exc:
            if "playwright" in type(exc).__module__ or "Executable" in str(exc):
                pytest.skip(f"Chromium cannot start: {exc}")
            raise
    t = asyncio.run(go())
    assert t.iterations_used == 3 and t.final_text == "All done."
    assert t.session_id == "abc123" and t.final_url.endswith("/blog")
    # The blocked outside address was reported to the model as an error result, not crashed on.
    # (the message list is shared and grows after each call, so index from the start)
    msgs = seen[-1]["messages"]
    assert "Posts" in msgs[2]["content"][0]["content"]
    assert msgs[4]["content"][0]["is_error"] is True and "Only pages on this website" in msgs[4]["content"][0]["content"]
    assert seen[0]["tools"] == agent_loop.TOOLS
    assert seen[0]["tool_choice"]["disable_parallel_tool_use"] is True


def test_loop_stops_at_max_iterations(site, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-not-a-real-key")
    script = [[_Block(type="tool_use", id=f"t{i}", name="go_back", input={})] for i in range(3)]
    monkeypatch.setitem(sys.modules, "anthropic", _fake_anthropic(script, []))

    async def go():
        try:
            return await run_agent(site, confirm_spend=True, max_iterations=2)
        except Exception as exc:
            if "Executable" in str(exc):
                pytest.skip(str(exc))
            raise
    t = asyncio.run(go())
    assert t.iterations_used == 2 and "max_iterations=2" in t.final_text