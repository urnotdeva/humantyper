"""Launch VS Code and Cursor and arrange them side by side."""

from __future__ import annotations

import platform
import shutil
import subprocess

MENU_BAR = 25


def _osascript(script: str) -> str:
    out = subprocess.run(
        ["osascript", "-e", script], capture_output=True, text=True, timeout=15
    )
    return out.stdout.strip()


def _screen_size_mac() -> tuple[int, int]:
    raw = _osascript('tell application "Finder" to get bounds of window of desktop')
    try:
        parts = [int(x.strip()) for x in raw.split(",")]
    except ValueError:
        parts = []
    if len(parts) == 4:
        return parts[2], parts[3]
    return 1440, 900


def _place_mac(process: str, x: int, y: int, w: int, h: int) -> bool:
    script = (
        'tell application "System Events"\n'
        f'  if not (exists process "{process}") then return false\n'
        f'  tell process "{process}"\n'
        "    if (count of windows) is 0 then return false\n"
        f"    set position of window 1 to {{{x}, {y}}}\n"
        f"    set size of window 1 to {{{w}, {h}}}\n"
        "  end tell\n"
        "  return true\n"
        "end tell"
    )
    return _osascript(script) == "true"


def _screen_size_linux() -> tuple[int, int]:
    try:
        out = subprocess.run(["xdpyinfo"], capture_output=True, text=True, timeout=5).stdout
        for line in out.splitlines():
            if "dimensions:" in line:
                w, h = line.split()[1].split("x")
                return int(w), int(h)
    except Exception:
        pass
    return 1920, 1080


def _place_linux(title: str, x: int, y: int, w: int, h: int) -> bool:
    if not shutil.which("wmctrl"):
        return False
    r = subprocess.run(
        ["wmctrl", "-r", title, "-e", f"0,{x},{y},{w},{h}"],
        capture_output=True,
        timeout=5,
    )
    return r.returncode == 0


def launch_ides(project: str | None = None) -> None:
    if platform.system() == "Darwin":
        vscode = ["open", "-a", "Visual Studio Code"]
        if project:
            vscode.append(project)
        subprocess.run(vscode, check=False, timeout=15)
        subprocess.run(["open", "-a", "Cursor"], check=False, timeout=15)
        return
    if shutil.which("code"):
        cmd = ["code"] + ([project] if project else [])
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if shutil.which("cursor"):
        subprocess.Popen(["cursor"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def arrange_side_by_side() -> dict[str, bool]:
    if platform.system() == "Darwin":
        width, height = _screen_size_mac()
        half = width // 2
        top = MENU_BAR
        return {
            "vscode": _place_mac("Code", 0, top, half, height - top),
            "cursor": _place_mac("Cursor", half, top, width - half, height - top),
        }
    width, height = _screen_size_linux()
    half = width // 2
    return {
        "vscode": _place_linux("Visual Studio Code", 0, 0, half, height),
        "cursor": _place_linux("Cursor", half, 0, width - half, height),
    }
