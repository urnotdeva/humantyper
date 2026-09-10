"""Optional break manager (mouse wander). Off by default for Operator."""

from __future__ import annotations

import math
import random
import subprocess
import time


def get_active_window_bounds(margin_top=15, margin_left=15, margin_right=15, margin_bottom=15):
    """Linux xdotool helper. Returns (min_x, min_y, max_x, max_y) or None."""
    try:
        out = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowgeometry", "--shell"],
            capture_output=True,
            text=True,
            timeout=1.0,
            check=True,
        ).stdout
        vals = {}
        for line in out.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                vals[k] = v
        x, y = int(vals["X"]), int(vals["Y"])
        w, h = int(vals["WIDTH"]), int(vals["HEIGHT"])
        min_x, min_y = x + margin_left, y + margin_top
        max_x, max_y = x + w - margin_right, y + h - margin_bottom
        if max_x <= min_x or max_y <= min_y:
            return None
        return (min_x, min_y, max_x, max_y)
    except Exception:
        return None


class BreakManager:
    def __init__(
        self,
        mouse_backend,
        keyboard_backend,
        screen_w,
        screen_h,
        avg_interval=60.0,
        avg_duration=5.0,
        margin_top=100,
        margin_left=60,
        margin_right=25,
        margin_bottom=35,
    ):
        self.mouse = mouse_backend
        self.kb = keyboard_backend
        self.margins = (margin_top, margin_left, margin_right, margin_bottom)
        self.screen_bounds = (
            margin_left,
            margin_top,
            screen_w - margin_right,
            screen_h - margin_bottom,
        )
        self.avg_interval = avg_interval
        self.avg_duration = avg_duration
        self.next_break_at = time.time() + self._jitter(avg_interval, 0.15)

    @staticmethod
    def _jitter(base, frac):
        return max(1.0, random.gauss(base, base * frac))

    def due(self):
        return time.time() >= self.next_break_at

    def _clamp_point(self, origin, min_r, max_r, bounds):
        minx, miny, maxx, maxy = bounds
        angle = random.uniform(0, math.tau)
        r = random.uniform(min_r, max_r)
        x = min(max(origin[0] + r * math.cos(angle), minx), maxx)
        y = min(max(origin[1] + r * math.sin(angle), miny), maxy)
        return (x, y)

    def take_break(self, stop_event):
        duration = self._jitter(self.avg_duration, 0.25)
        deadline = time.time() + duration
        bounds = get_active_window_bounds(*self.margins) or self.screen_bounds

        pos0 = self.mouse.get_position()
        minx, miny, maxx, maxy = bounds
        pos0 = (min(max(pos0[0], minx), maxx), min(max(pos0[1], miny), maxy))

        pos1 = self._clamp_point(pos0, 80, 220, bounds)
        self.mouse.human_move(pos0, pos1, target_width=220, stop_event=stop_event)

        pos2 = self._clamp_point(pos1, 60, 180, bounds)
        self.mouse.press_button()
        self.mouse.human_move(pos1, pos2, target_width=140, stop_event=stop_event)
        self.mouse.release_button()

        if stop_event.is_set():
            raise InterruptedError
        time.sleep(min(0.6, max(0.0, deadline - time.time()) * 0.4))

        pos3 = self._clamp_point(pos2, 40, 150, bounds)
        self.mouse.human_move(pos2, pos3, target_width=45, stop_event=stop_event)
        self.mouse.click()

        if stop_event.is_set():
            raise InterruptedError
        remaining = deadline - time.time()
        if remaining > 0:
            time.sleep(remaining)

        if hasattr(self.kb, "ctrl_end"):
            self.kb.ctrl_end()
        time.sleep(random.uniform(0.1, 0.3))
        self.next_break_at = time.time() + self._jitter(self.avg_interval, 0.2)
