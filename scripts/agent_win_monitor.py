"""
Simple Windows native monitoring agent (Python).
- On startup, minimizes all other windows to isolate the exam environment.
- Polls the foreground window title and process every second.
- Posts a JSON payload to /agent/report_event with fields: attempt_id, token, event, data

Usage (PowerShell):
    pip install pywin32 psutil requests
    python .\scripts\agent_win_monitor.py --attempt 123 --token ABCDEF --server http://localhost:25570

Security & privacy:
- The agent collects the active window title and process executable name. Only run this with explicit consent from the student.
- Use TLS (https) in production and a secure token for authentication.

"""
import time
import argparse
import requests
import psutil
import sys

try:
    import win32gui
    import win32process
    import win32con
except Exception as e:
    print('This script requires pywin32 (win32gui, win32process, win32con).', file=sys.stderr)
    raise


def get_foreground_process_info():
    try:
        hwnd = win32gui.GetForegroundWindow()
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        proc = psutil.Process(pid)
        title = win32gui.GetWindowText(hwnd) or ''
        exe = proc.exe() if proc else ''
        name = proc.name() if proc else ''
        return {'pid': pid, 'exe': exe, 'name': name, 'title': title}
    except Exception:
        return None


def minimize_other_windows():
    """Minimize all windows except the foreground one to isolate the exam."""
    try:
        fg_hwnd = win32gui.GetForegroundWindow()
        def enum_callback(hwnd, _):
            if hwnd != fg_hwnd and win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
        win32gui.EnumWindows(enum_callback, None)
        print('Minimized other windows.')
    except Exception as e:
        print('Failed to minimize windows:', e)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--attempt', required=True, help='Attempt ID')
    p.add_argument('--token', required=True, help='Agent token (from the exam page)')
    p.add_argument('--server', required=True, help='Server base URL, e.g. http://localhost:25570')
    p.add_argument('--interval', type=float, default=1.0, help='Polling interval seconds')
    args = p.parse_args()

    url = args.server.rstrip('/') + '/agent/report_event'

    # Minimize other windows to isolate the exam
    minimize_other_windows()

    last_info = None
    print(f'Starting agent for attempt {args.attempt}. Reporting to {url}')

    while True:
        info = get_foreground_process_info()
        if info and info != last_info:
            payload = {
                'attempt_id': int(args.attempt),
                'token': args.token,
                'event': 'agent_foreground_change',
                'data': info
            }
            try:
                r = requests.post(url, json=payload, timeout=5)
                if r.status_code != 200:
                    print('Server error:', r.status_code, r.text)
                else:
                    print('Reported:', info.get('title'), '|', info.get('name'))
            except Exception as e:
                print('Failed to report:', e)
            last_info = info
        time.sleep(args.interval)


if __name__ == '__main__':
    main()
