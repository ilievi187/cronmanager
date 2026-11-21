#!/usr/bin/env python3
"""
Cron Manager — sleek, premium, native Linux scheduled task manager (Qt 6 / PySide6).
Controls real Linux scheduled tasks (systemd --user timers or crontab) with zero
third-party agent dependencies and live Omarchy theme synchronization.
"""

from __future__ import annotations

import sys
from typing import Callable, Optional

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

import cronmanager as cm
from theme import ThemePalette, ThemeWatcher, build_stylesheet


class GlowButton(QPushButton):
    """PushButton with smooth animated accent glow on hover and pointer cursor."""

    def __init__(self, text: str = "", glow_hex: str = "#7376b7", max_blur: float = 20.0, parent=None) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._max_blur = max_blur
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setOffset(0, 0)
        self._shadow.setBlurRadius(0.0)
        self._set_glow_color(glow_hex)
        self.setGraphicsEffect(self._shadow)

        self._anim = QPropertyAnimation(self._shadow, b"blurRadius", self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _set_glow_color(self, hex_color: str) -> None:
        c = QColor(hex_color)
        c.setAlpha(155)
        self._shadow.setColor(c)

    def update_glow_color(self, hex_color: str) -> None:
        self._set_glow_color(hex_color)

    def enterEvent(self, event) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._shadow.blurRadius())
        self._anim.setEndValue(self._max_blur)
        self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._shadow.blurRadius())
        self._anim.setEndValue(0.0)
        self._anim.start()
        super().leaveEvent(event)


class HoverCard(QFrame):
    """Elevated card with smooth animated accent glow on hover."""

    def __init__(self, glow_hex: str = "#7376b7", parent=None) -> None:
        super().__init__(parent)
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setOffset(0, 3)
        self._shadow.setBlurRadius(10.0)
        c = QColor(glow_hex)
        c.setAlpha(35)
        self._shadow.setColor(c)
        self.setGraphicsEffect(self._shadow)
        self._glow_hex = glow_hex

        self._anim = QPropertyAnimation(self._shadow, b"blurRadius", self)
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def enterEvent(self, event) -> None:
        c = QColor(self._glow_hex)
        c.setAlpha(115)
        self._shadow.setColor(c)
        self._anim.stop()
        self._anim.setStartValue(self._shadow.blurRadius())
        self._anim.setEndValue(24.0)
        self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        c = QColor(self._glow_hex)
        c.setAlpha(35)
        self._shadow.setColor(c)
        self._anim.stop()
        self._anim.setStartValue(self._shadow.blurRadius())
        self._anim.setEndValue(10.0)
        self._anim.start()
        super().leaveEvent(event)


class WorkerThread(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable, *args, **kwargs) -> None:
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self) -> None:
        try:
            self.succeeded.emit(self._fn(*self._args, **self._kwargs))
        except Exception as exc:
            self.failed.emit(str(exc))


class JobFormDialog(QDialog):
    """Human-friendly modal to create or edit a native Linux scheduled task."""

    PRESETS = [
        ("Every 5 min", "*/5 * * * *"),
        ("Every 15 min", "*/15 * * * *"),
        ("Every hour", "0 * * * *"),
        ("Daily 09:00", "0 9 * * *"),
        ("Mondays 09:00", "0 9 * * 1"),
        ("At Startup", "@reboot"),
    ]

    UNIT_MAP = [
        ("minutes", "m"),
        ("hours", "h"),
        ("days", "d"),
    ]

    EXAMPLES = [
        ("Desktop Notification", 'notify-send "Cron Manager" "Time for a quick break!"'),
        ("Backup Documents", 'tar -czf ~/Backups/docs-$(date +%F).tar.gz ~/Documents'),
        ("Clean /tmp logs", 'find /tmp -maxdepth 1 -name "*.log" -mtime +7 -delete'),
    ]

    def __init__(
        self,
        parent: QWidget,
        palette: ThemePalette,
        job: Optional[cm.Job] = None,
    ) -> None:
        super().__init__(parent)
        self.job = job
        self.palette_data = palette
        self.result_payload: Optional[dict] = None

        is_edit = job is not None
        self.setWindowTitle("Edit Linux Task" if is_edit else "New Linux Task")
        self.setMinimumWidth(560)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(14)

        title = QLabel("Edit Scheduled Task" if is_edit else "Create a Scheduled Linux Task")
        title.setObjectName("TitleLabel")
        subtitle = QLabel("Schedule any shell command, script, or backup directly on your Linux system.")
        subtitle.setObjectName("SubtitleLabel")
        root.addWidget(title)
        root.addWidget(subtitle)

        # Task name
        root.addWidget(self._section_label("Task name"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g., Daily Backup, Clean Downloads, Break Reminder")
        if job:
            self.name_input.setText(job.name or "")
        root.addWidget(self.name_input)

        # Quick schedule presets
        root.addWidget(self._section_label("When should it run?"))
        preset_row = QHBoxLayout()
        preset_row.setSpacing(6)
        self._preset_buttons: list[QPushButton] = []
        for label, sched in self.PRESETS:
            btn = GlowButton(label, glow_hex=palette.accent, max_blur=14.0)
            btn.setObjectName("ChipButton")
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, s=sched, b=btn: self._select_preset(s, b))
            preset_row.addWidget(btn)
            self._preset_buttons.append(btn)
        preset_row.addStretch()
        root.addLayout(preset_row)

        # Friendly interval builder
        interval_row = QHBoxLayout()
        interval_row.setSpacing(8)
        interval_row.addWidget(QLabel("Or repeat every"))
        self.amount_spin = QSpinBox()
        self.amount_spin.setRange(1, 999)
        self.amount_spin.setValue(30)
        self.amount_spin.setFixedWidth(78)
        self.amount_spin.valueChanged.connect(self._sync_from_interval)
        interval_row.addWidget(self.amount_spin)

        self.unit_combo = QComboBox()
        for label, _ in self.UNIT_MAP:
            self.unit_combo.addItem(label)
        self.unit_combo.currentIndexChanged.connect(self._sync_from_interval)
        interval_row.addWidget(self.unit_combo)
        interval_row.addStretch()
        root.addLayout(interval_row)

        # Cron schedule expression + human preview
        root.addWidget(self._section_label("Cron schedule"))
        self.schedule_input = QLineEdit()
        self.schedule_input.setPlaceholderText("*/15 * * * *, 0 9 * * *, or @reboot")
        self.schedule_input.setText(job.schedule if job and job.schedule else "*/30 * * * *")
        self.schedule_input.textChanged.connect(self._update_preview)
        root.addWidget(self.schedule_input)

        self.preview_label = QLabel()
        self.preview_label.setStyleSheet(f"color: {palette.accent}; font-weight: 600; font-size: 12px;")
        root.addWidget(self.preview_label)

        # Linux Command / Script
        cmd_hdr = QHBoxLayout()
        cmd_hdr.addWidget(self._section_label("Linux command or script to run"))
        cmd_hdr.addStretch()
        browse_btn = GlowButton("Browse Script...", glow_hex=palette.accent, max_blur=12.0)
        browse_btn.setObjectName("CardAction")
        browse_btn.clicked.connect(self._browse_script)
        cmd_hdr.addWidget(browse_btn)
        root.addLayout(cmd_hdr)

        self.command_edit = QPlainTextEdit()
        self.command_edit.setPlaceholderText("e.g., ~/scripts/backup.sh   or   notify-send 'Hello Linux!'")
        self.command_edit.setFixedHeight(84)
        self.command_edit.setStyleSheet('font-family: "JetBrains Mono", "Fira Code", monospace; font-size: 12px;')
        if job:
            self.command_edit.setPlainText(job.command or "")
        root.addWidget(self.command_edit)

        # Quick example chips
        ex_row = QHBoxLayout()
        ex_row.setSpacing(6)
        ex_lbl = QLabel("Examples:")
        ex_lbl.setObjectName("SubtitleLabel")
        ex_row.addWidget(ex_lbl)
        for label, cmd in self.EXAMPLES:
            eb = GlowButton(label, glow_hex=palette.accent, max_blur=10.0)
            eb.setObjectName("ChipButton")
            eb.clicked.connect(lambda checked=False, n=label, c=cmd: self._apply_example(n, c))
            ex_row.addWidget(eb)
        ex_row.addStretch()
        root.addLayout(ex_row)

        # Paused option
        self.paused_check = QCheckBox("Create paused (do not run automatically yet)")
        if job and job.status == "paused":
            self.paused_check.setChecked(True)
        root.addWidget(self.paused_check)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()
        cancel_btn = GlowButton("Cancel", glow_hex=palette.accent, max_blur=12.0)
        cancel_btn.clicked.connect(self.reject)
        save_btn = GlowButton("Save Changes" if is_edit else "Create Task", glow_hex=palette.accent, max_blur=22.0)
        save_btn.setObjectName("PrimaryButton")
        save_btn.clicked.connect(self._submit)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        root.addLayout(btn_row)

        self._update_preview()
        self.name_input.setFocus()

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-weight: 700; font-size: 12px;")
        return lbl

    def _select_preset(self, schedule: str, active_btn: QPushButton) -> None:
        for b in self._preset_buttons:
            if b is not active_btn:
                b.setChecked(False)
        self.schedule_input.setText(schedule)

    def _sync_from_interval(self) -> None:
        for b in self._preset_buttons:
            b.setChecked(False)
        amt = self.amount_spin.value()
        suffix = self.UNIT_MAP[self.unit_combo.currentIndex()][1]
        self.schedule_input.setText(cm.normalize_schedule(f"{amt}{suffix}"))

    def _apply_example(self, name: str, cmd: str) -> None:
        if not self.name_input.text().strip():
            self.name_input.setText(name)
        self.command_edit.setPlainText(cmd)

    def _browse_script(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose a Linux Script or Executable",
            str(cm.Path.home()),
            "Scripts (*.sh *.py *.bash);;All Files (*)",
        )
        if path:
            if path.endswith(".py"):
                self.command_edit.setPlainText(f'python3 "{path}"')
            else:
                self.command_edit.setPlainText(f'"{path}"')
            if not self.name_input.text().strip():
                self.name_input.setText(cm.Path(path).stem.replace("_", " ").replace("-", " ").title())

    def _update_preview(self) -> None:
        sched = self.schedule_input.text().strip()
        self.preview_label.setText(f"⏱  {cm.human_schedule(sched)}")

    def _submit(self) -> None:
        schedule = self.schedule_input.text().strip()
        command = self.command_edit.toPlainText().strip()
        if not schedule:
            QMessageBox.warning(self, "Schedule required", "Please choose or enter a schedule.")
            return
        if not command:
            QMessageBox.warning(self, "Command required", "Please enter a Linux command or choose a script.")
            return

        self.result_payload = {
            "name": self.name_input.text().strip(),
            "schedule": schedule,
            "command": command,
            "paused": self.paused_check.isChecked(),
        }
        self.accept()


class HistoryDialog(QDialog):
    def __init__(self, parent: QWidget, palette: ThemePalette, title: str, text: str) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Logs — {title}")
        self.resize(700, 460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        hdr = QLabel(f"Execution Logs · {title}")
        hdr.setObjectName("TitleLabel")
        layout.addWidget(hdr)

        viewer = QPlainTextEdit()
        viewer.setReadOnly(True)
        viewer.setPlainText(text.strip())
        viewer.setStyleSheet('font-family: "JetBrains Mono", "Fira Code", monospace; font-size: 12px;')
        layout.addWidget(viewer, 1)

        btn_row = QHBoxLayout()
        copy_btn = GlowButton("Copy Logs", glow_hex=palette.accent, max_blur=14.0)
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(viewer.toPlainText()))
        close_btn = GlowButton("Close", glow_hex=palette.accent, max_blur=18.0)
        close_btn.setObjectName("PrimaryButton")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(copy_btn)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)


class JobCard(HoverCard):
    """Premium card representing one native Linux scheduled task."""

    def __init__(
        self,
        job: cm.Job,
        palette: ThemePalette,
        on_run: Callable[[cm.Job], None],
        on_toggle_pause: Callable[[cm.Job], None],
        on_history: Callable[[cm.Job], None],
        on_edit: Callable[[cm.Job], None],
        on_remove: Callable[[cm.Job], None],
    ) -> None:
        super().__init__(glow_hex=palette.accent)
        self.setObjectName("JobCard")
        self.job = job

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(10)

        # Header row: status dot + name + schedule + status badge
        top = QHBoxLayout()
        top.setSpacing(10)

        status_lower = (job.status or "active").lower()
        status_color = {
            "active": palette.success,
            "paused": palette.warning,
            "failed": palette.danger,
        }.get(status_lower, palette.fg_muted)

        dot = QLabel("●")
        dot.setStyleSheet(f"color: {status_color}; font-size: 14px;")
        top.addWidget(dot)

        name_lbl = QLabel(job.name or f"Task {job.id}")
        name_lbl.setStyleSheet("font-size: 15px; font-weight: 700;")
        top.addWidget(name_lbl)

        sched_pill = QLabel(f"⏱  {cm.human_schedule(job.schedule)}")
        sched_pill.setStyleSheet(
            f"background-color: {palette.surface_alt}; color: {palette.fg_muted}; "
            f"border: 1px solid {palette.border}; border-radius: 9px; "
            f"padding: 2px 10px; font-size: 11px; font-weight: 600;"
        )
        top.addWidget(sched_pill)

        top.addStretch()

        badge = QLabel(status_lower.upper())
        badge.setStyleSheet(
            f"background-color: {palette.surface_alt}; color: {status_color}; "
            f"border: 1px solid {status_color}; border-radius: 10px; "
            f"padding: 3px 10px; font-size: 11px; font-weight: 700;"
        )
        top.addWidget(badge)
        outer.addLayout(top)

        # Command preview pill
        cmd_pill = QLabel(f"$  {job.command}")
        cmd_pill.setObjectName("CmdPill")
        cmd_pill.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        outer.addWidget(cmd_pill)

        # Bottom row: next run + hover-glow action buttons
        bottom = QHBoxLayout()
        bottom.setSpacing(8)

        next_text = f"Next: {job.next_run}" if job.next_run else f"Cron: {job.schedule}"
        next_lbl = QLabel(next_text)
        next_lbl.setStyleSheet(f"color: {palette.fg_muted}; font-size: 12px;")
        bottom.addWidget(next_lbl)
        bottom.addStretch()

        run_btn = GlowButton("▶  Run Now", glow_hex=palette.accent, max_blur=18.0)
        run_btn.setObjectName("RunAction")
        run_btn.clicked.connect(lambda: on_run(job))
        bottom.addWidget(run_btn)

        pause_btn = GlowButton(
            "▶  Resume" if status_lower == "paused" else "⏸  Pause",
            glow_hex=palette.warning,
            max_blur=14.0,
        )
        pause_btn.setObjectName("CardAction")
        pause_btn.clicked.connect(lambda: on_toggle_pause(job))
        bottom.addWidget(pause_btn)

        logs_btn = GlowButton("Logs", glow_hex=palette.accent, max_blur=14.0)
        logs_btn.setObjectName("CardAction")
        logs_btn.clicked.connect(lambda: on_history(job))
        bottom.addWidget(logs_btn)

        edit_btn = GlowButton("Edit", glow_hex=palette.accent, max_blur=14.0)
        edit_btn.setObjectName("CardAction")
        edit_btn.clicked.connect(lambda: on_edit(job))
        bottom.addWidget(edit_btn)

        del_btn = GlowButton("Delete", glow_hex=palette.danger, max_blur=16.0)
        del_btn.setObjectName("DangerAction")
        del_btn.clicked.connect(lambda: on_remove(job))
        bottom.addWidget(del_btn)

        outer.addLayout(bottom)


class CronManagerWindow(QMainWindow):
    def __init__(self, theme_watcher: ThemeWatcher) -> None:
        super().__init__()
        self.theme_watcher = theme_watcher
        self.palette_data: ThemePalette = theme_watcher.palette
        self.jobs: list[cm.Job] = []
        self.active_filter: str = "all"
        self._workers: list[WorkerThread] = []
        self._glow_buttons: list[GlowButton] = []

        self.setWindowTitle("Cron Manager")
        self.resize(980, 680)
        self.setMinimumSize(780, 540)

        self._build_ui()
        self._bind_shortcuts()
        self.apply_theme(self.palette_data)
        self.theme_watcher.theme_changed.connect(self.apply_theme)

        QTimer.singleShot(40, self.refresh_jobs)

    def _make_glow_btn(self, text: str, obj_name: str = "", max_blur: float = 18.0) -> GlowButton:
        btn = GlowButton(text, glow_hex=self.palette_data.accent, max_blur=max_blur)
        if obj_name:
            btn.setObjectName(obj_name)
        self._glow_buttons.append(btn)
        return btn

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 20, 24, 18)
        root.setSpacing(16)

        # Premium Header Card
        header_card = QFrame()
        header_card.setObjectName("HeaderCard")
        header = QHBoxLayout(header_card)
        header.setContentsMargins(20, 16, 20, 16)
        header.setSpacing(14)

        logo = QLabel("⏱")
        logo.setObjectName("LogoBadge")
        logo.setFixedSize(44, 44)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(logo)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_lbl = QLabel("Cron Manager")
        title_lbl.setObjectName("TitleLabel")
        subtitle_lbl = QLabel(f"Linux task scheduler · {cm.backend_label()}")
        subtitle_lbl.setObjectName("SubtitleLabel")
        title_col.addWidget(title_lbl)
        title_col.addWidget(subtitle_lbl)
        header.addLayout(title_col)

        header.addStretch()

        self.active_pill = QLabel("0 Active")
        self.active_pill.setObjectName("StatPill")
        self.paused_pill = QLabel("0 Paused")
        self.paused_pill.setObjectName("StatPill")
        header.addWidget(self.active_pill)
        header.addWidget(self.paused_pill)

        refresh_btn = self._make_glow_btn("↻  Refresh", max_blur=14.0)
        refresh_btn.clicked.connect(self.refresh_jobs)
        header.addWidget(refresh_btn)

        new_btn = self._make_glow_btn("+  New Task", obj_name="PrimaryButton", max_blur=24.0)
        new_btn.clicked.connect(self.open_create_dialog)
        header.addWidget(new_btn)

        root.addWidget(header_card)

        # Search + Filter row
        controls = QHBoxLayout()
        controls.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search tasks by name, command, or schedule... (Ctrl+F)")
        self.search_input.textChanged.connect(self._render_cards)
        controls.addWidget(self.search_input, 1)

        self._filter_buttons: dict[str, GlowButton] = {}
        for key, label in (("all", "All"), ("active", "Active"), ("paused", "Paused")):
            btn = self._make_glow_btn(label, obj_name="ChipButton", max_blur=14.0)
            btn.setCheckable(True)
            btn.setChecked(key == "all")
            btn.clicked.connect(lambda checked, k=key: self._set_filter(k))
            controls.addWidget(btn)
            self._filter_buttons[key] = btn

        root.addLayout(controls)

        # Toast banner
        self.toast_frame = QFrame()
        self.toast_frame.setObjectName("ToastBanner")
        toast_layout = QHBoxLayout(self.toast_frame)
        toast_layout.setContentsMargins(14, 9, 14, 9)
        self.toast_label = QLabel("")
        self.toast_label.setStyleSheet("font-weight: 600;")
        toast_layout.addWidget(self.toast_label, 1)
        self.toast_frame.hide()
        root.addWidget(self.toast_frame)

        # Scrollable cards
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(4, 4, 8, 8)
        self.cards_layout.setSpacing(14)
        self.cards_layout.addStretch()
        self.scroll.setWidget(self.cards_container)
        root.addWidget(self.scroll, 1)

        # Footer
        footer = QHBoxLayout()
        self.status_lbl = QLabel("Ready")
        self.status_lbl.setObjectName("SubtitleLabel")
        self.theme_lbl = QLabel("")
        self.theme_lbl.setObjectName("SubtitleLabel")
        footer.addWidget(self.status_lbl)
        footer.addStretch()
        footer.addWidget(self.theme_lbl)
        root.addLayout(footer)

    def _bind_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+N"), self, self.open_create_dialog)
        QShortcut(QKeySequence("Ctrl+R"), self, self.refresh_jobs)
        QShortcut(QKeySequence("F5"), self, self.refresh_jobs)
        QShortcut(QKeySequence("Ctrl+F"), self, self.search_input.setFocus)
        QShortcut(QKeySequence("Ctrl+Q"), self, self.close)

    def apply_theme(self, palette: ThemePalette) -> None:
        self.palette_data = palette
        app = QApplication.instance()
        if app:
            app.setStyleSheet(build_stylesheet(palette))
        for btn in self._glow_buttons:
            btn.update_glow_color(palette.accent)
        self.theme_lbl.setText(f"{palette.source_name} ({palette.mode}) · {palette.accent}")
        self._render_cards()

    def _show_toast(self, message: str, duration_ms: int = 3800) -> None:
        self.toast_label.setText(message)
        self.toast_frame.show()
        QTimer.singleShot(duration_ms, self.toast_frame.hide)

    def _set_filter(self, key: str) -> None:
        self.active_filter = key
        for k, btn in self._filter_buttons.items():
            btn.setChecked(k == key)
        self._render_cards()

    def _run_async(self, status_text: str, fn: Callable, on_ok: Callable, *args, **kwargs) -> None:
        self.status_lbl.setText(status_text)
        worker = WorkerThread(fn, *args, **kwargs)
        self._workers.append(worker)

        def _done(res):
            self._workers.remove(worker)
            on_ok(res)

        def _err(msg):
            self._workers.remove(worker)
            self.status_lbl.setText("Error")
            self._show_toast(f"Error: {msg}", 5500)

        worker.succeeded.connect(_done)
        worker.failed.connect(_err)
        worker.start()

    def refresh_jobs(self) -> None:
        def _loaded(jobs: list[cm.Job]) -> None:
            self.jobs = jobs
            active_n = sum(1 for j in jobs if (j.status or "").lower() == "active")
            paused_n = sum(1 for j in jobs if (j.status or "").lower() == "paused")
            self.active_pill.setText(f"{active_n} Active")
            self.paused_pill.setText(f"{paused_n} Paused")
            self.status_lbl.setText(f"{len(jobs)} scheduled Linux task(s)")
            self._render_cards()

        self._run_async("Loading tasks...", cm.list_jobs, _loaded, include_all=True)

    def _render_cards(self) -> None:
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        q = self.search_input.text().strip().lower()
        filtered = []
        for j in self.jobs:
            st = (j.status or "").lower()
            if self.active_filter != "all" and st != self.active_filter:
                continue
            if q and q not in f"{j.name} {j.command} {j.schedule} {j.status}".lower():
                continue
            filtered.append(j)

        if not filtered:
            empty = QFrame()
            empty.setObjectName("EmptyCard")
            el = QVBoxLayout(empty)
            el.setContentsMargins(36, 48, 36, 48)
            el.setSpacing(12)
            el.setAlignment(Qt.AlignmentFlag.AlignCenter)

            heading = QLabel("No scheduled Linux tasks yet" if not self.jobs else "No matching tasks")
            heading.setStyleSheet("font-size: 18px; font-weight: 700;")
            heading.setAlignment(Qt.AlignmentFlag.AlignCenter)

            desc = QLabel(
                "Automate backups, scripts, cleanup commands, or reminders right on your Linux desktop."
                if not self.jobs
                else "Try clearing your search or switching the filter."
            )
            desc.setObjectName("SubtitleLabel")
            desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
            desc.setWordWrap(True)

            el.addWidget(heading)
            el.addWidget(desc)

            if not self.jobs:
                cta = GlowButton("+  Create First Task", glow_hex=self.palette_data.accent, max_blur=24.0)
                cta.setObjectName("PrimaryButton")
                cta.setFixedWidth(195)
                cta.clicked.connect(self.open_create_dialog)
                el.addSpacing(8)
                el.addWidget(cta, alignment=Qt.AlignmentFlag.AlignCenter)

            self.cards_layout.addWidget(empty)
            self.cards_layout.addStretch()
            return

        for job in filtered:
            card = JobCard(
                job=job,
                palette=self.palette_data,
                on_run=self.run_job_now,
                on_toggle_pause=self.toggle_pause_job,
                on_history=self.show_job_history,
                on_edit=self.open_edit_dialog,
                on_remove=self.remove_job,
            )
            self.cards_layout.addWidget(card)
        self.cards_layout.addStretch()

    def open_create_dialog(self) -> None:
        dlg = JobFormDialog(self, self.palette_data, job=None)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_payload:
            p = dlg.result_payload
            self._run_async(
                "Creating Linux task...",
                cm.create_job,
                lambda _: (self._show_toast("Task created and scheduled!"), self.refresh_jobs()),
                schedule=p["schedule"],
                command=p["command"],
                name=p["name"],
                paused=p["paused"],
            )

    def open_edit_dialog(self, job: cm.Job) -> None:
        dlg = JobFormDialog(self, self.palette_data, job=job)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_payload:
            p = dlg.result_payload
            self._run_async(
                "Updating task...",
                cm.edit_job,
                lambda _: (self._show_toast("Task updated!"), self.refresh_jobs()),
                job.id,
                name=p["name"],
                schedule=p["schedule"],
                command=p["command"],
                paused=p["paused"],
            )

    def run_job_now(self, job: cm.Job) -> None:
        self._run_async(
            f"Running {job.name or job.id}...",
            cm.run_job,
            lambda out: (self._show_toast(out.strip(), 4500), self.refresh_jobs()),
            job.id,
        )

    def toggle_pause_job(self, job: cm.Job) -> None:
        is_paused = (job.status or "").lower() == "paused"
        fn = cm.resume_job if is_paused else cm.pause_job
        verb = "Resuming" if is_paused else "Pausing"
        self._run_async(
            f"{verb} {job.name or job.id}...",
            fn,
            lambda out: (self._show_toast(out.strip()), self.refresh_jobs()),
            job.id,
        )

    def show_job_history(self, job: cm.Job) -> None:
        def _open(out: str) -> None:
            self.status_lbl.setText(f"{len(self.jobs)} scheduled Linux task(s)")
            HistoryDialog(self, self.palette_data, job.name or job.id, out).exec()

        self._run_async("Loading logs...", cm.history, _open, job.id)

    def remove_job(self, job: cm.Job) -> None:
        reply = QMessageBox.question(
            self,
            "Delete Task",
            f"Remove scheduled task '{job.name or job.id}' from Linux?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._run_async(
            "Deleting task...",
            cm.remove_job,
            lambda _: (self._show_toast("Task deleted."), self.refresh_jobs()),
            job.id,
        )


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Cron Manager")
    app.setDesktopFileName("cronmanager")

    watcher = ThemeWatcher(app)
    window = CronManagerWindow(watcher)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
