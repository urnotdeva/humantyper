"""Git status / commit helpers for the operator."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable


class GitManager:
    def __init__(self, project_root_provider: Callable[[], str] | None = None, root: str | None = None):
        self._root = root
        self._provider = project_root_provider

    @property
    def root(self) -> Path | None:
        raw = self._root or (self._provider() if self._provider else "")
        if not raw:
            return None
        path = Path(raw).expanduser().resolve()
        return path if path.exists() else None

    def set_root(self, root: str) -> None:
        self._root = root

    def _run(self, *args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
        cwd = self.root
        if cwd is None:
            raise RuntimeError("No project_root set. Arm with project_root or set it in the GUI.")
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=check,
        )

    def summary(self) -> dict:
        if self.root is None:
            return {"branch": "", "last_commit": "", "dirty": False, "error": "no project_root"}
        try:
            branch = self._run("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
            last = self._run("log", "-1", "--pretty=format:%h %s").stdout.strip()
            status = self._run("status", "--porcelain").stdout
            staged = [ln[3:] for ln in status.splitlines() if ln and ln[0] in "MADRCT"]
            modified = [ln[3:] for ln in status.splitlines() if ln and ln[1] in "MADRCT?"]
            diff_stat = self._run("diff", "--stat").stdout.strip()
            return {
                "branch": branch,
                "last_commit": last,
                "dirty": bool(status.strip()),
                "staged": staged,
                "modified": modified,
                "diff_stat": diff_stat,
            }
        except Exception as exc:
            return {"branch": "", "last_commit": "", "dirty": False, "error": str(exc)}

    def commit_now(self, message: str | None = None) -> dict:
        info = self.summary()
        if info.get("error"):
            return {"ok": False, "error": info["error"]}
        if not info.get("dirty"):
            return {"ok": False, "error": "nothing to commit", **info}

        # Stage tracked modifications + untracked (sensible default)
        self._run("add", "-A")
        msg = (message or "").strip() or self._default_message(info)
        result = self._run("commit", "-m", msg)
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "commit failed").strip()
            if "nothing to commit" in err.lower():
                return {"ok": False, "error": "nothing to commit"}
            return {"ok": False, "error": err}
        after = self.summary()
        return {
            "ok": True,
            "message": msg,
            "commit": after.get("last_commit", ""),
            "branch": after.get("branch", ""),
        }

    def commit_checkpoint(self, message: str | None = None, size: str = "small") -> dict:
        info = self.summary()
        if not info.get("dirty"):
            return {"ok": True, "skipped": True, "reason": "clean working tree"}
        prefix = {
            "small": "chore",
            "medium": "feat",
            "large": "feat",
        }.get(size, "chore")
        msg = message or f"{prefix}: checkpoint ({size})"
        # Prefer coherent unit: if only a few files, use file list in message
        if not message:
            files = (info.get("modified") or [])[:5]
            if files:
                msg = f"{prefix}: update {', '.join(Path(f).name for f in files)}"
        return self.commit_now(msg)

    def _default_message(self, info: dict) -> str:
        files = info.get("modified") or info.get("staged") or []
        names = [Path(f).name for f in files[:5]]
        if not names:
            return "chore: operator checkpoint"
        return f"chore: update {', '.join(names)}"
