"""Compact control GUI for AI Coding Operator."""

from __future__ import annotations

import threading

from coding_operator.esc_watch import EscWatcher, user_stop_handler

import logging

from coding_operator import logs
from coding_operator.control_state import STATE
from coding_operator.executor import EXECUTOR
from coding_operator.git_manager import GitManager
from coding_operator.ipc import ControlAPI

DARK_BG = "#1e1e1e"
DARK_FIELD = "#2d2d30"
DARK_FG = "#d4d4d4"
DARK_ACCENT = "#0e639c"
DARK_BORDER = "#3c3c3c"
DARK_DANGER = "#a1260d"
DARK_OK = "#388a34"


def _require_tk():
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, scrolledtext, ttk
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "tkinter is not available in this Python. Install python-tk "
            "(e.g. brew install python-tk) or run: ai-coding-operator-daemon"
        ) from exc
    return tk, filedialog, messagebox, scrolledtext, ttk


def apply_dark_theme(root, ttk):
    root.configure(bg=DARK_BG)
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure(".", background=DARK_BG, foreground=DARK_FG, fieldbackground=DARK_FIELD)
    style.configure("TFrame", background=DARK_BG)
    style.configure("TLabel", background=DARK_BG, foreground=DARK_FG)
    style.configure("TButton", background=DARK_FIELD, foreground=DARK_FG)
    style.map("TButton", background=[("active", DARK_ACCENT)])
    style.configure("TCheckbutton", background=DARK_BG, foreground=DARK_FG)
    style.configure("TEntry", fieldbackground=DARK_FIELD, foreground=DARK_FG)
    style.configure("Horizontal.TProgressbar", background=DARK_ACCENT, troughcolor=DARK_FIELD)
    style.configure("Danger.TButton", background=DARK_DANGER, foreground=DARK_FG)
    style.configure("Ok.TButton", background=DARK_OK, foreground=DARK_FG)
    return style


class OperatorApp:
    def __init__(self, root, tk, filedialog, messagebox, scrolledtext, ttk):
        self.tk = tk
        self.filedialog = filedialog
        self.messagebox = messagebox
        self.ttk = ttk
        self.root = root
        root.title("AI Coding Operator")
        root.geometry("640x560")
        root.minsize(520, 420)
        apply_dark_theme(root, ttk)

        self.state = STATE
        self.executor = EXECUTOR
        self.git = GitManager(project_root_provider=lambda: self.state.project_root)
        self._esc_listener = None
        self._confirm_shown_for = ""
        self.api = ControlAPI(self.executor)
        try:
            self.api.start()
        except OSError as exc:
            messagebox.showwarning(
                "Control API",
                f"Could not bind localhost:8765 ({exc}). MCP may run standalone.",
            )
            self.api = None

        self.project_var = tk.StringVar(value=self.state.project_root)
        self.task_var = tk.StringVar(value="(set task in Cursor chat)")
        self.action_var = tk.StringVar(value="—")
        self.file_var = tk.StringVar(value="—")
        self.branch_var = tk.StringVar(value="—")
        self.commit_var = tk.StringVar(value="—")
        self.status_var = tk.StringVar(value="disarmed")
        self.message_var = tk.StringVar(value="Disarmed")
        self.auto_commit_var = tk.BooleanVar(value=False)
        self.armed_var = tk.BooleanVar(value=False)

        self._build(scrolledtext)
        self.state.add_listener(self._on_state)
        self._start_esc_listener()
        self._poll_confirm()
        self._refresh_git()

    def _build(self, scrolledtext):
        tk = self.tk
        ttk = self.ttk
        frm = ttk.Frame(self.root, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)

        proj = ttk.Frame(frm)
        proj.pack(fill=tk.X)
        ttk.Label(proj, text="Project root:").pack(side=tk.LEFT)
        ttk.Entry(proj, textvariable=self.project_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=6
        )
        ttk.Button(proj, text="Browse…", command=self._browse).pack(side=tk.LEFT)

        grid = ttk.Frame(frm)
        grid.pack(fill=tk.X, pady=(12, 0))
        rows = [
            ("Task", self.task_var),
            ("Action", self.action_var),
            ("File", self.file_var),
            ("Branch", self.branch_var),
            ("Last commit", self.commit_var),
            ("Automation", self.status_var),
            ("Message", self.message_var),
        ]
        for i, (label, var) in enumerate(rows):
            ttk.Label(grid, text=f"{label}:").grid(row=i, column=0, sticky="w", pady=2)
            ttk.Label(grid, textvariable=var).grid(row=i, column=1, sticky="w", padx=8)

        self.progress = ttk.Progressbar(frm, mode="determinate")
        self.progress.pack(fill=tk.X, pady=(10, 0))

        ctrl = ttk.Frame(frm)
        ctrl.pack(fill=tk.X, pady=(12, 0))

        self.arm_btn = ttk.Button(ctrl, text="Arm", command=self._toggle_arm)
        self.arm_btn.pack(side=tk.LEFT)
        ttk.Button(ctrl, text="Pause", command=self._pause).pack(side=tk.LEFT, padx=4)
        ttk.Button(ctrl, text="Resume", command=self._resume).pack(side=tk.LEFT, padx=4)
        ttk.Button(ctrl, text="Stop", style="Danger.TButton", command=self._stop).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(ctrl, text="Commit Now", command=self._commit_now).pack(side=tk.LEFT, padx=8)
        ttk.Checkbutton(
            ctrl,
            text="Auto Commit",
            variable=self.auto_commit_var,
            command=self._toggle_auto_commit,
        ).pack(side=tk.LEFT, padx=4)

        self.confirm_frame = ttk.Frame(frm)
        self.confirm_label = ttk.Label(self.confirm_frame, text="")
        self.confirm_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(
            self.confirm_frame,
            text="Allow",
            style="Ok.TButton",
            command=lambda: self._confirm(True),
        ).pack(side=tk.LEFT, padx=4)
        ttk.Button(
            self.confirm_frame,
            text="Deny",
            style="Danger.TButton",
            command=lambda: self._confirm(False),
        ).pack(side=tk.LEFT)

        ttk.Label(frm, text="Execution log").pack(anchor="w", pady=(12, 2))
        self.log = scrolledtext.ScrolledText(
            frm,
            height=12,
            wrap=tk.WORD,
            font=("Menlo", 10),
            bg=DARK_FIELD,
            fg=DARK_FG,
            insertbackground=DARK_FG,
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=DARK_BORDER,
        )
        self.log.pack(fill=tk.BOTH, expand=True)
        self.log.configure(state=tk.DISABLED)

        tip = ttk.Label(
            frm,
            text="Esc = stop. Keep this GUI open (API :8765). Cursor MCP forwards actions here.",
            foreground="#888",
        )
        tip.pack(anchor="w", pady=(6, 0))

    def _browse(self):
        path = self.filedialog.askdirectory()
        if path:
            self.project_var.set(path)
            self.state.project_root = path
            self._refresh_git()

    def _toggle_arm(self):
        if self.state.armed:
            self.executor.execute({"type": "disarm"})
            self.arm_btn.configure(text="Arm")
        else:
            root = self.project_var.get().strip()
            if root:
                self.state.project_root = root
            self.executor.execute({"type": "arm", "project_root": root or None})
            self.arm_btn.configure(text="Disarm")
            self._refresh_git()
            self._append_log("Armed — Cursor may call human-typer MCP tools")

    def _pause(self):
        self.executor.execute({"type": "pause"})

    def _resume(self):
        self.executor.execute({"type": "resume"})

    def _stop(self):
        self.executor.execute({"type": "emergency_stop"})
        self._append_log("EMERGENCY STOP")

    def _toggle_auto_commit(self):
        self.state.set_auto_commit(self.auto_commit_var.get())

    def _commit_now(self):
        if not self.state.project_root:
            self.messagebox.showwarning("Commit", "Set project root first.")
            return

        def work():
            result = self.git.commit_now()
            self.root.after(0, lambda: self._commit_done(result))

        threading.Thread(target=work, daemon=True).start()

    def _commit_done(self, result: dict):
        if result.get("ok"):
            self._append_log(f"Commit: {result.get('commit')} — {result.get('message')}")
            self._refresh_git()
        else:
            self._append_log(f"Commit failed: {result.get('error')}")
            self.messagebox.showerror("Commit", result.get("error", "failed"))

    def _confirm(self, approved: bool):
        self.state.resolve_command_confirm(approved)
        self.confirm_frame.pack_forget()
        self._confirm_shown_for = ""

    def _poll_confirm(self):
        pending = self.state.pending_command
        if pending and pending != self._confirm_shown_for:
            self._confirm_shown_for = pending
            self.confirm_label.configure(text=f"Allow run_command?\n{pending}")
            self.confirm_frame.pack(fill=self.tk.X, pady=(8, 0))
        elif not pending and self._confirm_shown_for:
            self.confirm_frame.pack_forget()
            self._confirm_shown_for = ""
        self.root.after(200, self._poll_confirm)

    def _on_state(self):
        self.root.after(0, self._apply_snapshot)

    def _apply_snapshot(self):
        snap = self.state.snapshot()
        self.task_var.set(snap.current_task or "(set task in Cursor chat)")
        self.action_var.set(snap.current_action or "—")
        self.file_var.set(snap.current_file or "—")
        self.branch_var.set(snap.branch or "—")
        self.commit_var.set(snap.last_commit or "—")
        self.status_var.set(snap.status)
        self.message_var.set(snap.message)
        self.progress["value"] = snap.progress
        self.armed_var.set(snap.armed)
        self.arm_btn.configure(text="Disarm" if snap.armed else "Arm")
        if snap.last_actions:
            last = snap.last_actions[-1]
            line = f"{last['action_type']}: {last['detail']}" + (
                f" ERR={last['error']}" if not last["ok"] else ""
            )
            self._append_log_unique(line)

    def _append_log_unique(self, line: str):
        self.log.configure(state=self.tk.NORMAL)
        content = self.log.get("1.0", self.tk.END)
        if line not in content.splitlines()[-5:]:
            self.log.insert(self.tk.END, line + "\n")
            self.log.see(self.tk.END)
        self.log.configure(state=self.tk.DISABLED)

    def _append_log(self, line: str):
        self.log.configure(state=self.tk.NORMAL)
        self.log.insert(self.tk.END, line + "\n")
        self.log.see(self.tk.END)
        self.log.configure(state=self.tk.DISABLED)

    def _refresh_git(self):
        root = self.project_var.get().strip()
        if root:
            self.state.project_root = root
        info = self.git.summary()
        if info.get("branch"):
            self.branch_var.set(info["branch"])
            self.commit_var.set(info.get("last_commit") or "—")
            self.state.set_status(branch=info["branch"], last_commit=info.get("last_commit", ""))

    def _start_esc_listener(self):
        self._esc_listener = EscWatcher(user_stop_handler(self.state))
        self._esc_listener.start()

    def on_close(self):
        logging.getLogger("gui").info("window closed by user")
        if self._esc_listener:
            self._esc_listener.stop()
        if self.api:
            self.api.stop()
        self.executor.close()
        self.root.destroy()


def main(project: str = "", auto_arm: bool = False):
    logs.setup("gui")
    tk, filedialog, messagebox, scrolledtext, ttk = _require_tk()
    if project:
        STATE.project_root = project
    EXECUTOR._ensure_backends()
    root = tk.Tk()
    app = OperatorApp(root, tk, filedialog, messagebox, scrolledtext, ttk)
    if auto_arm and not STATE.armed:
        app._toggle_arm()
    if project:
        x = root.winfo_screenwidth() - 640 - 24
        y = root.winfo_screenheight() - 560 - 96
        root.geometry(f"640x560+{max(x, 0)}+{max(y, 0)}")
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
