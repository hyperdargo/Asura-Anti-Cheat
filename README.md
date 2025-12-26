# Asura — Client-Side Anti-Cheat Exam Portal

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-2.x-000?logo=flask&logoColor=white)
![License](https://img.shields.io/badge/License-Academic-blue)

Asura is a Flask-based exam platform with built-in anti-cheat enforcement, real-time monitoring, and optional native/browser helpers. It supports multiple roles (student, lecturer, staff, admin), timed exams with autosave, and detailed event trails so proctors can react quickly.

---

## Table of Contents

1. [Features](#features)
2. [Architecture Overview](#architecture-overview)
3. [Repository Layout](#repository-layout)
4. [Quick Start (Windows PowerShell)](#quick-start-windows-powershell)
5. [Running an Exam Session](#running-an-exam-session)
6. [Native Monitoring Toolkit (Windows)](#native-monitoring-toolkit-windows)
7. [Browser Extension](#browser-extension)
8. [Configuration](#configuration)
9. [Security & Privacy](#security--privacy)
10. [Contributing](#contributing)

---

## Features

- **Role-aware workflows** — students take exams, lecturers manage content, admins oversee users, staff monitor attempts.
- **Fullscreen & shortcut enforcement** — `take_exam.html` blocks Alt+F4, Alt+Tab, Win key, PrintScreen, Ctrl+S/P, DevTools, and exits on fullscreen loss.
- **Screenshot deterrence** — white overlay + event logging (`exam_portal_screenshot_possible`) when capture is suspected.
- **Live monitoring** — Socket.IO dashboard streams `exam_portal_focus/blur/hidden` and shortcut events.
- **Native agent support** — foreground window/process reporting with per-attempt tokens.
- **Autosave & deadline enforcement** — client autosaves every 30 s and submits at cutoff.

---

## Architecture Overview

```text
Students ──> Flask Web App ──> SQLite (default)
          │          │
          │          └─> Socket.IO live monitor (staff/admin)
          ├─> Optional Chrome extension (tab guard, token helper)
          └─> Optional Windows agent (foreground process telemetry)
```

---

## Repository Layout

| Path | Purpose |
|------|---------|
| `app.py` | Flask app: models, routes, live monitoring rooms, anti-cheat endpoints. |
| `templates/` | Jinja UI (notably `take_exam.html` with enforcement logic). |
| `scripts/agent_win_monitor.py` | Windows agent posting foreground process/window metadata. |
| `student_monitor_app.py` | Tkinter launcher that validates tokens and terminates blocked processes (Task Manager, cmd, PowerShell). |
| `exam_proctor_extension/` | Chrome extension that closes non-exam tabs and exposes attempt tokens. |
| `static/` | Static assets (CSS/JS/extension zip). |

---

## Quick Start (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python .\app.py
```

First boot seeds the default admin:

```
username: admin
password: adminpass
```

Update these credentials and `SECRET_KEY` before any deployment.

---

## Running an Exam Session

1. Lecturer creates + starts an exam (`/teacher/exams`).
2. Student navigates to `/student/exams`, launches attempt, and clicks **Enter Fullscreen & Begin**.
3. Portal behaviour:
   - Reveals questions only after fullscreen succeeds.
   - Blocks critical shortcuts via a top-level capture listener (`exam_portal_shortcut_blocked` events).
   - Logs focus/visibility changes (`exam_portal_focus`, `exam_portal_blur`, `exam_portal_hidden`, `exam_portal_visible`).
   - Shows a white overlay on suspected screenshot capture.
   - Autosaves answers every 30 s and auto-submits at deadline.
4. Staff monitors attempts via the live dashboard; event feed now uses the descriptive labels above.

---

## Native Monitoring Toolkit (Windows)

| Component | Purpose | Usage |
|-----------|---------|-------|
| `student_monitor_app.py` | GUI wrapper to launch the agent safely | Run with Python 3, enter **Attempt ID** & **Agent Token**, click **Start Monitoring**. A background thread continually kills blocked processes. |
| `scripts/agent_win_monitor.py` | Foreground process telemetry | ```powershell<br>python scripts/agent_win_monitor.py --attempt <ID> --token <TOKEN> --server http://localhost:25570<br>``` Requires `pywin32`, `psutil`, `requests`. |

Tokens appear on the exam page. The agent reports to `POST /agent/report_event`.

---

## Browser Extension

`exam_proctor_extension` ships a minimal Chrome extension that:

- Closes tabs unrelated to the exam when triggered.
- Displays the attempt token in `popup.html` with a copy button.

Load via Chrome’s **Load unpacked** in developer mode.

---

## Configuration

- `SECRET_KEY` — Flask secret key (change in production).
- `DATABASE_URL` — SQLAlchemy connection URI (defaults to SQLite).
- `HOST`, `PORT` — server bind parameters (defaults: `0.0.0.0`, `25570`).
- Socket.IO needs `eventlet` or `gevent` for production-grade WebSocket support.
- Serve via HTTPS when native agents are in use.

---

## Security & Privacy

- Obtain user consent before collecting foreground window/process names.
- Harden JSON endpoints with CSRF tokens or signed payloads.
- Define retention policies for `ExamAttempt.events`.
- Browsers cannot fully block OS-level screenshots—combine with live supervision and the native agent for stronger guarantees.

---

## Contributing

Contributions welcome. Please:

- Submit focused PRs with relevant tests or DB migrations.
- Document schema changes (consider Alembic).
- Respect privacy regulations in any new telemetry.

---
