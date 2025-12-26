"""
Student Proctoring GUI Application
A Tkinter-based app for students to easily run the monitoring agent.
"""

import tkinter as tk
from tkinter import messagebox, ttk
import webbrowser
import subprocess
import sys
import os

class ProctorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Student Proctoring App")
        self.root.geometry("400x300")
        self.root.resizable(False, False)

        # Title
        title_label = ttk.Label(root, text="Exam Proctoring Monitor", font=("Arial", 16, "bold"))
        title_label.pack(pady=20)

        # Open Site Button
        open_btn = ttk.Button(root, text="Open Exam Site & Login", command=self.open_site)
        open_btn.pack(pady=10)

        # Token Entry
        token_frame = ttk.Frame(root)
        token_frame.pack(pady=5)
        ttk.Label(token_frame, text="Agent Token:").pack(side=tk.LEFT)
        self.token_entry = ttk.Entry(token_frame, width=30)
        self.token_entry.pack(side=tk.LEFT, padx=5)

        # Attempt ID Entry
        attempt_frame = ttk.Frame(root)
        attempt_frame.pack(pady=5)
        ttk.Label(attempt_frame, text="Attempt ID:").pack(side=tk.LEFT)
        self.attempt_entry = ttk.Entry(attempt_frame, width=30)
        self.attempt_entry.pack(side=tk.LEFT, padx=5)

        # Start Monitoring Button
        start_btn = ttk.Button(root, text="Start Monitoring", command=self.start_monitoring)
        start_btn.pack(pady=20)

        # Status Label
        self.status_label = ttk.Label(root, text="", foreground="blue")
        self.status_label.pack(pady=10)

    def open_site(self):
        """Open the exam site in the default browser."""
        try:
            webbrowser.open('https://exam.ankitgupta.com.np/')
            self.status_label.config(text="Site opened in browser. Please login and start your exam.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open site: {e}")

    def start_monitoring(self):
        """Start the monitoring agent with provided credentials."""
        token = self.token_entry.get().strip()
        attempt_id = self.attempt_entry.get().strip()

        if not token or not attempt_id:
            messagebox.showerror("Error", "Please enter both Agent Token and Attempt ID.")
            return

        # Path to the agent script
        script_path = os.path.join(os.path.dirname(__file__), 'scripts', 'agent_win_monitor.py')
        if not os.path.exists(script_path):
            messagebox.showerror("Error", f"Agent script not found at {script_path}")
            return

        try:
            # Run the agent
            cmd = [sys.executable, script_path, '--attempt', attempt_id, '--token', token, '--server', 'https://exam.ankitgupta.com.np/']
            subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
            self.status_label.config(text="Monitoring started! Check the console window.")
            messagebox.showinfo("Success", "Monitoring agent started. It will minimize other windows and monitor activity.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start monitoring: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = ProctorApp(root)
    root.mainloop()