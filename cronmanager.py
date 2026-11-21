"""
cronmanager - core library for reading/managing Hermes cron jobs.

Wraps the `hermes cron` CLI and parses its output into plain Python dicts.
Public, permission-free: just call the functions below.

Example:
    from cronmanager import list_jobs, create_job, edit_job, remove_job

    jobs = list_jobs(include_all=True)
    create_job(schedule="30m", prompt="echo hi", name="Demo")
    edit_job(job_id="...", schedule="15m")
    remove_job(job_id="...")
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from typing import Optional

CMD = ["hermes", "cron"]


def _run(args: list[str], raw: bool = False) -> str:
    """Run a hermes cron subcommand. Raises on failure."""
    res = subprocess.run(
        [*CMD, *args],
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"hermes cron {' '.join(args)} failed: {res.stderr.strip()} {res.stdout.strip()}"
        )
    return res.stdout


@dataclass
class Job:
    id: str = ""
    name: str = ""
    status: str = "active"  # active | paused | completed | ...
    schedule: str = ""
    repeat: str = ""
    next_run: str = ""
    deliver: str = ""
    raw: str = ""

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "schedule": self.schedule,
            "repeat": self.repeat,
            "next_run": self.next_run,
            "deliver": self.deliver,
        }


def list_jobs(include_all: bool = False) -> list[Job]:
    """Return all cron jobs as Job objects. Empty list if none."""
    args = ["list"]
    if include_all:
        args.append("--all")
    out = _run(args)
    return _parse_list(out)


def _parse_list(out: str) -> list[Job]:
    """Parse the box-drawn `hermes cron list` output into Job objects."""
    jobs: list[Job] = []
    lines = out.splitlines()
    block: list[str] = []

    def flush(block: list[str]) -> None:
        if not block:
            return
        text = "\n".join(block)
        job = Job(raw=text)
        # id + status: "  7ea817ddacf6 [active]"
        m = re.search(r"([0-9a-f]{8,})\s+\[([^\]]+)\]", text)
        if m:
            job.id = m.group(1)
            job.status = m.group(2)
        # key: value pairs
        for line in block:
            km = re.match(r"\s*(Name|Schedule|Repeat|Next run|Deliver):\s*(.+)", line)
            if km:
                key = km.group(1).lower().replace(" ", "_")
                val = km.group(2).strip()
                setattr(job, key, val)
        jobs.append(job)

    for line in lines:
        if line.startswith("\u250c") or line.startswith("No scheduled"):
            # header / empty marker -> start fresh block
            block = []
            continue
        if line.strip() == "":
            flush(block)
            block = []
        else:
            block.append(line.rstrip())
    flush(block)
    # drop phantom header-only entries
    return [j for j in jobs if j.id]


def create_job(
    schedule: str,
    prompt: str = "",
    name: str = "",
    repeat: Optional[int] = None,
    paused: bool = False,
) -> Job:
    """Create a cron job. Returns the created Job.

    schedule like '30m', 'every 2h', or cron '0 9 * * *'.
    """
    args = ["create"]
    if name:
        args += ["--name", name]
    if repeat is not None:
        args += ["--repeat", str(repeat)]
    if paused:
        args.append("--paused")
    args += [schedule]
    if prompt:
        args.append(prompt)
    out = _run(args)
    return _parse_create(out)


def _parse_create(out: str) -> Job:
    job = Job()
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("Created job:"):
            job.id = line.split(":", 1)[1].strip()
        km = re.match(r"([A-Za-z _]+):\s*(.+)", line)
        if km:
            key = km.group(1).strip().lower().replace(" ", "_")
            if key in ("name", "schedule", "next_run"):
                setattr(job, key, km.group(2).strip())
    return job


def edit_job(job_id: str, **fields) -> str:
    """Edit an existing job. Supported: schedule, name, repeat, paused.

    Returns the CLI output.
    """
    args = ["edit", job_id]
    if "schedule" in fields:
        args += ["--schedule", fields["schedule"]]
    if "name" in fields:
        args += ["--name", fields["name"]]
    if "repeat" in fields:
        args += ["--repeat", str(fields["repeat"])]
    if fields.get("paused") is True:
        args.append("--paused")
    elif fields.get("paused") is False:
        args.append("--unpaused")
    return _run(args)


def pause_job(job_id: str) -> str:
    return _run(["pause", job_id])


def resume_job(job_id: str) -> str:
    return _run(["resume", job_id])


def run_job(job_id: str) -> str:
    return _run(["run", job_id])


def cancel_job(job_id: str) -> str:
    return _run(["cancel", job_id])


def remove_job(job_id: str) -> str:
    return _run(["remove", job_id])


def history(job_id: str = "") -> str:
    args = ["history"]
    if job_id:
        args.append(job_id)
    return _run(args)
