# Cron Manager

A small, simple GUI to browse, create, edit and delete [Hermes](https://hermes-agent.nousresearch.com) cron jobs. Plain Python + `tkinter`, wraps the `hermes cron` CLI.

## Requirements

- Python 3.10+
- `hermes` CLI available on `PATH`

## Run

```bash
python3 gui.py
```

## Features

- **List** all cron jobs (name, status, schedule, next run)
- **Create** a new job (schedule + prompt + optional name/repeat)
- **Edit** an existing job (name, schedule, pause/resume)
- **Run now**, **Pause/Resume**, **Remove** actions
- **History** view for a job
- Refresh on demand

## Usage

1. Select a job in the list.
2. Use the toolbar:
   - **New Job** — create a job (schedule required; prompt optional)
   - **Edit** — change name / schedule / pause state
   - **Run Now** — trigger the job immediately
   - **Pause/Resume** — toggle the job's active state
   - **History** — see durable execution attempts for a job
   - **Remove** — delete the job

Schedule formats: `30m`, `every 2h`, or a cron expression like `0 9 * * *`.

## Layout

```
cronmanager/
  cronmanager.py   # core library (CLI wrapper + output parsing)
  gui.py           # tkinter front-end
  README.md
  LICENSE
```

## Testing the core

```bash
python3 -c "import cronmanager as cm; print(cm.list_jobs())"
```

## License

MIT — see `LICENSE`.
