"""
The desktop "computer" that Claude controls: a real browser window on a virtual screen.

Unlike environment.py (a bare Playwright page with no browser interface), this
gives Claude what a person has: a full-screen picture that includes the tab bar
and the address bar, and a mouse and keyboard whose events go through the
operating system. Claude can type a web address, use keyboard shortcuts, open
tabs and press the back button, as well as click links on the page.

Pieces:
  - An Xvfb virtual screen (started here unless DISPLAY already points at one).
  - Chromium, started with a visible window through Playwright. Playwright is
    used only to start the browser and to read the page address and the
    session cookie for the run record; every action Claude takes goes through
    x11.py.
  - Network restriction: all requests from the browser are sent to a dead proxy
    except those for the test site, so the agent cannot reach the open internet
    even if it types another address. (The Anthropic API calls are made by the
    Python process, not the browser, and are unaffected.)

It has the same interface as ComputerEnvironment (start, execute,
screenshot_base64, current_url, get_session_cookie, close), so the agent loop
works with either. Run it inside the Docker image (docker/claude-desktop/);
the scheduler does this for the Claude agent.
"""
from __future__ import annotations

import asyncio
import base64
import os
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

from agents.claude_computer_use.environment import SESSION_COOKIE_NAME, ActionLogEntry
from agents.claude_computer_use import x11

SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 800

# Time for the page to react after an input before Claude's next screenshot.
SETTLE_SECONDS = 0.6
# Scroll clicks are sent as mouse-wheel presses at the pointer; Chromium scrolls a fixed distance per press.
BUTTONS = {"left_click": x11.BUTTON_LEFT, "right_click": x11.BUTTON_RIGHT, "middle_click": x11.BUTTON_MIDDLE}
CLICK_COUNTS = {"double_click": 2, "triple_click": 3}

# Chromium options. The window fills the screen; the infobar that says the browser is
# automated is removed (it would take up space and is not what a user sees).
BROWSER_ARGS = [
    "--window-position=0,0",
    f"--window-size={SCREEN_WIDTH},{SCREEN_HEIGHT}",
    "--disable-dev-shm-usage",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-infobars",
    "--disable-session-crashed-bubble",
    "--disable-save-password-bubble",
    "--disable-features=Translate,PasswordManagerOnboarding",
    "--password-store=basic",
]

DEAD_PROXY = "http://127.0.0.1:1"


def restriction_args(start_url: str) -> list[str]:
    """Browser flags that allow only the test site (host and port of start_url)."""
    parsed = urlparse(start_url)
    if not parsed.hostname:
        raise ValueError(f"Not a usable URL: {start_url!r}")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    allowed = f"{parsed.hostname}:{port}"
    return [f"--proxy-server={DEAD_PROXY}", f"--proxy-bypass-list={allowed}"]


def _free_display_number() -> int:
    for number in range(90, 200):
        if not Path(f"/tmp/.X11-unix/X{number}").exists() and not Path(f"/tmp/.X{number}-lock").exists():
            return number
    raise RuntimeError("No free X display number between :90 and :199.")


def start_xvfb(width: int = SCREEN_WIDTH, height: int = SCREEN_HEIGHT) -> tuple[subprocess.Popen, str]:
    """Start a virtual screen and return (process, display name such as ':90')."""
    if not shutil.which("Xvfb"):
        raise RuntimeError("Xvfb is not installed. Use the Docker image (docker/claude-desktop/) or install xvfb.")
    number = _free_display_number()
    process = subprocess.Popen(
        ["Xvfb", f":{number}", "-screen", "0", f"{width}x{height}x24", "-nolisten", "tcp"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    socket_path = Path(f"/tmp/.X11-unix/X{number}")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if socket_path.exists():
            return process, f":{number}"
        if process.poll() is not None:
            raise RuntimeError("Xvfb exited immediately; the virtual screen could not be started.")
        time.sleep(0.1)
    process.terminate()
    raise RuntimeError("Xvfb did not become ready within 10 seconds.")


class DesktopEnvironment:
    """A headed Chromium window on a virtual screen, driven by OS-level input."""

    def __init__(self, restrict_network: bool = True, no_sandbox: bool | None = None) -> None:
        self.restrict_network = restrict_network
        # Chromium's sandbox cannot run as root inside a container.
        self.no_sandbox = (hasattr(os, "geteuid") and os.geteuid() == 0) if no_sandbox is None else no_sandbox
        self.action_log: list[ActionLogEntry] = []
        self._xvfb: subprocess.Popen | None = None
        self._previous_display: str | None = None
        self._x: x11.XDisplay | None = None
        self._playwright = None
        self._browser = None
        self._context = None
        self._cursor_x = 0
        self._cursor_y = 0

    async def start(self, start_url: str) -> None:
        from playwright.async_api import async_playwright

        self._previous_display = os.environ.get("DISPLAY")
        if not self._previous_display:
            self._xvfb, display_name = start_xvfb()
            os.environ["DISPLAY"] = display_name

        try:
            self._x = x11.XDisplay()
            args = list(BROWSER_ARGS)
            if self.no_sandbox:
                args.append("--no-sandbox")
            if self.restrict_network:
                args += restriction_args(start_url)

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=False, args=args, ignore_default_args=["--enable-automation"]
            )
            self._context = await self._browser.new_context(no_viewport=True)
            page = await self._context.new_page()
            await page.goto(start_url, wait_until="domcontentloaded")
            await asyncio.sleep(SETTLE_SECONDS)
        except Exception:
            await self.close()
            raise

    async def close(self) -> None:
        for step in (
            lambda: self._browser.close() if self._browser else None,
            lambda: self._playwright.stop() if self._playwright else None,
        ):
            try:
                result = step()
                if result is not None:
                    await result
            except Exception:
                pass
        self._browser = self._playwright = self._context = None
        if self._x:
            try:
                self._x.close()
            except Exception:
                pass
            self._x = None
        if self._xvfb:
            self._xvfb.terminate()
            try:
                self._xvfb.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._xvfb.kill()
            self._xvfb = None
            if self._previous_display is None:
                os.environ.pop("DISPLAY", None)

    # What the run record needs

    @property
    def current_url(self) -> str:
        """The address of the most recently opened tab that is still open."""
        if not self._context:
            return ""
        pages = [p for p in self._context.pages if not p.is_closed()]
        return pages[-1].url if pages else ""

    async def get_session_cookie(self) -> str | None:
        if not self._context:
            return None
        cookies = await self._context.cookies()
        return next((c["value"] for c in cookies if c["name"] == SESSION_COOKIE_NAME), None)

    # What Claude sees and does

    async def screenshot_base64(self) -> str:
        png = await asyncio.to_thread(self._x.screenshot_png)
        return base64.b64encode(png).decode("ascii")

    async def _settle(self) -> None:
        await asyncio.sleep(SETTLE_SECONDS)

    async def _move(self, x: int, y: int) -> None:
        await asyncio.to_thread(self._x.move, x, y)
        self._cursor_x, self._cursor_y = int(x), int(y)

    async def execute(self, name: str, tool_input: dict) -> str | list[dict]:
        """Run one computer-tool action. Same contract as ComputerEnvironment.execute."""
        assert self._x is not None, "environment not started"
        x = self._x

        def log(summary: str) -> None:
            self.action_log.append(ActionLogEntry(name, tool_input, summary))

        if name == "screenshot":
            b64 = await self.screenshot_base64()
            log("screenshot captured")
            return [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}}]

        if name == "zoom":
            raise RuntimeError("zoom is disabled in this environment (see configs in agent_loop.py)")

        if name in BUTTONS or name in CLICK_COUNTS:
            coord = tool_input.get("coordinate")
            if coord is not None:
                await self._move(*coord)
            modifiers = x11.split_key_combo(tool_input.get("text") or "")
            for mod in modifiers:
                await asyncio.to_thread(x.key_down, mod)
            try:
                await asyncio.to_thread(x.click, BUTTONS.get(name, x11.BUTTON_LEFT), CLICK_COUNTS.get(name, 1))
            finally:
                for mod in reversed(modifiers):
                    await asyncio.to_thread(x.key_up, mod)
            log(f"{name} at ({self._cursor_x}, {self._cursor_y})")
            await self._settle()
            return "OK"

        if name == "left_click_drag":
            sx, sy = tool_input["start_coordinate"]
            ex, ey = tool_input["coordinate"]
            await self._move(sx, sy)
            await asyncio.to_thread(x.button_down)
            await self._move(ex, ey)
            await asyncio.to_thread(x.button_up)
            log(f"dragged ({sx},{sy}) -> ({ex},{ey})")
            await self._settle()
            return "OK"

        if name == "mouse_move":
            mx, my = tool_input["coordinate"]
            await self._move(mx, my)
            log(f"moved to ({mx},{my})")
            return "OK"

        if name == "left_mouse_down":
            await asyncio.to_thread(x.button_down)
            log("left button down")
            return "OK"

        if name == "left_mouse_up":
            await asyncio.to_thread(x.button_up)
            log("left button up")
            return "OK"

        if name == "cursor_position":
            text = f"X={self._cursor_x}, Y={self._cursor_y}"
            log(text)
            return text

        if name == "scroll":
            direction = tool_input["scroll_direction"]
            amount = int(tool_input.get("scroll_amount", 3))
            coord = tool_input.get("coordinate")
            if coord is not None:
                await self._move(*coord)
            await asyncio.to_thread(x.wheel, direction, amount)
            log(f"scrolled {direction} x{amount}")
            await self._settle()
            return "OK"

        if name == "type":
            text = tool_input["text"]
            await asyncio.to_thread(x.type_text, text)
            log(f"typed {len(text)} chars")
            await self._settle()
            return "OK"

        if name == "key":
            combo = tool_input["text"]
            repeat = int(tool_input.get("repeat", 1))
            for _ in range(repeat):
                await asyncio.to_thread(x.press_combo, combo)
            log(f"pressed {combo} x{repeat}")
            await self._settle()
            return "OK"

        if name == "hold_key":
            names = x11.split_key_combo(tool_input["text"])
            duration = tool_input["duration"]
            for key in names:
                await asyncio.to_thread(x.key_down, key)
            await asyncio.sleep(duration)
            for key in reversed(names):
                await asyncio.to_thread(x.key_up, key)
            log(f"held {tool_input['text']} for {duration}s")
            await self._settle()
            return "OK"

        if name == "wait":
            duration = tool_input["duration"]
            await asyncio.sleep(duration)
            log(f"waited {duration}s")
            return "OK"

        raise RuntimeError(f"Unhandled computer-use member: {name}")