"""Tests for git manager with a temporary repo."""

from __future__ import annotations

import subprocess
from pathlib import Path

from coding_operator.git_manager import GitManager


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_commit_now(tmp_path: Path):
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "a.txt").write_text("hello\n", encoding="utf-8")
    gm = GitManager(root=str(tmp_path))
    summary = gm.summary()
    assert summary["dirty"] is True
    result = gm.commit_now("test: add a.txt")
    assert result["ok"] is True
    assert "a.txt" in result["message"] or result["message"].startswith("test:")
    after = gm.summary()
    assert after["dirty"] is False
