#!/usr/bin/env python3
"""
Cron Manager - a simple GUI to browse, create, edit and delete Hermes cron jobs.

Run:  python3 gui.py

Features:
  - List all cron jobs (name, status, schedule, next run)
  - Create a new job (schedule + prompt + optional name/repeat)
  - Edit an existing job (name / schedule / pause-resume)
  - Run now / Pause / Resume / Remove actions
  - View run history
  - Refresh on demand

Uses the `cronmanager` library (hermes cron CLI wrapper) from the same folder.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

import cronmanager as cm

# ---- theme / accent colours -------------------------------------------------
ACCENT = "#2d6cdf"        # button / header accent
ACCENT_TEXT = "#ffffff"
BG = "#f4f5f7"
HEADER_BG = "#1f2a44"
ROW_ALT = "#ffffff"
STATUS_COLORS = {
    "active": "#1b7e3b",
    "paused": "#c8860b",
    "completed": "#6b7280",
    "running": "#2d6cdf",
    "failed": "#b42319",
    "missed": "#933646",
    "cancelled": "#6b7280",
}


class CronManagerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Cron Manager")
        self.geometry("920x620")
        self.minsize(780, 500)
        self.configure(bg=BG)
        self._configure_theme()

        self.jobs: list[cm.Job] = []
        self._build_ui()
        self.refresh()

    # ---- theming -----------------------------------------------------------
    def _configure_theme(self) -> None:
        style = ttk.Style(self)
        # Pick a native theme if available, else rely on defaults.
        available = set(style.themes()) if hasattr(style, "themes") else set()
        for candidate in ("arc", "breeze", "clam", "highwind", "default"):
            if candidate in available:
                style.theme_use(candidate)
                break

    # ---- UI construction ---------------------------------------------------
    def _build_ui(self) -> None:
        # Title header
        header = ttk.Frame(self, height=46)
        header.pack(fill=tk.X, side=tk.TOP)
        header.propagate(False)
        ttk.Label(
            header,
            text="  🗓  Cron Manager",
            foreground=ACCENT_TEXT,
            font=("Segoe UI", 13, "bold"),
            anchor="w",
        ).pack(fill=tk.BOTH, side=tk.LEFT)

        # Toolbar
        bar = ttk.Frame(self, padding=6)
        bar.pack(fill=tk.X, side=tk.TOP)
        self._btn(bar, "Refresh", self.refresh)
        self._btn(bar, "New Job", self._new_dialog)
        self._btn(bar, "Edit", self._edit_dialog)
        self._btn(bar, "Run Now", self.run_now)
        self._btn(bar, "Pause/Resume", self.toggle_pause)
        self._btn(bar, "History", self.show_history)
        self._btn(bar, "Remove", self.remove_selected)

        # Job list
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill=tk.BOTH, expand=True, side=tk.TOP)
        self.tree = ttk.Treeview(
            tree_frame,
            columns=("id", "name", "status", "schedule", "next"),
            show="headings",
            height=18,
        )
        for col, text in zip(
            self.tree["columns"], ("ID", "Name", "Status", "Schedule", "Next Run")
        ):
            self.tree.heading(col, text=text)
        self.tree.column("id", width=110, anchor=tk.W, minwidth=90)
        self.tree.column("name", width=200, anchor=tk.W, minwidth=120)
        self.tree.column("status", width=90, anchor=tk.W, minwidth=70)
        self.tree.column("schedule", width=150, anchor=tk.W, minwidth=110)
        self.tree.column("next", width=200, anchor=tk.W, minwidth=160)
        self.tree.bind("<Map>", lambda e: self._bind_tags())
        self.tree.bind("<Unmap>", lambda e: self._unbind_tags())

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        tree_frame.pack_propagate(False)
        tree_frame.pack(fill=tk.BOTH, expand=True, side=tk.TOP)

        # Detail panel
        detail = ttk.LabelFrame(self, text="Job details", padding=8)
        detail.pack(fill=tk.X, side=tk.BOTTOM)
        self.detail_var = tk.StringVar(value="Select a job to edit.")
        ttk.Label(detail, textvariable=self.detail_var, foreground="#555555").pack(anchor=tk.W)

        # Status bar
        self.status = ttk.Label(self, text="", anchor=tk.W, foreground="#555555")
        self.status.pack(fill=tk.X, side=tk.BOTTOM)

        self.tree.bind("<Double-Button-1>", lambda e: self._edit_dialog())

    def _bind_tags(self) -> None:
        self.tree.tag_configure("active", foreground=STATUS_COLORS.get("active"))
        self.tree.tag_configure("paused", foreground=STATUS_COLORS.get("paused"))
        self.tree.tag_configure("running", foreground=STATUS_COLORS.get("running"))
        self.tree.tag_configure("completed", foreground=STATUS_COLORS.get("completed"))
        self.tree.tag_configure("failed", foreground=STATUS_COLORS.get("failed"))

    def _unbind_tags(self) -> None:
        pass

    def _btn(self, parent: ttk.Frame, text: str, cmd) -> None:
        ttk.Button(parent, text=text, command=cmd, width=12).pack(side=tk.LEFT, padx=3, pady=2)

    # ---- actions -----------------------------------------------------------
    def refresh(self) -> None:
        self.jobs = cm.list_jobs(include_all=True)
        self.tree.delete(*self.tree.get_children())
        for j in self.jobs:
            tags = [j.status] if j.status in STATUS_COLORS else []
            self.tree.insert(
                "",
                tk.END,
                iid=j.id,
                values=(j.id[:8], j.name or "-", j.status, j.schedule or "-", j.next_run or "-"),
                tags=tags,
            )
        self.status.configure(text=f"{len(self.jobs)} job(s) loaded")
        self._refresh_detail()

    def _refresh_detail(self) -> None:
        sel = self.tree.selection()
        j = self._selected() if sel else None
        if j:
            lines = [
                f"Name:     {j.name or '-'}",
                f"Status:   {j.status}",
                f"Schedule: {j.schedule}",
                f"Repeat:   {j.repeat}",
                f"Next:     {j.next_run}",
                f"Deliver:  {j.deliver}",
            ]
            self.detail_var.set("\n".join(lines))
        else:
            self.detail_var.set("Select a job to edit.")

    def _selected(self) -> cm.Job | None:
        sel = self.tree.selection()
        if not sel:
            return None
        jid = sel[0]
        for j in self.jobs:
            if j.id == jid:
                return j
        return None

    def _new_dialog(self) -> None:
        self._form("Create Job", empty_job=True)

    def _edit_dialog(self) -> None:
        j = self._selected()
        if not j:
            messagebox.showinfo("Edit", "Select a job first.")
            return
        self._form("Edit Job", job=j)

    def _form(self, title: str, job: cm.Job | None = None, empty_job: bool = False) -> None:
        win = tk.Toplevel(self)
        win.title(title)
        win.geometry("480x380")
        win.translucent = False
        win.modelodal = True

        if job and not empty_job:
            name_v = tk.StringVar(value=job.name or "")
            sched_v = tk.StringVar(value=job.schedule)
            repeat_v = tk.StringVar(value=self._parse_repeat(job.repeat))
            paused_v = tk.BooleanVar(value=(job.status == "paused"))
            prompt_v = tk.StringVar(value=self._extract_prompt(job.raw))
        else:
            name_v = tk.StringVar(value="")
            sched_v = tk.StringVar(value="")
            repeat_v = tk.StringVar(value="")
            paused_v = tk.BooleanVar(value=False)
            prompt_v = tk.StringVar(value="")

        ttk.Label(win, text=title, foreground=ACCENT, font=("Segoe UI", 11, "bold")).grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=(8, 6)
        )

        ttk.Label(win, text="Name (optional):").grid(row=1, column=0, sticky=tk.W, pady=3)
        ttk.Entry(win, textvariable=name_v).grid(row=1, column=1, sticky=tk.EW, pady=3)

        ttk.Label(win, text="Schedule (e.g. 30m / every 2h / 0 9 * * *):").grid(
            row=2, column=0, sticky=tk.W, pady=3
        )
        ttk.Entry(win, textvariable=sched_v).grid(row=2, column=1, sticky=tk.EW, pady=3)

        ttk.Label(win, text="Repeat count (optional):").grid(row=3, column=0, sticky=tk.W, pady=3)
        ttk.Entry(win, textvariable=repeat_v).grid(row=3, column=1, sticky=tk.EW, pady=3)

        ttk.Label(win, text="Prompt / task:").grid(row=4, column=0, sticky=tk.NW, pady=3)
        txt = scrolledtext.ScrolledText(win, width=36, height=5)
        txt.grid(row=4, column=1, sticky=tk.NSEW, pady=3)
        txt.insert(tk.END, prompt_v.get())

        ttk.Checkbutton(win, text="Paused", variable=paused_v).grid(row=5, column=0, sticky=tk.W, pady=3)

        def ok() -> None:
            schedule = sched_v.get().strip()
            if not schedule:
                messagebox.showwarning("Input", "Schedule is required.")
                return
            data = {
                "name": name_v.get().strip(),
                "schedule": schedule,
                "repeat": int(repeat_v.get()) if repeat_v.get().strip() else None,
                "paused": paused_v.get(),
            }
            try:
                if empty_job:
                    prompt = txt.get("1.0", tk.END).strip()
                    cm.create_job(schedule=schedule, prompt=prompt, **data)
                else:
                    cm.edit_job(job.id, **data)
                messagebox.showinfo("OK", "Saved.")
                win.destroy()
                self.refresh()
            except RuntimeError as e:
                messagebox.showerror("Error", str(e))

        btns = ttk.Frame(win)
        btns.grid(row=6, column=0, columnspan=2, sticky=tk.EW, pady=(8, 4))
        ttk.Button(btns, text="Cancel", width=10, command=win.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btns, text="Save", width=10, command=ok).pack(side=tk.RIGHT)

        win.grid_columnconfigure(1, weight=1)
        win.grid_rowconfigure(4, weight=1)
        win.grab_set()

    @staticmethod
    def _parse_repeat(repeat: str) -> str:
        if not repeat:
            return ""
        if "0/" in repeat:
            return repeat.split("0/", 1)[1]
        return ""

    @staticmethod
    def _extract_prompt(raw: str) -> str:
        if not raw:
            return ""
        for line in raw.splitlines():
            if "Prompt" in line or "prompt" in line:
                return line
        return ""

    def run_now(self) -> None:
        j = self._selected()
        if not j:
            messagebox.showinfo("Run", "Select a job first.")
            return
        try:
            out = cm.run_job(j.id)
            messagebox.showinfo("Run", out.strip())
            self.refresh()
        except RuntimeError as e:
            messagebox.showerror("Error", str(e))

    def toggle_pause(self) -> None:
        j = self._selected()
        if not j:
            messagebox.showinfo("Pause", "Select a job first.")
            return
        try:
            out = cm.resume_job(j.id) if j.status == "paused" else cm.pause_job(j.id)
            messagebox.showinfo("Status", out.strip())
            self.refresh()
        except RuntimeError as e:
            messagebox.showerror("Error", str(e))

    def remove_selected(self) -> None:
        j = self._selected()
        if not j:
            messagebox.showinfo("Remove", "Select a job first.")
            return
        if not messagebox.askyesno("Confirm", f"Remove job {j.id}?"):
            return
        try:
            out = cm.remove_job(j.id)
            messagebox.showinfo("Removed", out.strip())
            self.refresh()
        except RuntimeError as e:
            messagebox.showerror("Error", str(e))

    def show_history(self) -> None:
        j = self._selected()
        if not j:
            messagebox.showinfo("History", "Select a job first.")
            return
        try:
            out = cm.history(j.id)
            box = tk.Toplevel(self)
            box.title(f"History - {j.name or j.id}")
            t = scrolledtext.ScrolledText(box, width=70, height=20)
            t.pack(fill=tk.BOTH, expand=True)
            t.insert(tk.END, out)
        except RuntimeError as e:
            messagebox.showerror("Error", str(e))


def main() -> None:
    CronManagerApp().mainloop()


if __name__ == "__main__":
    main()
