"""Human-like typing engine with stop/pause support."""

from __future__ import annotations

import math
import random
import threading
import time
from typing import Callable

from human_typer.typos import FAST_BIGRAMS, PAUSE_AFTER, typo_for


class TypingEngine:
    def __init__(self, backend, pause_event: threading.Event | None = None):
        self.backend = backend
        self.stop_event = threading.Event()
        self.pause_event = pause_event or threading.Event()
        self.gate: Callable[[], None] | None = None
        self.reset_indent = False
        # pause_event set => paused (wait until cleared)

    def stop(self):
        self.stop_event.set()

    def reset_stop(self):
        self.stop_event.clear()

    def _sleep(self, seconds: float):
        end = time.time() + max(0.0, seconds)
        while time.time() < end:
            if self.stop_event.is_set():
                raise InterruptedError
            while self.pause_event.is_set():
                if self.stop_event.is_set():
                    raise InterruptedError
                time.sleep(0.05)
            remaining = end - time.time()
            if remaining <= 0:
                break
            time.sleep(min(0.02, remaining))

    def wait_if_paused(self):
        while self.pause_event.is_set():
            if self.stop_event.is_set():
                raise InterruptedError
            time.sleep(0.05)

    def _press(self, ch: str):
        if self.gate is not None:
            self.gate()
        if ch == "\n":
            self.backend.enter()
            if self.reset_indent and hasattr(self.backend, "hotkey"):
                time.sleep(0.03)
                self.backend.hotkey("shift", "home")
        elif ch == "\t":
            self.backend.tab()
        else:
            self.backend.type_char(ch)

    def _backspace(self):
        self.backend.backspace()

    def type_text(
        self,
        text,
        avg_wpm=55,
        wpm_variance_pct=25,
        error_rate=0.03,
        skip_leading_ws=True,
        on_progress: Callable[[int, int], None] | None = None,
        break_manager=None,
    ):
        """
        avg_wpm: target average words-per-minute (1 word = 5 chars)
        wpm_variance_pct: 0-60, how much instantaneous speed wobbles
        error_rate: 0.0-0.15, probability per character of a typo
        skip_leading_ws: drop leading whitespace on each line for editor auto-indent
        """
        self.reset_stop()
        base_cps = (avg_wpm * 5) / 60.0
        sigma = max(0.05, wpm_variance_pct / 100.0)
        drift_phase = random.uniform(0, math.tau)
        char_index = 0
        total_chars = len(text)

        lines = text.split("\n")
        for li, line in enumerate(lines):
            content = line
            if skip_leading_ws:
                stripped = line.lstrip(" \t")
                content = stripped if line[: len(line) - len(stripped)] else line

            i = 0
            while i < len(content):
                if self.stop_event.is_set():
                    raise InterruptedError
                self.wait_if_paused()

                if break_manager and break_manager.due():
                    break_manager.take_break(self.stop_event)

                ch = content[i]
                drift = 1.0 + 0.15 * math.sin(drift_phase + char_index / 40.0)
                mean_interval = drift / (base_cps + 1e-6)

                if i + 1 < len(content):
                    bg = content[i : i + 2].lower()
                    if bg in FAST_BIGRAMS:
                        mean_interval *= 0.75

                interval = random.lognormvariate(math.log(max(mean_interval, 0.01)), sigma)
                interval = min(interval, mean_interval * 4)

                if random.random() < error_rate and ch.isalnum():
                    wrong = typo_for(ch)
                    if wrong:
                        self._sleep(interval)
                        self._press(wrong)
                        char_index += 1
                        self._sleep(random.uniform(0.15, 0.55))
                        self._backspace()
                        self._sleep(random.uniform(0.05, 0.15))
                        self._press(ch)
                        char_index += 1
                        i += 1
                        if on_progress:
                            on_progress(char_index, total_chars)
                        continue

                self._sleep(interval)
                self._press(ch)
                char_index += 1
                i += 1
                if on_progress:
                    on_progress(char_index, total_chars)

                if ch in PAUSE_AFTER and random.random() < 0.3:
                    self._sleep(random.uniform(0.2, 1.2))

            if li != len(lines) - 1:
                self._sleep(
                    random.lognormvariate(math.log(max(1.0 / (base_cps + 1e-6), 0.01)), sigma)
                )
                self._press("\n")
                char_index += 1
                if on_progress:
                    on_progress(char_index, total_chars)
