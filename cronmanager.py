"""
cronmanager — universal native Linux scheduled task backend.

Supports:
  1. Native Linux systemd --user timers (works out of the box on Arch/Omarchy,
     Ubuntu, Debian, Fedora, openSUSE without requiring root or cronie).
  2. Native Linux crontab fallback on non-systemd setups.

Zero third-party dependencies — pure Python standard library.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


SYSTEMD_USER_DIR = Path.home() / ".config" / "systemd" / "user"
DATA_DIR = Path.home() / ".local" / "share" / "cronmanager"
HISTORY_FILE = DATA_DIR / "history.json"
UNIT_PREFIX = "cronmgr-"


@dataclass
class Job:
    id: str = ""
    name: str = ""
    status: str = "active"  # active | paused | failed
    schedule: str = ""
    command: str = ""
    next_run: str = ""
    last_run: str = ""
    backend: str = "systemd"
    managed: bool = True

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "schedule": self.schedule,
            "command": self.command,
            "next_run": self.next_run,
            "last_run": self.last_run,
            "backend": self.backend,
            "managed": self.managed,
        }


def detect_backend() -> str:
    """Return 'systemd' or 'crontab' based on what Linux provides."""
    if shutil.which("systemctl"):
        res = subprocess.run(
            ["systemctl", "--user", "show-environment"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if res.returncode == 0:
            return "systemd"
    if shutil.which("crontab"):
        return "crontab"
    return "systemd"


def backend_label() -> str:
    b = detect_backend()
    return "Linux systemd user timers" if b == "systemd" else "Linux crontab"


def normalize_schedule(schedule: str) -> str:
    """Normalize shorthand intervals ('15m', 'every 2h', '@daily') into standard cron or @keywords."""
    s = (schedule or "").strip()
    if not s:
        return "*/30 * * * *"
    low = s.lower()
    if low in ("@reboot", "@hourly", "@daily", "@weekly", "@monthly"):
        return low

    # Match "15m", "every 15m", "every 15 minutes", "2h", "1d"
    m = re.match(r"^(?:every\s+)?(\d+)\s*(m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)$", low)
    if m:
        amt = max(1, int(m.group(1)))
        unit = m.group(2)
        if unit.startswith("m"):
            return f"*/{min(59, amt)} * * * *"
        if unit.startswith("h"):
            return f"0 */{min(23, amt)} * * *"
        if unit.startswith("d"):
            return "0 9 * * *" if amt == 1 else f"0 9 */{min(31, amt)} * *"
    return s


def cron_to_systemd_timer_spec(schedule: str) -> tuple[str, str]:
    """Convert a cron expression or @keyword into (key, value) for [Timer]."""
    norm = normalize_schedule(schedule).strip()
    low = norm.lower()
    if low == "@reboot":
        return ("OnBootSec", "30s")
    if low == "@hourly":
        return ("OnCalendar", "hourly")
    if low == "@daily":
        return ("OnCalendar", "daily")
    if low == "@weekly":
        return ("OnCalendar", "weekly")
    if low == "@monthly":
        return ("OnCalendar", "monthly")

    parts = norm.split()
    if len(parts) != 5:
        # Allow direct systemd OnCalendar syntax if user entered it
        return ("OnCalendar", norm)

    minute, hour, dom, month, dow = parts

    # Day of week mapping (cron 0 or 7 = Sun, 1 = Mon ... 6 = Sat)
    dow_map = {"0": "Sun", "7": "Sun", "1": "Mon", "2": "Tue", "3": "Wed", "4": "Thu", "5": "Fri", "6": "Sat"}
    dow_prefix = ""
    if dow != "*":
        if dow in dow_map:
            dow_prefix = f"{dow_map[dow]} "
        elif "-" in dow:
            a, b = dow.split("-", 1)
            if a in dow_map and b in dow_map:
                dow_prefix = f"{dow_map[a]}..{dow_map[b]} "
        elif "," in dow:
            names = [dow_map[x] for x in dow.split(",") if x in dow_map]
            if names:
                dow_prefix = ",".join(names) + " "

    def _conv(field: str, pad: bool = True) -> str:
        if field == "*":
            return "*"
        if field.startswith("*/"):
            step = field[2:]
            return f"0/{step}" if pad else f"*/{step}"
        if field.isdigit() and pad:
            return f"{int(field):02d}"
        return field

    m_s = _conv(minute, pad=True)
    h_s = _conv(hour, pad=True)
    dom_s = _conv(dom, pad=True)
    mon_s = _conv(month, pad=True)

    return ("OnCalendar", f"{dow_prefix}*-{mon_s}-{dom_s} {h_s}:{m_s}:00")


def human_schedule(schedule: str) -> str:
    """Turn a cron expression into friendly everyday English."""
    s = normalize_schedule(schedule)
    low = s.lower()
    known = {
        "@reboot": "At system startup",
        "@hourly": "Every hour",
        "@daily": "Every day at 00:00",
        "@weekly": "Every week",
        "@monthly": "Once a month",
        "0 * * * *": "Every hour",
        "0 9 * * *": "Every day at 09:00",
        "0 8 * * *": "Every day at 08:00",
        "0 18 * * *": "Every day at 18:00",
        "0 9 * * 1": "Every Monday at 09:00",
    }
    if low in known:
        return known[low]
    m = re.match(r"^\*/(\d+)\s+\*\s+\*\s+\*\s+\*$", s)
    if m:
        n = int(m.group(1))
        return "Every minute" if n == 1 else f"Every {n} minutes"
    m = re.match(r"^0\s+\*/(\d+)\s+\*\s+\*\s+\*$", s)
    if m:
        n = int(m.group(1))
        return "Every hour" if n == 1 else f"Every {n} hours"
    m = re.match(r"^(\d+)\s+(\d+)\s+\*\s+\*\s+\*$", s)
    if m:
        return f"Every day at {int(m.group(2)):02d}:{int(m.group(1)):02d}"
    return s


# ---- History storage --------------------------------------------------------
def _load_history() -> dict[str, list[dict]]:
    if not HISTORY_FILE.exists():
        return {}
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _append_history(job_id: str, exit_code: int, duration_s: float, output: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    hist = _load_history()
    entries = hist.get(job_id, [])
    entries.insert(
        0,
        {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "exit_code": exit_code,
            "duration_s": round(duration_s, 2),
            "output": output[-4000:],
        },
    )
    hist[job_id] = entries[:25]
    tmp = HISTORY_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(hist, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(HISTORY_FILE)


# ---- Systemd --user backend -------------------------------------------------
def _systemctl(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    res = subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True)
    if check and res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or res.stdout.strip() or f"systemctl {' '.join(args)} failed")
    return res


def _read_systemd_timer_schedule_map() -> dict[str, tuple[str, str]]:
    """Return {unit_name: (next_run, last_run)} from `systemctl --user list-timers --all`."""
    res = _systemctl("list-timers", "--all", "--no-pager", "--no-legend", check=False)
    info: dict[str, tuple[str, str]] = {}
    if res.returncode != 0:
        return info
    for line in res.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.search(r"(\S+\.timer)\s+\S+\.service\s*$", line)
        if not m:
            continue
        unit = m.group(1)
        # Extract NEXT and LEFT nicely
        prefix = line[: m.start()].strip()
        if prefix.startswith("n/a") or prefix.startswith("-"):
            info[unit] = ("Paused / Inactive", "")
        else:
            # Typical: "Sat 2026-11-21 17:30:00 EET 4min left ..."
            tokens = prefix.split()
            next_str = " ".join(tokens[:4]) if len(tokens) >= 4 else prefix[:28]
            left_m = re.search(r"(\d+\w+(?:\s+\d+\w+)?\s+left)", prefix)
            if left_m:
                next_str = f"{next_str} ({left_m.group(1)})"
            info[unit] = (next_str, "")
    return info


def _parse_unit_metadata(service_path: Path, timer_path: Path) -> Job:
    jid = service_path.stem.removeprefix(UNIT_PREFIX)
    name = jid
    schedule = ""
    command = ""

    for p in (service_path, timer_path):
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            if s.startswith("# X-CronManager-Name:"):
                name = s.split(":", 1)[1].strip()
            elif s.startswith("# X-CronManager-Schedule:"):
                schedule = s.split(":", 1)[1].strip()
            elif s.startswith("# X-CronManager-Command:"):
                command = s.split(":", 1)[1].strip()
            elif s.startswith("Description=") and name == jid:
                name = s.split("=", 1)[1].strip()
            elif s.startswith("ExecStart=") and not command:
                command = s.split("=", 1)[1].strip()
            elif s.startswith("OnCalendar=") and not schedule:
                schedule = s.split("=", 1)[1].strip()
            elif s.startswith("OnBootSec=") and not schedule:
                schedule = "@reboot"

    unit = f"{UNIT_PREFIX}{jid}.timer"
    active_res = _systemctl("is-active", unit, check=False)
    is_active = active_res.stdout.strip() in ("active", "waiting", "running")
    status = "active" if is_active else "paused"

    return Job(
        id=jid,
        name=name,
        status=status,
        schedule=schedule,
        command=command,
        backend="systemd",
        managed=True,
    )


def _write_systemd_units(job_id: str, name: str, schedule: str, command: str) -> None:
    SYSTEMD_USER_DIR.mkdir(parents=True, exist_ok=True)
    norm_sched = normalize_schedule(schedule)
    timer_key, timer_val = cron_to_systemd_timer_spec(norm_sched)

    safe_cmd = shlex.quote(command)
    service_content = (
        f"# X-CronManager-Name: {name}\n"
        f"# X-CronManager-Schedule: {norm_sched}\n"
        f"# X-CronManager-Command: {command}\n"
        f"[Unit]\n"
        f"Description={name or f'Cron Manager Task {job_id}'}\n\n"
        f"[Service]\n"
        f"Type=oneshot\n"
        f"ExecStart=/usr/bin/env bash -lc {safe_cmd}\n"
    )
    timer_content = (
        f"# X-CronManager-Name: {name}\n"
        f"# X-CronManager-Schedule: {norm_sched}\n"
        f"[Unit]\n"
        f"Description=Timer for {name or job_id}\n\n"
        f"[Timer]\n"
        f"{timer_key}={timer_val}\n"
        f"Persistent=true\n\n"
        f"[Install]\n"
        f"WantedBy=timers.target\n"
    )

    service_file = SYSTEMD_USER_DIR / f"{UNIT_PREFIX}{job_id}.service"
    timer_file = SYSTEMD_USER_DIR / f"{UNIT_PREFIX}{job_id}.timer"
    service_file.write_text(service_content, encoding="utf-8")
    timer_file.write_text(timer_content, encoding="utf-8")
    _systemctl("daemon-reload")


# ---- Public API -------------------------------------------------------------
def list_jobs(include_all: bool = True) -> list[Job]:
    """List all scheduled Linux tasks managed by Cron Manager."""
    if detect_backend() == "systemd":
        if not SYSTEMD_USER_DIR.exists():
            return []
        timers_map = _read_systemd_timer_schedule_map()
        jobs: list[Job] = []
        for timer_file in sorted(SYSTEMD_USER_DIR.glob(f"{UNIT_PREFIX}*.timer")):
            service_file = timer_file.with_suffix(".service")
            job = _parse_unit_metadata(service_file, timer_file)
            next_run, last_run = timers_map.get(timer_file.name, ("", ""))
            job.next_run = next_run if job.status == "active" else "Paused"
            job.last_run = last_run
            if include_all or job.status == "active":
                jobs.append(job)
        return jobs

    # Crontab fallback
    return _list_crontab_jobs()


def create_job(
    schedule: str,
    command: str = "",
    name: str = "",
    paused: bool = False,
    **kwargs,
) -> Job:
    cmd = (command or kwargs.get("prompt", "")).strip()
    if not cmd:
        raise RuntimeError("Command cannot be empty.")
    norm_sched = normalize_schedule(schedule)
    job_id = uuid.uuid4().hex[:8]
    display_name = name.strip() or cmd[:36]

    if detect_backend() == "systemd":
        _write_systemd_units(job_id, display_name, norm_sched, cmd)
        unit = f"{UNIT_PREFIX}{job_id}.timer"
        if paused:
            _systemctl("disable", "--now", unit, check=False)
        else:
            _systemctl("enable", "--now", unit)
        return Job(
            id=job_id,
            name=display_name,
            status="paused" if paused else "active",
            schedule=norm_sched,
            command=cmd,
            backend="systemd",
        )

    return _create_crontab_job(job_id, display_name, norm_sched, cmd, paused)


def edit_job(job_id: str, **fields) -> str:
    jobs = {j.id: j for j in list_jobs(include_all=True)}
    existing = jobs.get(job_id)
    if not existing:
        raise RuntimeError(f"Task '{job_id}' not found.")

    new_name = fields.get("name", existing.name) or existing.name
    new_sched = normalize_schedule(fields.get("schedule", existing.schedule) or existing.schedule)
    new_cmd = (fields.get("command") or fields.get("prompt") or existing.command).strip()
    paused = fields.get("paused", existing.status == "paused")

    if detect_backend() == "systemd":
        _write_systemd_units(job_id, new_name, new_sched, new_cmd)
        unit = f"{UNIT_PREFIX}{job_id}.timer"
        if paused:
            _systemctl("disable", "--now", unit, check=False)
        else:
            _systemctl("enable", "--now", unit)
        return f"Updated '{new_name}'"

    return _edit_crontab_job(job_id, new_name, new_sched, new_cmd, bool(paused))


def pause_job(job_id: str) -> str:
    if detect_backend() == "systemd":
        _systemctl("disable", "--now", f"{UNIT_PREFIX}{job_id}.timer", check=False)
        return f"Paused task {job_id}"
    return edit_job(job_id, paused=True)


def resume_job(job_id: str) -> str:
    if detect_backend() == "systemd":
        _systemctl("enable", "--now", f"{UNIT_PREFIX}{job_id}.timer")
        return f"Resumed task {job_id}"
    return edit_job(job_id, paused=False)


def run_job(job_id: str) -> str:
    jobs = {j.id: j for j in list_jobs(include_all=True)}
    job = jobs.get(job_id)
    if not job:
        raise RuntimeError(f"Task '{job_id}' not found.")

    start = time.monotonic()
    res = subprocess.run(
        ["/usr/bin/env", "bash", "-lc", job.command],
        capture_output=True,
        text=True,
        timeout=60,
    )
    elapsed = time.monotonic() - start
    combined = (res.stdout + ("\n" + res.stderr if res.stderr else "")).strip()
    _append_history(job_id, res.returncode, elapsed, combined or "(no output)")

    if res.returncode != 0:
        return f"Finished with exit code {res.returncode} ({elapsed:.1f}s)\n{combined}"
    return f"Ran successfully in {elapsed:.1f}s" + (f" — {combined[:140]}" if combined else "")


def remove_job(job_id: str) -> str:
    if detect_backend() == "systemd":
        timer_unit = f"{UNIT_PREFIX}{job_id}.timer"
        service_unit = f"{UNIT_PREFIX}{job_id}.service"
        _systemctl("disable", "--now", timer_unit, check=False)
        _systemctl("stop", service_unit, check=False)
        for p in (SYSTEMD_USER_DIR / timer_unit, SYSTEMD_USER_DIR / service_unit):
            if p.exists():
                p.unlink()
        _systemctl("daemon-reload", check=False)
        return f"Deleted task {job_id}"
    return _remove_crontab_job(job_id)


def history(job_id: str = "") -> str:
    sections: list[str] = []

    local = _load_history().get(job_id, [])
    if local:
        lines = ["=== Recent Manual Runs ==="]
        for entry in local:
            status = "OK" if entry["exit_code"] == 0 else f"EXIT {entry['exit_code']}"
            lines.append(f"[{entry['timestamp']}] {status} ({entry['duration_s']}s)")
            if entry["output"]:
                lines.append(entry["output"])
            lines.append("")
        sections.append("\n".join(lines))

    if detect_backend() == "systemd" and shutil.which("journalctl") and job_id:
        res = subprocess.run(
            ["journalctl", "--user", "-u", f"{UNIT_PREFIX}{job_id}.service", "-n", "40", "--no-pager"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0 and res.stdout.strip():
            sections.append("=== Systemd Journal Logs ===\n" + res.stdout.strip())

    return "\n\n".join(sections).strip() or "No execution logs yet. Click 'Run Now' to test this task."


# ---- Crontab fallback implementation ----------------------------------------
def _read_crontab_lines() -> list[str]:
    res = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if res.returncode != 0:
        return []
    return res.stdout.splitlines()


def _write_crontab_lines(lines: list[str]) -> None:
    payload = "\n".join(lines).rstrip() + "\n"
    res = subprocess.run(["crontab", "-"], input=payload, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or "Failed to write crontab.")


def _list_crontab_jobs() -> list[Job]:
    lines = _read_crontab_lines()
    jobs: list[Job] = []
    pending_meta: Optional[tuple[str, str]] = None
    for idx, raw in enumerate(lines):
        s = raw.strip()
        m = re.match(r"^#\s*cronmanager:\s*id=(\S+)\s*\|\s*name=(.*)$", s)
        if m:
            pending_meta = (m.group(1), m.group(2).strip())
            continue
        if not s:
            pending_meta = None
            continue
        paused = False
        body = s
        if s.startswith("# [PAUSED] "):
            paused = True
            body = s[len("# [PAUSED] ") :].strip()
        elif s.startswith("#"):
            pending_meta = None
            continue

        if body.startswith("@"):
            parts = body.split(None, 1)
            if len(parts) < 2:
                continue
            sched, cmd = parts[0], parts[1]
        else:
            parts = body.split(None, 5)
            if len(parts) < 6:
                continue
            sched = " ".join(parts[:5])
            cmd = parts[5]

        jid = pending_meta[0] if pending_meta else f"cron{idx}"
        name = pending_meta[1] if pending_meta else cmd[:36]
        pending_meta = None
        jobs.append(
            Job(
                id=jid,
                name=name,
                status="paused" if paused else "active",
                schedule=sched,
                command=cmd,
                next_run="Paused" if paused else human_schedule(sched),
                backend="crontab",
            )
        )
    return jobs


def _create_crontab_job(job_id: str, name: str, schedule: str, command: str, paused: bool) -> Job:
    lines = _read_crontab_lines()
    lines.append(f"# cronmanager: id={job_id} | name={name}")
    prefix = "# [PAUSED] " if paused else ""
    lines.append(f"{prefix}{schedule} {command}")
    _write_crontab_lines(lines)
    return Job(id=job_id, name=name, status="paused" if paused else "active", schedule=schedule, command=command, backend="crontab")


def _edit_crontab_job(job_id: str, name: str, schedule: str, command: str, paused: bool) -> str:
    lines = _read_crontab_lines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        if re.match(rf"^#\s*cronmanager:\s*id={re.escape(job_id)}\b", lines[i].strip()):
            out.append(f"# cronmanager: id={job_id} | name={name}")
            prefix = "# [PAUSED] " if paused else ""
            out.append(f"{prefix}{schedule} {command}")
            i += 2
            continue
        out.append(lines[i])
        i += 1
    _write_crontab_lines(out)
    return f"Updated '{name}'"


def _remove_crontab_job(job_id: str) -> str:
    lines = _read_crontab_lines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        if re.match(rf"^#\s*cronmanager:\s*id={re.escape(job_id)}\b", lines[i].strip()):
            i += 2
            continue
        out.append(lines[i])
        i += 1
    _write_crontab_lines(out)
    return f"Deleted task {job_id}"
