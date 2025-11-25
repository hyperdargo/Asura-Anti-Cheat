# Asura — Client-Side Anti-Cheat Exam Portal

Asura is a Flask-based exam portal prototype with client-side anti-cheat features and optional native monitoring agent support. It includes roles (student, lecturer, staff, admin), timed exams, per-student attempts, autosave, live monitoring for staff, and a sample native Windows agent that can report foreground application info.

🌐 **Live Demo**: [https://exam.ankitgupta.com.np](https://exam.ankitgupta.com.np)

This README explains the code layout, main components, quickstart (Windows PowerShell), developer notes, and security considerations for publishing on GitHub.

---

## Main components / code

- `app.py` — Main Flask application. Implements models, routes, Socket.IO live updates, anti-cheat events endpoints, and the native agent reporting endpoint.
	- Key models: `User`, `Batch`, `Exam`, `Question`, `ExamAttempt`.
	- Notable fields: `Exam.results_published` (controls when scores are shown), `ExamAttempt.events` (JSON list of anti-cheat logs), `ExamAttempt.agent_token` (short token for native agent reporting).
- `templates/` — Jinja2 templates for UI (login, admin, teacher, student, live monitoring, results, etc.).
- `scripts/agent_win_monitor.py` — Example Windows native agent (Python) that polls the foreground window/process and posts events to `POST /agent/report_event`.
- `image/` — image assets used by the UI (e.g., `asura.png`).

## Technology stack

- Python 3.x
- Flask
- Flask-Login
- Flask-SQLAlchemy (SQLite by default)
- Flask-SocketIO (live updates)
- Optional native agent dependencies: `pywin32`, `psutil`, `requests` (Windows only)

## Quick start (Windows PowerShell)

1. Clone the repo and open PowerShell in the project folder (the folder that contains `app.py`).

2. Create and activate a virtual environment (optional but recommended):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
