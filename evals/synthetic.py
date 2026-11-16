# Generates weeks of fake but realistic data with KNOWN patterns planted in it.
#
#   python -m evals.synthetic --out data_demo/habits.db
#
# Planted patterns (the ground truth the analytics and the LLM evals check against):
#   1. skin_picking is 3x more frequent on reddit.com at night (23:00-05:00)
#   2. nail_biting is 3.5x more frequent once a VS Code session passes 45 minutes
#   3. eye_rubbing has NO pattern (same rate everywhere), so any pattern "found" for it is false
#
# Nudge outcomes are also simulated: each swap has a true success probability per trigger,
# and the stored nudges come from a Thompson-sampling bandit with a 20% random group,
# so the dashboard's bandit panel has something to show.

import argparse
import math
import os
import random
import time

import config
from backend import db

BASE_RATES = {"skin_picking": 0.6, "nail_biting": 0.4, "eye_rubbing": 0.3}   # per observed hour
PLANTED = [
    {"behavior": "skin_picking", "where": "reddit.com", "daypart": "night", "multiplier": 3.0},
    {"behavior": "nail_biting", "where": "Code", "streak_min": 45, "multiplier": 3.5},
]
NULL_BEHAVIOR = "eye_rubbing"

TRUE_ARM_SUCCESS = {
    "habit": {"walk": 0.55, "fidget": 0.70, "switch_task": 0.45, "water": 0.40,
              "breathe": 0.35, "stretch": 0.50, "hands_busy": 0.65},
    "doomscroll": {"walk": 0.60, "switch_task": 0.50, "water": 0.30, "breathe": 0.25,
                   "stretch": 0.35, "close_tab": 0.45},
}

DEFAULT_SUCCESS = 0.45   # for swaps you add in config.py that aren't listed above


def true_success(trigger, arm):
    return TRUE_ARM_SUCCESS.get(trigger, {}).get(arm, DEFAULT_SUCCESS)


APPS = {
    "Code": ("coding", None), "Terminal": ("coding", None), "Slack": ("chat", None),
    "Discord": ("chat", None), "Spotify": ("music", None),
}
SITES = {"reddit.com": "social", "youtube.com": "video", "x.com": "social",
         "github.com": "coding", "stackoverflow.com": "coding", "docs.google.com": "docs"}


def multiplier(behavior, where, hour, streak_minutes):
    m = 1.0
    for p in PLANTED:
        if p["behavior"] != behavior or p["where"] != where:
            continue
        if p.get("daypart") == "night" and (hour >= 23 or hour < 5):
            m *= p["multiplier"]
        if "streak_min" in p and streak_minutes is not None and streak_minutes >= p["streak_min"]:
            m *= p["multiplier"]
    return m


class Builder:
    def __init__(self, rng):
        self.rng = rng
        self.segments = []     # (start, end, app, domain, category)

    def add(self, t, minutes, where):
        if where in SITES:
            app, domain, cat = "Google Chrome", where, SITES[where]
        else:
            app, domain, cat = where, None, APPS[where][0]
        end = t + minutes * 60
        self.segments.append((t, end, app, domain, cat))
        return end

    def coding_block(self, t, minutes):
        # a long VS Code session with short trips to Slack / GitHub / StackOverflow
        end_block = t + minutes * 60
        while t < end_block:
            stretch = min(self.rng.uniform(8, 25), (end_block - t) / 60)
            t = self.add(t, stretch, "Code")
            if t >= end_block:
                break
            t = self.add(t, self.rng.uniform(0.3, 1.5),
                         self.rng.choice(["Slack", "github.com", "stackoverflow.com", "Terminal"]))
        return t

    def leisure_block(self, t, minutes, night=False):
        end_block = t + minutes * 60
        while t < end_block:
            if night:
                where = self.rng.choices(["reddit.com", "youtube.com", "Discord", "x.com"], [5, 3, 1, 1])[0]
            else:
                where = self.rng.choices(["reddit.com", "youtube.com", "Discord", "x.com", "Spotify"],
                                         [3, 4, 2, 1, 1])[0]
            t = self.add(t, min(self.rng.uniform(3, 25), max((end_block - t) / 60, 0.5)), where)
        return t


def build_day(rng, day_start):
    # day_start: local midnight. returns segments and webcam sessions for the day
    b = Builder(rng)
    sessions = []
    weekend = time.localtime(day_start).tm_wday >= 5

    def block(start_hour, minutes, kind):
        t0 = day_start + start_hour * 3600 + rng.uniform(-15, 15) * 60
        if sessions:
            t0 = max(t0, sessions[-1][1] + 5 * 60)    # blocks never overlap
        if kind == "code":
            t1 = b.coding_block(t0, minutes)
        elif kind == "docs":
            t1 = b.add(t0, minutes, "docs.google.com")
        else:
            t1 = b.leisure_block(t0, minutes, night=(kind == "night"))
        sessions.append((t0, t1))

    if not weekend:
        block(9.5, rng.uniform(90, 160), "code")
        block(13, rng.uniform(30, 60), "leisure")
        block(14.2, rng.uniform(70, 150), "code")
        if rng.random() < 0.5:
            block(17.5, rng.uniform(30, 60), "docs")
    else:
        block(11, rng.uniform(60, 120), "leisure")
        if rng.random() < 0.6:
            block(14, rng.uniform(40, 100), "code")
    block(20, rng.uniform(60, 120), "leisure")
    if rng.random() < 0.6:
        block(23.2, rng.uniform(40, 110), "night")
    return b.segments, sessions


def streak_minutes_at(segments, idx, t):
    # minutes into the current VS Code session (ignoring short trips elsewhere)
    app = segments[idx][2]
    start = segments[idx][0]
    j = idx - 1
    while j >= 0:
        s, e, a = segments[j][0], segments[j][1], segments[j][2]
        if a == app and start - e <= config.STREAK_GAP_SECONDS:
            start = s
        elif e - s > config.STREAK_GAP_SECONDS or start - e > config.STREAK_GAP_SECONDS:
            break
        j -= 1
    return (t - start) / 60


def poisson_times(rng, s, e, rate_per_hour):
    out = []
    t = s
    while True:
        t += rng.expovariate(rate_per_hour / 3600) if rate_per_hour > 0 else math.inf
        if t >= e:
            return out
        out.append(t)


def simulate_nudges(conn, rng, alerts_ts, doom_ts):
    # alerts_ts: [(ts, behavior, region)], doom_ts: [(ts, site)]
    from backend import bandit
    policy = bandit.Bandit(seed=rng.randrange(1 << 30))
    events = [(t, "habit", "habit:" + b, region) for t, b, region in alerts_ts]
    events += [(t, "doomscroll", "doomscroll", site) for t, site in doom_ts]
    for ts, trigger, context, detail in sorted(events):
        arm, pol = policy.choose(trigger, context)
        success = rng.random() < true_success(trigger, arm)
        status = "success" if success else "failure"
        conn.execute("INSERT INTO nudges (ts, trigger, context, detail, arm, policy, status, resolved_at) "
                     "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                     (ts, trigger, context, detail, arm, pol, status, ts + config.NUDGE_OUTCOME_MINUTES * 60))
        policy.update(context, arm, success)
    conn.commit()


def generate(path, days=28, seed=7, end=None, nudges=True):
    if os.path.exists(path):
        os.remove(path)
    rng = random.Random(seed)
    conn = db.connect(path)
    end = end or time.time()
    lt = time.localtime(end)
    today = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
    alerts_ts, doom_ts = [], []
    last_doom = 0
    for d in range(days, 0, -1):
        day_start = time.mktime(time.localtime(today - d * 86400 + 3 * 3600)[:3] + (0, 0, 0, 0, 0, -1))
        segments, sessions = build_day(rng, day_start)
        for s, e in sessions:
            for kind in ("webcam", "activity"):
                conn.execute("INSERT INTO sessions (source, start, end, last_seen) VALUES (?, ?, ?, ?)",
                             (kind, s, e, e))
        for i, (s, e, app, domain, cat) in enumerate(segments):
            conn.execute("INSERT INTO activity (start, end, app, domain, category, idle) VALUES (?, ?, ?, ?, ?, 0)",
                         (s, e, app, domain, cat))
            where = domain or app
            # cut into 1-minute steps so the rate can change with the hour and the streak
            t = s
            while t < e:
                nxt = min(t + 60, e)
                hour = time.localtime(t).tm_hour
                streak = streak_minutes_at(segments, i, t) if app == "Code" else None
                for behavior, base in BASE_RATES.items():
                    rate = base * multiplier(behavior, where, hour, streak)
                    for ts in poisson_times(rng, t, nxt, rate):
                        dur = rng.uniform(1.0, 12.0)
                        region = {"skin_picking": rng.choice(["cheek_chin", "forehead", "nose"]),
                                  "nail_biting": "mouth", "eye_rubbing": "eyes"}[behavior]
                        conn.execute("INSERT INTO touch_events (start, end, region, behavior, alerted, duration) "
                                     "VALUES (?, ?, ?, ?, 1, ?)", (ts, ts + dur, region, behavior, dur))
                        conn.execute("INSERT INTO alerts (ts, region, behavior) VALUES (?, ?, ?)",
                                     (ts + 1.0, region, behavior))
                        alerts_ts.append((ts + 1.0, behavior, region))
                t = nxt
            if cat in config.DOOMSCROLL_CATEGORIES and e - s >= config.DOOMSCROLL_MINUTES * 60 \
                    and s - last_doom > config.NUDGE_COOLDOWN_MINUTES * 60:
                doom_ts.append((s + config.DOOMSCROLL_MINUTES * 60, where))
                last_doom = s
        # a little harmless contact too (logged, not alerted)
        for s, e in sessions:
            for ts in poisson_times(rng, s, e, 1.5):
                conn.execute("INSERT INTO touch_events (start, end, region, behavior, alerted, duration) "
                             "VALUES (?, ?, 'cheek_chin', 'benign', 0, 3.0)", (ts, ts + 3.0))
    conn.commit()
    if nudges:
        # space the habit nudges out like the real cooldown would
        kept, last = [], 0
        for ts, b, region in sorted(alerts_ts):
            if ts - last >= config.NUDGE_COOLDOWN_MINUTES * 60:
                kept.append((ts, b, region))
                last = ts
        simulate_nudges(conn, rng, kept, doom_ts)
    conn.close()
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data_demo/habits.db")
    parser.add_argument("--days", type=int, default=28)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    generate(args.out, args.days, args.seed)
    print("wrote", args.out)


if __name__ == "__main__":
    main()
