"""
Tests for the desktop environment (agents/claude_computer_use/desktop.py and x11.py).

The key-name and browser-flag helpers are tested everywhere. The live test starts a real
browser on a virtual screen, so it runs only on Linux with Xvfb installed (as in the Docker
image) and is skipped on other machines.
"""
import asyncio
import shutil
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from agents.claude_computer_use.desktop import DesktopEnvironment, restriction_args
from agents.claude_computer_use.x11 import keysym_for_char, split_key_combo


def test_key_combinations_are_translated_to_x11_names():
    assert split_key_combo("ctrl+l") == ["Control_L", "l"]
    assert split_key_combo("ctrl+shift+T") == ["Control_L", "Shift_L", "T"]
    assert split_key_combo("Return") == ["Return"]
    assert split_key_combo("alt+Left") == ["Alt_L", "Left"]
    assert split_key_combo("PageDown") == ["Page_Down"]
    assert split_key_combo("f5") == ["F5"]


def test_characters_map_to_keysyms():
    assert keysym_for_char("a") == ord("a")
    assert keysym_for_char("/") == ord("/")
    assert keysym_for_char("\n") == 0xFF0D
    assert keysym_for_char("€") == 0x01000000 + ord("€")
    with pytest.raises(ValueError):
        keysym_for_char("\x01")


def test_network_restriction_allows_only_the_test_site():
    args = restriction_args("http://host.docker.internal:8000/")
    assert "--proxy-bypass-list=host.docker.internal:8000" in args
    assert any(a.startswith("--proxy-server=") for a in args)
    assert restriction_args("http://127.0.0.1/")[1] == "--proxy-bypass-list=127.0.0.1:80"
    with pytest.raises(ValueError):
        restriction_args("not a url")


class _Pages(BaseHTTPRequestHandler):
    def do_GET(self):
        body = f"<html><title>{self.path}</title><body><a href='/two'>go to two</a></body></html>".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Set-Cookie", "hp_session=abc123; Path=/")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.mark.skipif(
    not (sys.platform.startswith("linux") and shutil.which("Xvfb")),
    reason="needs Linux with Xvfb (runs in the Docker image)",
)
def test_a_real_browser_can_be_driven_through_the_address_bar():
    server = HTTPServer(("127.0.0.1", 0), _Pages)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"

    async def scenario():
        env = DesktopEnvironment()
        await env.start(base + "/")
        try:
            assert env.current_url == base + "/"
            assert await env.get_session_cookie() == "abc123"

            # Type an address, as a person would.
            await env.execute("key", {"text": "ctrl+l"})
            await env.execute("type", {"text": f"{base}/typed\n"})
            assert env.current_url == base + "/typed"

            # Back button through the keyboard.
            await env.execute("key", {"text": "alt+Left"})
            assert env.current_url == base + "/"

            # Screenshots are of the whole screen, not just the page.
            shot = await env.execute("screenshot", {})
            assert shot[0]["source"]["media_type"] == "image/png"

            # Anything other than the test site is blocked.
            await env.execute("key", {"text": "ctrl+l"})
            await env.execute("type", {"text": "http://example.com/\n"})
            await asyncio.sleep(1.5)
            assert env.current_url.startswith("chrome-error://")
        finally:
            await env.close()

    try:
        asyncio.run(scenario())
    finally:
        server.shutdown()


@pytest.mark.skipif(
    not (sys.platform.startswith("linux") and shutil.which("Xvfb")),
    reason="needs Linux with Xvfb (runs in the Docker image)",
)
def test_the_agent_loop_drives_the_desktop_with_a_scripted_model(monkeypatch):
    """The whole loop with a fake model (no API call): type an address, then finish with text."""
    import types

    from agents.claude_computer_use import agent_loop

    server = HTTPServer(("127.0.0.1", 0), _Pages)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"

    def block(**fields):
        return types.SimpleNamespace(model_dump=lambda: dict(fields), **fields)

    script = [
        [block(type="tool_use", id="1", name="key", input={"text": "ctrl+l"}, toolset_name="computer"),
         block(type="tool_use", id="2", name="type", input={"text": f"{base}/typed\n"}, toolset_name="computer"),
         block(type="tool_use", id="3", name="screenshot", input={}, toolset_name="computer")],
        [block(type="text", text="Done: nothing sensitive found.")],
    ]

    class FakeMessages:
        async def create(self, **kwargs):
            return types.SimpleNamespace(content=script.pop(0))

    class FakeClient:
        def __init__(self, api_key):
            self.messages = FakeMessages()

    fake_module = types.SimpleNamespace(AsyncAnthropic=FakeClient)
    monkeypatch.setitem(sys.modules, "anthropic", fake_module)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    try:
        transcript = asyncio.run(agent_loop.run_agent(base + "/", confirm_spend=True, max_iterations=4, desktop=True))
    finally:
        server.shutdown()

    assert transcript.environment == "desktop"
    assert transcript.final_url == base + "/typed"
    assert transcript.session_id == "abc123"
    assert transcript.final_text == "Done: nothing sensitive found."
    assert transcript.iterations_used == 2


# The Docker wrapper (agents/claude_computer_use/docker_run.py). Docker itself is not run here.

def test_local_addresses_are_rewritten_for_the_container():
    from agents.claude_computer_use.docker_run import container_base_url

    assert container_base_url("http://127.0.0.1:8000") == "http://host.docker.internal:8000"
    assert container_base_url("http://localhost:8000/x") == "http://host.docker.internal:8000/x"
    assert container_base_url("http://example.test:8000") == "http://example.test:8000"


def test_the_docker_command_passes_the_key_by_name_and_mounts_read_only():
    from pathlib import Path

    from agents.claude_computer_use.docker_run import IMAGE, docker_run_command

    command = docker_run_command("c1", ["python", "-m", "x"], Path("/host/out"), pass_api_key=True, platform="win32")
    assert command[:3] == ["docker", "run", "--rm"]
    assert "ANTHROPIC_API_KEY" in command and not any("sk-" in part for part in command)
    assert any(part.endswith("/app/agents:ro") for part in command)
    assert "--add-host" not in command  # Docker Desktop provides the host name itself
    assert command[-4:] == [IMAGE, "python", "-m", "x"]
    assert "--add-host" in docker_run_command("c1", [], Path("/o"), True, platform="linux")
    assert "ANTHROPIC_API_KEY" not in docker_run_command("c1", [], Path("/o"), False)


def test_container_paths_in_the_output_are_mapped_to_the_host():
    from pathlib import Path

    from agents.claude_computer_use.docker_run import map_container_paths

    out = "Finished.\nRun record written to /out/20261015T101010Z.json\n"
    mapped = map_container_paths(out, Path("/host/runs"))
    assert mapped.strip().endswith(str(Path("/host/runs") / "20261015T101010Z.json"))


def test_the_docker_wrapper_does_nothing_without_a_flag(capsys, monkeypatch):
    from agents.claude_computer_use import docker_run

    monkeypatch.setattr(sys, "argv", ["docker_run"])
    assert docker_run.main() == 2
    assert "Nothing was run" in capsys.readouterr().out


def test_the_scheduler_runs_claude_through_the_docker_wrapper():
    from experiment.config import AGENTS

    config = AGENTS["claude_computer_use"]
    assert config.module == "agents.claude_computer_use.docker_run"
    assert "--confirm-spend" in config.extra_args and config.costs_money
    assert config.timeout_seconds > 840  # the wrapper stops its container at 840 s