"""
Operating-system-level screen, mouse and keyboard for an X11 display.

The desktop environment (desktop.py) uses this so that Claude controls a real
browser window the way a person would: it sees the whole screen, including the
tab bar and address bar, and its clicks and key presses are delivered to the
window by the X server (the XTEST extension), not injected into the page.

Only python-xlib and Pillow are needed (no xdotool or scrot), so the same code
runs inside the Docker image and on any Linux machine with an X server.

The key-name helpers at the top are plain functions and are unit-tested without
a display.
"""
from __future__ import annotations

import io
import time

# Names Claude may use for keys -> X11 keysym names.
_MODIFIER_KEYSYMS = {
    "ctrl": "Control_L",
    "control": "Control_L",
    "shift": "Shift_L",
    "alt": "Alt_L",
    "super": "Super_L",
    "meta": "Super_L",
    "cmd": "Super_L",
}

_NAMED_KEYSYMS = {
    "return": "Return",
    "enter": "Return",
    "escape": "Escape",
    "esc": "Escape",
    "backspace": "BackSpace",
    "delete": "Delete",
    "tab": "Tab",
    "space": "space",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "pageup": "Page_Up",
    "page_up": "Page_Up",
    "pagedown": "Page_Down",
    "page_down": "Page_Down",
    "home": "Home",
    "end": "End",
    "insert": "Insert",
}

# Mouse buttons in X11.
BUTTON_LEFT, BUTTON_MIDDLE, BUTTON_RIGHT = 1, 2, 3
WHEEL = {"up": 4, "down": 5, "left": 6, "right": 7}


def split_key_combo(text: str) -> list[str]:
    """'ctrl+shift+t' -> ['Control_L', 'Shift_L', 't']. Keys are returned as keysym names
    (or single characters), modifiers first in the order given."""
    names = []
    for part in text.split("+"):
        key = part.strip()
        if not key:
            continue
        low = key.lower()
        if low in _MODIFIER_KEYSYMS:
            names.append(_MODIFIER_KEYSYMS[low])
        elif low in _NAMED_KEYSYMS:
            names.append(_NAMED_KEYSYMS[low])
        elif len(key) == 1:
            names.append(key)
        elif low.startswith("f") and low[1:].isdigit():
            names.append(key.upper())  # F1 .. F12
        else:
            names.append(key[0].upper() + key[1:])
    return names


def keysym_for_char(char: str) -> int:
    """The X11 keysym for one character: Latin-1 characters use their own code, others use the Unicode range."""
    code = ord(char)
    if char == "\n":
        return 0xFF0D  # Return
    if char == "\t":
        return 0xFF09  # Tab
    if code < 0x20:
        raise ValueError(f"Cannot type control character {code!r}.")
    if code <= 0xFF:
        return code
    return 0x01000000 + code


class XDisplay:
    """A connection to one X display."""

    def __init__(self, display_name: str | None = None) -> None:
        from Xlib import X, display
        from Xlib.ext import xtest

        self._X = X
        self._xtest = xtest
        self.display = display.Display(display_name)
        if not self.display.has_extension("XTEST"):
            raise RuntimeError("The X server does not provide the XTEST extension, so input cannot be sent.")
        self.root = self.display.screen().root
        geometry = self.root.get_geometry()
        self.width, self.height = geometry.width, geometry.height

    def close(self) -> None:
        self.display.close()

    # Screen

    def screenshot_png(self) -> bytes:
        """The whole screen as a PNG (the pointer is not drawn)."""
        from PIL import Image

        raw = self.root.get_image(0, 0, self.width, self.height, self._X.ZPixmap, 0xFFFFFFFF)
        image = Image.frombytes("RGB", (self.width, self.height), raw.data, "raw", "BGRX")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    # Mouse

    def move(self, x: int, y: int) -> None:
        self._xtest.fake_input(self.display, self._X.MotionNotify, x=int(x), y=int(y))
        self.display.sync()

    def button_down(self, button: int = BUTTON_LEFT) -> None:
        self._xtest.fake_input(self.display, self._X.ButtonPress, button)
        self.display.sync()

    def button_up(self, button: int = BUTTON_LEFT) -> None:
        self._xtest.fake_input(self.display, self._X.ButtonRelease, button)
        self.display.sync()

    def click(self, button: int = BUTTON_LEFT, count: int = 1) -> None:
        for _ in range(count):
            self.button_down(button)
            self.button_up(button)
            time.sleep(0.05)

    def wheel(self, direction: str, clicks: int) -> None:
        button = WHEEL[direction]
        for _ in range(clicks):
            self.click(button)

    # Keyboard

    def _keycode(self, keysym: int) -> tuple[int, bool]:
        """(keycode, needs_shift) for a keysym, using the server's current key map."""
        found = list(self.display.keysym_to_keycodes(keysym))
        if not found:
            raise ValueError(f"No key produces keysym {keysym:#x} on this display.")
        keycode, index = found[0]
        return keycode, index in (1, 3)

    def _keycode_for_name(self, name: str) -> tuple[int, bool]:
        from Xlib import XK

        if len(name) == 1:
            return self._keycode(keysym_for_char(name))
        keysym = XK.string_to_keysym(name)
        if keysym == 0:
            raise ValueError(f"Unknown key name {name!r}.")
        return self._keycode(keysym)

    def _key_event(self, keycode: int, down: bool) -> None:
        kind = self._X.KeyPress if down else self._X.KeyRelease
        self._xtest.fake_input(self.display, kind, keycode)
        self.display.sync()

    def key_down(self, name: str) -> None:
        keycode, _ = self._keycode_for_name(name)
        self._key_event(keycode, True)

    def key_up(self, name: str) -> None:
        keycode, _ = self._keycode_for_name(name)
        self._key_event(keycode, False)

    def press_combo(self, text: str) -> None:
        """Press and release a combination such as 'ctrl+l' or 'Return'."""
        names = split_key_combo(text)
        if not names:
            raise ValueError(f"Empty key combination {text!r}.")
        codes = []
        for name in names:
            keycode, shift = self._keycode_for_name(name)
            codes.append((keycode, shift and len(names) == 1))
        shift_code = self._keycode_for_name("Shift_L")[0]
        for keycode, needs_shift in codes[:-1]:
            self._key_event(keycode, True)
        last, needs_shift = codes[-1]
        if needs_shift:
            self._key_event(shift_code, True)
        self._key_event(last, True)
        self._key_event(last, False)
        if needs_shift:
            self._key_event(shift_code, False)
        for keycode, _ in reversed(codes[:-1]):
            self._key_event(keycode, False)

    def type_text(self, text: str, delay: float = 0.02) -> None:
        shift_code = self._keycode_for_name("Shift_L")[0]
        for char in text:
            keycode, needs_shift = self._keycode(keysym_for_char(char))
            if needs_shift:
                self._key_event(shift_code, True)
            self._key_event(keycode, True)
            self._key_event(keycode, False)
            if needs_shift:
                self._key_event(shift_code, False)
            time.sleep(delay) 