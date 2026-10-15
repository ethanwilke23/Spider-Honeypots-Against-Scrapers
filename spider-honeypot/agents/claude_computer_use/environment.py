"""
The "computer" that Claude controls: a headless Playwright browser page.

Claude's computer-use tools use coordinates in the pixel space of the
screenshots it is sent. The screenshots here are the browser viewport
(1280x800), so its coordinates map directly onto Playwright's.

Scope:
  - Claude can click, scroll, type and press keys inside the page. There is
    no address bar, so it can only follow what is visible on the page.
  - The zoom action is disabled (see agent_loop.py) rather than implemented.
"""
from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass

from playwright.async_api import Page, async_playwright

VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 800

SESSION_COOKIE_NAME = "hp_session"

# Modifier key names used by Claude -> Playwright names.
_MODIFIER_MAP = {"ctrl": "Control", "shift": "Shift", "alt": "Alt", "super": "Meta"}

# Key names that Playwright spells differently. Playwright accepts most
# other names directly (for example "Tab" and "ArrowDown").
_KEY_NAME_MAP = {
    "return": "Enter",
    "enter": "Enter",
    "escape": "Escape",
    "esc": "Escape",
    "backspace": "Backspace",
    "delete": "Delete",
    "tab": "Tab",
    "space": "Space",
    "up": "ArrowUp",
    "down": "ArrowDown",
    "left": "ArrowLeft",
    "right": "ArrowRight",
    "pagedown": "PageDown",
    "pageup": "PageUp",
    "home": "Home",
    "end": "End",
}


def translate_key_combo(text: str) -> str:
    """Convert a key combination to Playwright's names: 'ctrl+s' becomes
    'Control+s' and 'Return' becomes 'Enter'. Other keys pass through."""
    parts = text.split("+")
    translated = []
    for part in parts:
        key = part.strip()
        low = key.lower()
        if low in _MODIFIER_MAP:
            translated.append(_MODIFIER_MAP[low])
        elif low in _KEY_NAME_MAP:
            translated.append(_KEY_NAME_MAP[low])
        elif len(key) == 1:
            translated.append(key)
        else:
            translated.append(key[0].upper() + key[1:])
    return "+".join(translated)


def parse_modifiers(text: str | None) -> list[str]:
    """Convert 'ctrl+shift' to ['Control', 'Shift']."""
    if not text:
        return []
    return [_MODIFIER_MAP.get(part.strip().lower(), part.strip()) for part in text.split("+")]


@dataclass
class ActionLogEntry:
    name: str
    input: dict
    result_summary: str


class ComputerEnvironment:
    """Wraps a single headless Playwright page as the computer-use target."""

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._context = None
        self._page: Page | None = None
        self._cursor_x = 0
        self._cursor_y = 0
        self.action_log: list[ActionLogEntry] = []

    async def start(self, start_url: str) -> None:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        self._context = await self._browser.new_context(
            viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT}
        )
        self._page = await self._context.new_page()
        await self._page.goto(start_url, wait_until="domcontentloaded")

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    @property
    def current_url(self) -> str:
        return self._page.url if self._page else ""

    async def get_session_cookie(self) -> str | None:
        """Return the server's hp_session cookie value, if present."""
        if not self._context:
            return None
        cookies = await self._context.cookies()
        return next((c["value"] for c in cookies if c["name"] == SESSION_COOKIE_NAME), None)

    async def screenshot_base64(self) -> str:
        png_bytes = await self._page.screenshot(type="png")
        return base64.b64encode(png_bytes).decode("ascii")

    async def execute(self, name: str, tool_input: dict) -> str | list[dict]:
        """
        Run one computer-tool action. Returns "OK", a short text result, or
        an image block for screenshots. Raises on failure; the agent loop
        turns that into an error result.
        """
        page = self._page
        assert page is not None, "environment not started"

        if name == "screenshot":
            b64 = await self.screenshot_base64()
            self.action_log.append(ActionLogEntry(name, tool_input, "screenshot captured"))
            return [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}}]

        if name == "zoom":
            raise RuntimeError("zoom is disabled in this environment (see configs in agent_loop.py)")

        if name in ("left_click", "right_click", "middle_click", "double_click", "triple_click"):
            coord = tool_input.get("coordinate")
            if coord is not None:
                self._cursor_x, self._cursor_y = coord
            button = {"left_click": "left", "right_click": "right", "middle_click": "middle"}.get(name, "left")
            click_count = {"double_click": 2, "triple_click": 3}.get(name, 1)
            modifiers = parse_modifiers(tool_input.get("text"))
            for mod in modifiers:
                await page.keyboard.down(mod)
            await page.mouse.click(self._cursor_x, self._cursor_y, button=button, click_count=click_count)
            for mod in modifiers:
                await page.keyboard.up(mod)
            self.action_log.append(
                ActionLogEntry(name, tool_input, f"{name} at ({self._cursor_x}, {self._cursor_y})")
            )
            return "OK"

        if name == "left_click_drag":
            sx, sy = tool_input["start_coordinate"]
            ex, ey = tool_input["coordinate"]
            await page.mouse.move(sx, sy)
            await page.mouse.down()
            await page.mouse.move(ex, ey)
            await page.mouse.up()
            self._cursor_x, self._cursor_y = ex, ey
            self.action_log.append(ActionLogEntry(name, tool_input, f"dragged ({sx},{sy}) -> ({ex},{ey})"))
            return "OK"

        if name == "mouse_move":
            x, y = tool_input["coordinate"]
            await page.mouse.move(x, y)
            self._cursor_x, self._cursor_y = x, y
            self.action_log.append(ActionLogEntry(name, tool_input, f"moved to ({x},{y})"))
            return "OK"

        if name == "left_mouse_down":
            await page.mouse.down()
            self.action_log.append(ActionLogEntry(name, tool_input, "left button down"))
            return "OK"

        if name == "left_mouse_up":
            await page.mouse.up()
            self.action_log.append(ActionLogEntry(name, tool_input, "left button up"))
            return "OK"

        if name == "cursor_position":
            text = f"X={self._cursor_x}, Y={self._cursor_y}"
            self.action_log.append(ActionLogEntry(name, tool_input, text))
            return text

        if name == "scroll":
            direction = tool_input["scroll_direction"]
            amount = tool_input.get("scroll_amount", 3)
            coord = tool_input.get("coordinate")
            if coord is not None:
                await page.mouse.move(*coord)
                self._cursor_x, self._cursor_y = coord
            dx, dy = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}[direction]
            # 100 pixels per scroll unit is an assumption; adjust it if
            # scrolling looks too far or too short.
            await page.mouse.wheel(dx * amount * 100, dy * amount * 100)
            self.action_log.append(ActionLogEntry(name, tool_input, f"scrolled {direction} x{amount}"))
            return "OK"

        if name == "type":
            text = tool_input["text"]
            await page.keyboard.type(text)
            self.action_log.append(ActionLogEntry(name, tool_input, f"typed {len(text)} chars"))
            return "OK"

        if name == "key":
            combo = translate_key_combo(tool_input["text"])
            repeat = tool_input.get("repeat", 1)
            for _ in range(repeat):
                await page.keyboard.press(combo)
            self.action_log.append(ActionLogEntry(name, tool_input, f"pressed {combo} x{repeat}"))
            return "OK"

        if name == "hold_key":
            combo = translate_key_combo(tool_input["text"])
            duration = tool_input["duration"]
            await page.keyboard.down(combo)
            await asyncio.sleep(duration)
            await page.keyboard.up(combo)
            self.action_log.append(ActionLogEntry(name, tool_input, f"held {combo} for {duration}s"))
            return "OK"

        if name == "wait":
            duration = tool_input["duration"]
            await asyncio.sleep(duration)
            self.action_log.append(ActionLogEntry(name, tool_input, f"waited {duration}s"))
            return "OK"

        raise RuntimeError(f"Unhandled computer-use member: {name}")