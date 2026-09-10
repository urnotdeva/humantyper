"""Linux keyboard/mouse backends (pynput + optional uinput)."""

from __future__ import annotations

import time

from human_typer.backends.pynput_backend import PynputKeyboardBackend, PynputMouseBackend
from human_typer.mouse_path import humanized_path

try:
    from evdev import UInput
    from evdev import ecodes as e

    EVDEV_AVAILABLE = True
except ImportError:
    EVDEV_AVAILABLE = False
    UInput = None  # type: ignore
    e = None  # type: ignore

BASE_MAP: dict = {}
SHIFT_MAP: dict = {}

if EVDEV_AVAILABLE:
    BASE_MAP = {
        **{c: getattr(e, f"KEY_{c.upper()}") for c in "abcdefghijklmnopqrstuvwxyz"},
        **{d: getattr(e, f"KEY_{d}") for d in "1234567890"},
        "`": e.KEY_GRAVE,
        "-": e.KEY_MINUS,
        "=": e.KEY_EQUAL,
        "[": e.KEY_LEFTBRACE,
        "]": e.KEY_RIGHTBRACE,
        "\\": e.KEY_BACKSLASH,
        ";": e.KEY_SEMICOLON,
        "'": e.KEY_APOSTROPHE,
        ",": e.KEY_COMMA,
        ".": e.KEY_DOT,
        "/": e.KEY_SLASH,
        " ": e.KEY_SPACE,
    }
    SHIFT_MAP = {
        "!": "1",
        "@": "2",
        "#": "3",
        "$": "4",
        "%": "5",
        "^": "6",
        "&": "7",
        "*": "8",
        "(": "9",
        ")": "0",
        "_": "-",
        "+": "=",
        "{": "[",
        "}": "]",
        "|": "\\",
        ":": ";",
        '"': "'",
        "<": ",",
        ">": ".",
        "?": "/",
        "~": "`",
    }

_UINPUT_KEY = {
    "enter": "KEY_ENTER",
    "tab": "KEY_TAB",
    "backspace": "KEY_BACKSPACE",
    "esc": "KEY_ESC",
    "escape": "KEY_ESC",
    "space": "KEY_SPACE",
    "up": "KEY_UP",
    "down": "KEY_DOWN",
    "left": "KEY_LEFT",
    "right": "KEY_RIGHT",
    "home": "KEY_HOME",
    "end": "KEY_END",
    "page_up": "KEY_PAGEUP",
    "page_down": "KEY_PAGEDOWN",
    "delete": "KEY_DELETE",
    "shift": "KEY_LEFTSHIFT",
    "ctrl": "KEY_LEFTCTRL",
    "alt": "KEY_LEFTALT",
}


class LinuxKeyboardBackend(PynputKeyboardBackend):
    name = "Linux (pynput / XTest)"


class LinuxMouseBackend(PynputMouseBackend):
    name = "Linux (pynput mouse)"


class UInputBackend:
    name = "Kernel uinput (virtual HID device)"

    def __init__(self, device_name="USB Keyboard", vendor=0x046D, product=0xC31C):
        if not EVDEV_AVAILABLE:
            raise RuntimeError("evdev not installed — pip install evdev")
        keys = set(BASE_MAP.values()) | {
            e.KEY_ENTER,
            e.KEY_TAB,
            e.KEY_BACKSPACE,
            e.KEY_LEFTSHIFT,
            e.KEY_LEFTCTRL,
            e.KEY_LEFTALT,
            e.KEY_END,
            e.KEY_HOME,
            e.KEY_UP,
            e.KEY_DOWN,
            e.KEY_LEFT,
            e.KEY_RIGHT,
            e.KEY_ESC,
            e.KEY_DELETE,
            e.KEY_PAGEUP,
            e.KEY_PAGEDOWN,
            e.KEY_SPACE,
        }
        capabilities = {e.EV_KEY: sorted(keys)}
        try:
            self.dev = UInput(
                capabilities, name=device_name, vendor=vendor, product=product, version=1
            )
        except PermissionError as exc:
            raise RuntimeError(
                "No permission to open /dev/uinput. Configure the uinput group."
            ) from exc
        time.sleep(1.0)

    def _code(self, name: str):
        attr = _UINPUT_KEY.get(name.lower())
        if not attr:
            raise ValueError(f"Unknown uinput key: {name}")
        return getattr(e, attr)

    def _tap(self, code, shift=False):
        if shift:
            self.dev.write(e.EV_KEY, e.KEY_LEFTSHIFT, 1)
        self.dev.write(e.EV_KEY, code, 1)
        self.dev.syn()
        self.dev.write(e.EV_KEY, code, 0)
        self.dev.syn()
        if shift:
            self.dev.write(e.EV_KEY, e.KEY_LEFTSHIFT, 0)
            self.dev.syn()

    def type_char(self, ch):
        if ch in BASE_MAP:
            self._tap(BASE_MAP[ch])
        elif ch.isupper() and ch.lower() in BASE_MAP:
            self._tap(BASE_MAP[ch.lower()], shift=True)
        elif ch in SHIFT_MAP:
            self._tap(BASE_MAP[SHIFT_MAP[ch]], shift=True)

    def backspace(self):
        self._tap(e.KEY_BACKSPACE)

    def enter(self):
        self._tap(e.KEY_ENTER)

    def tab(self):
        self._tap(e.KEY_TAB)

    def key(self, name: str) -> None:
        self._tap(self._code(name))

    def hotkey(self, *keys: str) -> None:
        codes = []
        for k in keys:
            lower = k.lower()
            if lower in ("ctrl", "shift", "alt"):
                codes.append(self._code(lower))
            elif len(k) == 1 and k.lower() in BASE_MAP:
                codes.append(BASE_MAP[k.lower()])
            else:
                codes.append(self._code(k))
        for code in codes:
            self.dev.write(e.EV_KEY, code, 1)
            self.dev.syn()
        for code in reversed(codes):
            self.dev.write(e.EV_KEY, code, 0)
            self.dev.syn()

    def ctrl_end(self):
        self.hotkey("ctrl", "end")

    def close(self):
        self.dev.close()


class UInputMouseBackend:
    name = "Kernel uinput (virtual HID mouse)"

    def __init__(self, device_name="USB Optical Mouse", vendor=0x046D, product=0xC077):
        if not EVDEV_AVAILABLE:
            raise RuntimeError("evdev not installed — pip install evdev")
        capabilities = {
            e.EV_REL: [e.REL_X, e.REL_Y],
            e.EV_KEY: [e.BTN_LEFT, e.BTN_RIGHT],
        }
        try:
            self.dev = UInput(
                capabilities, name=device_name, vendor=vendor, product=product, version=1
            )
        except PermissionError as exc:
            raise RuntimeError("No permission to open /dev/uinput for mouse.") from exc
        time.sleep(0.5)
        from pynput.mouse import Controller as MouseController

        self._reader = MouseController()

    def get_position(self):
        return self._reader.position

    def _move_rel(self, dx, dy):
        if dx:
            self.dev.write(e.EV_REL, e.REL_X, int(round(dx)))
        if dy:
            self.dev.write(e.EV_REL, e.REL_Y, int(round(dy)))
        self.dev.syn()

    def human_move(self, start, end, target_width=60.0, stop_event=None):
        points, step_delay = humanized_path(start, end, target_width=target_width)
        prev = start
        for pt in points:
            if stop_event and stop_event.is_set():
                raise InterruptedError
            self._move_rel(pt[0] - prev[0], pt[1] - prev[1])
            prev = pt
            time.sleep(step_delay)

    def press_button(self):
        self.dev.write(e.EV_KEY, e.BTN_LEFT, 1)
        self.dev.syn()

    def release_button(self):
        self.dev.write(e.EV_KEY, e.BTN_LEFT, 0)
        self.dev.syn()

    def click(self):
        self.press_button()
        time.sleep(0.03)
        self.release_button()

    def close(self):
        self.dev.close()
