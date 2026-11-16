# Watches both trackers, sends a swap suggestion when a habit alert fires or when you have been
# doomscrolling for a while, and later decides whether the nudge worked.
#
# Success: from NUDGE_GRACE_SECONDS after the nudge until NUDGE_OUTCOME_MINUTES after it,
#   habit nudge       no habit contact (no alert, no habit touch overlapping that window)
#   doomscroll nudge  at most 30 seconds in a doomscroll category during that window
# If the tracker that would see the behavior wasn't running for most of that window,
# the outcome is 'unknown' and the nudge is left out of the bandit and the comparison.

import threading
import time

import alerts
import config
from backend import bandit as bandit_mod
from backend import db

DOOM_ALLOWED_SECONDS = 30
COVERAGE_NEEDED = 0.9
HABITS = list(config.HABIT_LABELS)


def covered_fraction(intervals, s, e):
    total = sum(max(0, min(b, e) - max(a, s)) for a, b in intervals)
    return total / (e - s) if e > s else 0


def doomscroll_streak(conn, now):
    # seconds of (nearly) continuous doomscrolling that is still going on right now
    recent = db.rows(conn, "SELECT start, end, category, idle, domain, app FROM activity "
                           "WHERE end >= ? ORDER BY start DESC", (now - 6 * 3600,))
    if not recent:
        return 0, None
    latest = recent[0]
    if latest["end"] < now - 3 * config.ACTIVITY_POLL_SECONDS - 5:
        return 0, None     # the activity tracker isn't running
    if latest["category"] not in config.DOOMSCROLL_CATEGORIES or latest["idle"]:
        return 0, None
    start = latest["start"]
    where = latest["domain"] or latest["app"]
    for seg in recent[1:]:
        if seg["idle"]:
            break
        if seg["category"] in config.DOOMSCROLL_CATEGORIES:
            start = seg["start"]
        elif seg["end"] - seg["start"] > config.STREAK_GAP_SECONDS:
            break
    return now - start, where


def judge(conn, nudge, now):
    s = nudge["ts"] + config.NUDGE_GRACE_SECONDS
    e = nudge["ts"] + config.NUDGE_OUTCOME_MINUTES * 60
    source = "webcam" if nudge["trigger"] == "habit" else "activity"
    if covered_fraction(db.coverage(conn, source, s, e), s, e) < COVERAGE_NEEDED:
        return "unknown"
    if nudge["trigger"] == "habit":
        placeholders = ",".join("?" * len(HABITS))
        n_alerts = conn.execute("SELECT COUNT(*) FROM alerts WHERE ts >= ? AND ts <= ?", (s, e)).fetchone()[0]
        n_touch = conn.execute(
            "SELECT COUNT(*) FROM touch_events WHERE end >= ? AND start <= ? AND "
            "(behavior IN (" + placeholders + ") OR (behavior = 'unclassified' AND alerted = 1))",
            (s, e, *HABITS)).fetchone()[0]
        return "failure" if n_alerts or n_touch else "success"
    doom = 0.0
    cats = ",".join("?" * len(config.DOOMSCROLL_CATEGORIES))
    for seg in db.rows(conn, "SELECT start, end FROM activity WHERE end >= ? AND start <= ? AND idle = 0 "
                             "AND category IN (" + cats + ")", (s, e, *config.DOOMSCROLL_CATEGORIES)):
        doom += min(seg["end"], e) - max(seg["start"], s)
    return "failure" if doom > DOOM_ALLOWED_SECONDS else "success"


class NudgeEngine:
    def __init__(self, db_path=None, notify=None, seed=None):
        self.db_path = db_path
        self.notify = notify or alerts.notify
        self.seed = seed
        self.stop_event = threading.Event()
        self.last_alert_id = None
        self.latest = None     # last nudge sent, for the dashboard

    def last_nudge_time(self, conn, trigger):
        r = conn.execute("SELECT MAX(ts) FROM nudges WHERE trigger = ?", (trigger,)).fetchone()[0]
        return r or 0

    def send(self, conn, policy, trigger, context, detail, now):
        arm, chosen_by = policy.choose(trigger, context)
        conn.execute("INSERT INTO nudges (ts, trigger, context, detail, arm, policy, status) "
                     "VALUES (?, ?, ?, ?, ?, ?, 'pending')", (now, trigger, context, detail, arm, chosen_by))
        conn.commit()
        text = config.NUDGE_ARMS[arm]
        title = "Swap idea" if trigger == "habit" else "You've been scrolling a while"
        self.notify(title, text)
        self.latest = {"ts": now, "trigger": trigger, "context": context, "arm": arm, "text": text,
                       "policy": chosen_by}

    def step(self, conn, now):
        policy = bandit_mod.Bandit.from_db(conn, self.seed)

        # 1. resolve old nudges
        for n in db.rows(conn, "SELECT * FROM nudges WHERE status = 'pending' AND ts <= ?",
                         (now - config.NUDGE_OUTCOME_MINUTES * 60 - 15,)):
            conn.execute("UPDATE nudges SET status = ?, resolved_at = ? WHERE id = ?",
                         (judge(conn, n, now), now, n["id"]))
        conn.commit()

        cooldown = config.NUDGE_COOLDOWN_MINUTES * 60
        # 2. habit alerts from the webcam tracker
        if self.last_alert_id is None:
            self.last_alert_id = conn.execute("SELECT COALESCE(MAX(id), 0) FROM alerts").fetchone()[0]
        new = db.rows(conn, "SELECT * FROM alerts WHERE id > ? ORDER BY id", (self.last_alert_id,))
        if new:
            self.last_alert_id = new[-1]["id"]
            alert = new[-1]
            if now - alert["ts"] < 60 and now - self.last_nudge_time(conn, "habit") >= cooldown:
                behavior = alert["behavior"] if alert["behavior"] in HABITS else "any"
                self.send(conn, policy, "habit", "habit:" + behavior, alert["region"], now)

        # 3. doomscrolling from the activity tracker
        seconds, where = doomscroll_streak(conn, now)
        if seconds >= config.DOOMSCROLL_MINUTES * 60 and now - self.last_nudge_time(conn, "doomscroll") >= cooldown:
            self.send(conn, policy, "doomscroll", "doomscroll", where, now)

    def run(self, interval=5):
        conn = db.connect(self.db_path)
        while not self.stop_event.is_set():
            try:
                self.step(conn, time.time())
            except Exception as error:
                print("nudge engine:", error)
            self.stop_event.wait(interval)
        conn.close()

    def start_background(self):
        thread = threading.Thread(target=self.run, daemon=True)
        thread.start()
        return thread

    def stop(self):
        self.stop_event.set()
