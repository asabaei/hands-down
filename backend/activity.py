# Logs which app (and for browsers, which site) is in the foreground.
#
#   python -m backend.activity            # on its own
#   python -m backend.server              # also starts it in the background
#
# Each stretch of time in one app/site is one row in the activity table. While a stretch is
# still going on its end time is updated, so the dashboard and the nudge engine see it live.
# When there is no keyboard or mouse input for ACTIVITY_IDLE_SECONDS the stretch is marked idle,
# so leaving YouTube open while you make lunch doesn't count as watching it.
#
# Platforms:
#   macOS:   osascript (frontmost app, plus the URL for Chrome, Safari, Arc, Brave, Edge).
#            The first run asks for Automation / Accessibility permission for your terminal.
#   Windows: the Win32 API through ctypes (no extra packages). The site is guessed from the title.
#   Linux:   xdotool and xprintidle on X11 (Wayland doesn't let apps see other windows).

import argparse
import ctypes
import os
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse

import config
from backend import categories, db

MAC_URL_SCRIPTS = {
    "Google Chrome": 'tell application "Google Chrome" to get URL of active tab of front window',
    "Brave Browser": 'tell application "Brave Browser" to get URL of active tab of front window',
    "Microsoft Edge": 'tell application "Microsoft Edge" to get URL of active tab of front window',
    "Arc": 'tell application "Arc" to get URL of active tab of front window',
    "Chromium": 'tell application "Chromium" to get URL of active tab of front window',
    "Safari": 'tell application "Safari" to get URL of front document',
}


def run(cmd):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


# ---- macOS ----

def mac_window():
    app = run(["osascript", "-e",
               'tell application "System Events" to get name of first application process '
               'whose frontmost is true'])
    title = run(["osascript", "-e",
                 'tell application "System Events" to tell (first application process whose '
                 'frontmost is true) to get name of front window'])
    url = None
    if app in MAC_URL_SCRIPTS:
        url = run(["osascript", "-e", MAC_URL_SCRIPTS[app]])
    return app, title, url


def mac_idle():
    out = run(["ioreg", "-c", "IOHIDSystem"])
    if not out:
        return 0.0
    for line in out.splitlines():
        if "HIDIdleTime" in line:
            try:
                return int(line.split("=")[-1].strip()) / 1e9
            except ValueError:
                return 0.0
    return 0.0


# ---- Windows ----

def win_window():
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    hwnd = user32.GetForegroundWindow()
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    title = buf.value

    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    app = None
    handle = kernel32.OpenProcess(0x1000, False, pid.value)   # PROCESS_QUERY_LIMITED_INFORMATION
    if handle:
        size = ctypes.c_ulong(512)
        path = ctypes.create_unicode_buffer(512)
        if kernel32.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
            app = os.path.basename(path.value)
        kernel32.CloseHandle(handle)
    return app, title, None


def win_idle():
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    return (ctypes.windll.kernel32.GetTickCount() - info.dwTime) / 1000.0


# ---- Linux (X11) ----

def linux_window():
    wid = run(["xdotool", "getactivewindow"])
    if not wid:
        return None, None, None
    title = run(["xdotool", "getwindowname", wid])
    pid = run(["xdotool", "getwindowpid", wid])
    app = None
    if pid:
        try:
            with open("/proc/" + pid + "/comm") as f:
                app = f.read().strip()
        except OSError:
            pass
    return app, title, None


def linux_idle():
    out = run(["xprintidle"])
    return int(out) / 1000.0 if out and out.isdigit() else 0.0


def read_window():
    # returns (app, title, url) for the focused window, or (None, None, None)
    if sys.platform == "darwin":
        return mac_window()
    if sys.platform.startswith("win"):
        return win_window()
    return linux_window()


def read_idle_seconds():
    if sys.platform == "darwin":
        return mac_idle()
    if sys.platform.startswith("win"):
        return win_idle()
    return linux_idle()


def describe(app, title, url, idle_seconds):
    # -> (app, domain, title_or_None, category, idle)
    domain = None
    if url:
        domain = categories.normalize_domain(urlparse(url).hostname)
    elif categories.is_browser(app):
        domain = categories.site_from_title(title)
    idle = idle_seconds >= config.ACTIVITY_IDLE_SECONDS
    category = "idle" if idle else categories.categorize(app, domain, title)
    keep_title = title if config.ACTIVITY_STORE_TITLES else None
    return (app or "unknown", domain, keep_title, category, idle)


class ActivityTracker:
    def __init__(self, db_path=None, reader=None, idle_reader=None):
        self.db_path = db_path
        self.reader = reader or read_window
        self.idle_reader = idle_reader or read_idle_seconds
        self.stop_event = threading.Event()
        self.current = None       # (app, domain, category, idle) of the open segment
        self.current_id = None
        self.last = None          # latest description, for the API

    def step(self, conn, session_id, now):
        app, title, url = self.reader()
        info = describe(app, title, url, self.idle_reader())
        key = (info[0], info[1], info[3], info[4])
        self.last = {"app": info[0], "domain": info[1], "category": info[3], "idle": info[4], "since": now}
        if key == self.current and self.current_id is not None:
            db.extend_activity(conn, self.current_id, now)
            self.last["since"] = self.since
        else:
            if self.current_id is not None:
                db.extend_activity(conn, self.current_id, now)
            self.current_id = db.open_activity(conn, session_id, now, *info)
            self.current = key
            self.since = now

    def run(self):
        conn = db.connect(self.db_path)
        session_id = db.start_session(conn, "activity")
        last_beat = 0
        try:
            while not self.stop_event.is_set():
                now = time.time()
                try:
                    self.step(conn, session_id, now)
                except Exception as error:   # one bad read shouldn't stop the tracker
                    print("activity tracker:", error)
                if now - last_beat >= config.HEARTBEAT_SECONDS:
                    db.heartbeat(conn, session_id, now)
                    last_beat = now
                self.stop_event.wait(config.ACTIVITY_POLL_SECONDS)
        finally:
            if self.current_id is not None:
                db.extend_activity(conn, self.current_id, time.time())
            db.end_session(conn, session_id)
            conn.close()

    def start_background(self):
        thread = threading.Thread(target=self.run, daemon=True)
        thread.start()
        return thread

    def stop(self):
        self.stop_event.set()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=None, help="database file (default: data/habits.db)")
    args = parser.parse_args()
    tracker = ActivityTracker(args.db)
    print("tracking the focused window, Ctrl+C to stop")
    try:
        tracker.run()
    except KeyboardInterrupt:
        tracker.stop()


if __name__ == "__main__":
    main()
