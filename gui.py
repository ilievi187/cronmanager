#!/usr/bin/env python3
"""
Cron Manager - a simple GUI to browse, create, edit and delete Hermes cron jobs.

Run:  python3 gui.py

Features:
  - List all cron jobs (name, status, schedule, next run)
  - Create a new job (friendly form: how often, what to do)
  - Edit an existing job (name / schedule / pause-resume)
  - Run now / Pause / Resume / Remove actions
  - View run history
  - Refresh on demand
  - Auto-adapts to dark/light system theme

Uses the `cronmanager` library (hermes cron CLI wrapper) from the same folder.
"""

from __future__ import annotations

import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

import cronmanager as cm


# ---- theme detection --------------------------------------------------------
def detect_theme() -> str:
    """Return 'dark' or 'light' based on the desktop theme settings."""
    try:
        out = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0:
            v = out.stdout.strip().strip("'")
            if "dark" in v:
                return "dark"
            if "light" in v:
                return "light"
    except (FileNotFoundError, subprocess.SubprocessError):
        pass

    # Fallback: read GTK settings for dark/light theme names.
    try:
        cfg = subprocess.run(
            ["bash", "-c",
             "cat ~/.config/gtk-3.0/settings.ini 2>/dev/null; "
             "cat ~/.config/gtk-4.0/settings.ini 2>/dev/null"],
            capture_output=True, text=True, timeout=5,
        )
        txt = (cfg.stdout + cfg.stderr).lower()
        if "dark" in txt or "black" in txt or "adapta" in txt:
            return "dark"
    except subprocess.SubprocessError:
        pass

    return "light"


THEME = detect_theme()
is_dark = THEME == "dark"

# ---- colours per theme ------------------------------------------------------
if is_dark:
    BG = "#242424"
    CARD = "#2f2f2f"
    HEADER_BG = "#1c1c1c"
    TEXT = "#f0f0f0"
    SUBTEXT = "#b0b0b0"
    BORDER = "#3a3a3a"
else:
    BG = "#f5f6f8"
    CARD = "#ffffff"
    HEADER_BG = "#2d6cdf"
    TEXT = "#1a1a1a"
    SUBTEXT = "#555555"
    BORDER = "#d0d0d0"

ACCENT_TEXT = "#ffffff"
STATUS_COLORS = {
    "active": "#3fb25f",
    "paused": "#e0a400",
    "running": "#4a86e8",
    "completed": "#808080",
    "failed": "#d43b2f",
    "missed": "#a05195",
    "cancelled": "#808080",
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
            background=HEADER_BG,
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
        ttk.Label(detail, textvariable=self.detail_var, foreground=SUBTEXT).pack(anchor=tk.W)

        # Status bar
        self.status = ttk.Label(self, text="", anchor=tk.W, foreground=SUBTEXT)
        self.status.pack(fill=tk.X, side=tk.BOTTOM)

        self.tree.bind("<Double-Button-1>", lambda e: self._edit_dialog())

    def _bind_tags(self) -> None:
        for st, col in STATUS_COLORS.items():
            self.tree.tag_configure(st, foreground=col)

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
        win.geometry("520x440")
        win.grab_set()
        win.configure(bg=BG)

        # --- shared variables ---
        name_v = tk.StringVar()
        unit_v = tk.StringVar(value="minutes")
        amount_v = tk.StringVar(value="30")
        every_v = tk.StringVar(value="every 30 minutes")
        cron_v = tk.StringVar(value="")
        cron_manual = tk.StringVar(value="")
        paused_v = tk.BooleanVar(value=False)
        prompt_v = tk.StringVar()

        if job and not empty_job:
            name_v.set(job.name or "")
            every_v.set(job.schedule or "")
            prompt_v.set(self._extract_prompt(job.raw))
            cron_v.set("")
            cron_manual.set("")

        def rebuild_hint() -> None:
            amt = amount_v.get().strip() or "30"
            u = unit_v.get()
            every_v.set(f"every {amt} {u}")
            cron_v.set(self._cron_from_form(amt, u))

        # Header
        ttk.Label(win, text=title, foreground=ACCENT if not is_dark else "#93c4ff",
                  background=BG, font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=(10, 8))

        # Friendly form
        ttk.Label(win, text="What do you want it to do?", anchor=tk.W).grid(
            row=1, column=0, sticky=tk.W, pady=(2, 2))
        ttk.Entry(win, textvariable=name_v).grid(
            row=1, column=1, sticky=tk.EW, pady=2, padx=(0, 6))
        ttk.Label(win, text="(optional name)", foreground=SUBTEXT).grid(
            row=2, column=1, sticky=tk.W)

        ttk.Label(win, text="How often?", anchor=tk.W).grid(
            row=3, column=0, sticky=tk.W, pady=(8, 2))

        frm = ttk.Frame(win)
        frm.grid(row=3, column=1, sticky=tk.EW, pady=2)
        ttk.Label(win, text="Repeat every").grid(row=3, column=0, sticky=tk.W)
        amt_entry = ttk.Entry(frm, textvariable=amount_v, width=5)
        amt_entry.grid(row=0, column=0, padx=(0, 6))
        unit_dd = ttk.Combobox(frm, values=["minutes", "hours", "days", "weeks"],
                                textvariable=unit_v, width=8, state="readonly")
        unit_dd.grid(row=0, column=1)
        unit_dd.bind("<<ComboboxChanged>>", lambda e: rebuild_hint())

        # Preview of the schedule string
        ttk.Label(win, text="Schedule preview:", anchor=tk.W).grid(
            row=4, column=0, sticky=tk.W, pady=(6, 2))
        ttk.Entry(win, textvariable=every_v, state="readonly").grid(
            row=4, column=1, sticky=tk.EW, pady=2)

        # Optional custom cron
        ttk.Label(win, text="Custom cron (optional, e.g. '0 9 * * *'):", anchor=tk.W).grid(
            row=5, column=0, sticky=tk.W, pady=(6, 2))
        ttk.Entry(win, textvariable=cron_manual).grid(
            row=5, column=1, sticky=tk.EW, pady=2)

        # Prompt / task
        ttk.Label(win, text="Task / prompt:", anchor=tk.W).grid(
            row=6, column=0, sticky=tk.W, pady=(6, 2))
        txt = scrolledtext.ScrolledText(win, width=36, height=4)
        txt.grid(row=6, column=1, sticky=tk.NSEW, pady=2)
        txt.insert(tk.END, prompt_v.get())

        # Paused checkbox
        ttk.Checkbutton(win, text="Create paused", variable=paused_v).grid(
            row=7, column=0, columnspan=2, sticky=tk.W, pady=(6, 2))

        def build_schedule() -> str:
            # Prefer manual cron if entered
            if cron_manual.get().strip():
                return cron_manual.get().strip()
            amt = amount_v.get().strip() or "30"
            u = unit_v.get()
            return f"every {amt} {u}"

        def ok() -> None:
            schedule = build_schedule()
            if not schedule:
                messagebox.showwarning("Input", "Please set how often.")
                return
            data = {
                "name": name_v.get().strip(),
                "schedule": schedule,
                "repeat": None,
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
        btns.grid(row=8, column=0, columnspan=2, sticky=tk.EW, pady=(8, 6))
        ttk.Button(btns, text="Cancel", width=10, command=win.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btns, text="Save", width=10, command=ok).pack(side=tk.RIGHT)

        win.grid_columnconfigure(1, weight=1)
        win.grid_rowconfigure(6, weight=1)
        win.lift()
        win.focus_set()
        win.attributes('-topmost', True)

    @staticmethod
    def _cron_from_form(amt: str, unit: str) -> str:
        """Very small helper to preview a cron-ish string (informational)."""
        if unit == "minutes":
            return f"*/{int(amt) if amt.isdigit() else amt} * * * *"
        if unit == "hours":
            h = int(amt) if amt.isdigit() else amt
            return f"0 */{h if isinstance(h, int) else h} * * *"
        if unit == "days":
            return f"0 0 */{amt if amt.isdigit() else amt} * *"
        return f"every {amt} {unit}"

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
