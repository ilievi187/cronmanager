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


class CronManagerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Cron Manager")
        self.geometry("900x600")
        self.minsize(760, 480)
        self.configure(bg="#f0f0f0")

        self.jobs: list[cm.Job] = []
        self._build_ui()
        self.refresh()

    # ---- UI construction -------------------------------------------------
    def _build_ui(self) -> None:
        # Toolbar
        bar = ttk.Frame(self, padding=4)
        bar.pack(fill=tk.X)
        ttk.Button(bar, text="Refresh", command=self.refresh).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="New Job", command=self._new_dialog).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="Edit", command=self._edit_dialog).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="Run Now", command=self.run_now).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="Pause/Resume", command=self.toggle_pause).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="History", command=self.show_history).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="Remove", command=self.remove_selected).pack(side=tk.LEFT, padx=2)

        # Job list
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.tree = ttk.Treeview(
            tree_frame,
            columns=("id", "name", "status", "schedule", "next"),
            show="headings",
        )
        self.tree.heading("id", text="ID")
        self.tree.heading("name", text="Name")
        self.tree.heading("status", text="Status")
        self.tree.heading("schedule", text="Schedule")
        self.tree.heading("next", text="Next Run")
        self.tree.column("id", width=110, anchor=tk.W)
        self.tree.column("name", width=160, anchor=tk.W)
        self.tree.column("status", width=70, anchor=tk.W)
        self.tree.column("schedule", width=140, anchor=tk.W)
        self.tree.column("next", width=190, anchor=tk.W)
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        tree_frame.pack_propagate(False)
        # Detail panel
        detail = ttk.LabelFrame(self, text="Job details", padding=8)
        detail.pack(fill=tk.X, padx=4, pady=(0, 4))
        self.detail_var = tk.StringVar(value="Select a job to edit.")
        ttk.Label(detail, textvariable=self.detail_var).pack(anchor=tk.W)

        # Status bar
        self.status = ttk.Label(self, text="", anchor=tk.W, foreground="#333333")
        self.status.pack(fill=tk.X, side=tk.BOTTOM)

        self.tree.bind("<Double-Button-1>", lambda e: self._edit_dialog())
        self.tree.pack(fill=tk.BOTH, expand=True)

    # ---- actions ---------------------------------------------------------
    def refresh(self) -> None:
        self.jobs = cm.list_jobs(include_all=True)
        self.tree.delete(*self.tree.get_children())
        for j in self.jobs:
            self.tree.insert(
                "",
                tk.END,
                iid=j.id,
                values=(j.id[:8], j.name or "-", j.status, j.schedule or "-", j.next_run or "-"),
            )
        self.status.configure(text=f"{len(self.jobs)} job(s) loaded")

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
        win.geometry("460x360")
        win.modal = False

        if job and not empty_job:
            name_v = tk.StringVar(job.name or "")
            sched_v = tk.StringVar(job.schedule)
            repeat_v = tk.StringVar(job.replace("0/", "").replace("/", "") if "0/" in job.repeat else "")
            paused_v = tk.BooleanVar(job.status == "paused")
        else:
            name_v = tk.StringVar("")
            sched_v = tk.StringVar("")
            repeat_v = tk.StringVar("")
            paused_v = tk.BooleanVar(False)

        form = ttk.Frame(win, padding=10)
        form.pack(fill=tk.BOTH, expand=True)

        ttk.Label(form, text="Name (optional):").grid(row=0, column=0, sticky=tk.W, pady=3)
        ttk.Entry(form, textvariable=name_v).grid(row=0, column=1, sticky=tk.EW, pady=3)

        ttk.Label(form, text="Schedule (e.g. 30m / every 2h / 0 9 * * *):").grid(
            row=1, column=0, sticky=tk.W, pady=3
        )
        ttk.Entry(form, textvariable=sched_v).grid(row=1, column=1, sticky=tk.EW, pady=3)

        ttk.Label(form, text="Repeat count (optional):").grid(row=2, column=0, sticky=tk.W, pady=3)
        ttk.Entry(form, textvariable=repeat_v).grid(row=2, column=1, sticky=tk.EW, pady=3)

        ttk.Label(form, text="Prompt / task:").grid(row=3, column=0, sticky=tk.NW, pady=3)
        txt = scrolledtext.ScrolledText(form, width=40, height=6)
        txt.grid(row=3, column=1, sticky=tk.NSEW, pady=3)
        if job and not empty_job and job.raw:
            txt.insert(tk.END, " ")

        ttk.Checkbutton(form, text="Paused", variable=paused_v).grid(row=4, column=0, sticky=tk.W, pady=3)

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
                    cm.create_job(schedule=schedule, prompt="", **data)
                else:
                    cm.edit_job(job.id, **data)
                messagebox.showinfo("OK", "Saved.")
                win.destroy()
                self.refresh()
            except RuntimeError as e:
                messagebox.showerror("Error", str(e))

        btns = ttk.Frame(win)
        btns.pack(fill=tk.X, padx=10, pady=(6, 10))
        ttk.Button(btns, text="Save", command=ok).pack(side=tk.LEFT)
        ttk.Button(btns, text="Cancel", command=win.destroy).pack(side=tk.RIGHT)

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
            if j.status == "paused":
                out = cm.resume_job(j.id)
            else:
                out = cm.pause_job(j.id)
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
