# SQLite storage shared by the webcam tracker, the activity tracker, the nudge engine,
# the assistant, and the dashboard API.
#
# All times are Unix timestamps (seconds, float). Local time is only applied when grouping
# by hour or day, so the database stays correct if you travel or the clock changes.
#
# Each process (and each thread) opens its own connection. WAL mode lets the webcam tracker,
# the activity tracker, and the API server write and read at the same time.

import os
import sqlite3
import threading
import time

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,          -- 'webcam' or 'activity'
    start REAL NOT NULL,
    end REAL,                      -- NULL while running
    last_seen REAL NOT NULL        -- heartbeat, so a crashed run still has a known end
);

CREATE TABLE IF NOT EXISTS touch_events (
    id INTEGER PRIMARY KEY,
    session_id INTEGER,
    start REAL NOT NULL,
    end REAL NOT NULL,
    region TEXT,
    behavior TEXT,                 -- classifier label, or 'unclassified'
    alerted INTEGER NOT NULL,
    duration REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS touch_start ON touch_events(start);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY,
    session_id INTEGER,
    ts REAL NOT NULL,              -- the moment the alert fired (the touch is still going on)
    region TEXT,
    behavior TEXT
);
CREATE INDEX IF NOT EXISTS alerts_ts ON alerts(ts);

CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY,
    session_id INTEGER,
    start REAL NOT NULL,
    end REAL NOT NULL,             -- updated while the segment is still open
    app TEXT,
    domain TEXT,                   -- for browsers, when it can be read
    title TEXT,                    -- only stored if ACTIVITY_STORE_TITLES is on
    category TEXT,
    idle INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS activity_start ON activity(start);

CREATE TABLE IF NOT EXISTS nudges (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    trigger TEXT NOT NULL,         -- 'habit' or 'doomscroll'
    context TEXT NOT NULL,         -- bandit context, e.g. 'habit:skin_picking'
    detail TEXT,                   -- e.g. the app or region
    arm TEXT NOT NULL,             -- which swap was suggested
    policy TEXT NOT NULL,          -- 'bandit' or 'random'
    status TEXT NOT NULL,          -- 'pending', 'success', 'failure', 'unknown'
    resolved_at REAL
);
CREATE INDEX IF NOT EXISTS nudges_ts ON nudges(ts);
"""

_lock = threading.Lock()


def default_path():
    return os.path.join(config.DATA_DIR, config.DB_FILENAME)


def connect(path=None):
    path = path or default_path()
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    with _lock:
        conn.executescript(SCHEMA)    # cheap: every statement is IF NOT EXISTS
        conn.commit()
    return conn


def rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


# ---- sessions ----

def start_session(conn, source, now=None):
    now = now or time.time()
    cur = conn.execute("INSERT INTO sessions (source, start, last_seen) VALUES (?, ?, ?)",
                       (source, now, now))
    conn.commit()
    return cur.lastrowid


def heartbeat(conn, session_id, now=None):
    conn.execute("UPDATE sessions SET last_seen = ? WHERE id = ?", (now or time.time(), session_id))
    conn.commit()


def end_session(conn, session_id, now=None):
    now = now or time.time()
    conn.execute("UPDATE sessions SET end = ?, last_seen = ? WHERE id = ?", (now, now, session_id))
    conn.commit()


def coverage(conn, source, start=None, end=None):
    # [(start, end)] intervals when a tracker was running. A session that never closed
    # (crash, killed process) ends at its last heartbeat.
    sql = "SELECT start, COALESCE(end, last_seen) AS end FROM sessions WHERE source = ?"
    params = [source]
    if start is not None:
        sql += " AND COALESCE(end, last_seen) >= ?"
        params.append(start)
    if end is not None:
        sql += " AND start <= ?"
        params.append(end)
    out = []
    for r in conn.execute(sql + " ORDER BY start", params):
        s, e = r["start"], r["end"]
        if start is not None:
            s = max(s, start)
        if end is not None:
            e = min(e, end)
        if e > s:
            out.append((s, e))
    return merge_intervals(out)


def merge_intervals(intervals):
    merged = []
    for s, e in sorted(intervals):
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


# ---- webcam events ----

def log_touch(conn, session_id, start, end, region, behavior, alerted):
    conn.execute(
        "INSERT INTO touch_events (session_id, start, end, region, behavior, alerted, duration) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (session_id, start, end, region, behavior, 1 if alerted else 0, max(end - start, 0.0)))
    conn.commit()


def log_alert(conn, session_id, ts, region, behavior):
    conn.execute("INSERT INTO alerts (session_id, ts, region, behavior) VALUES (?, ?, ?, ?)",
                 (session_id, ts, region, behavior))
    conn.commit()


# ---- activity ----

def open_activity(conn, session_id, now, app, domain, title, category, idle):
    cur = conn.execute(
        "INSERT INTO activity (session_id, start, end, app, domain, title, category, idle) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (session_id, now, now, app, domain, title, category, 1 if idle else 0))
    conn.commit()
    return cur.lastrowid


def extend_activity(conn, activity_id, now):
    conn.execute("UPDATE activity SET end = ? WHERE id = ?", (now, activity_id))
    conn.commit()
