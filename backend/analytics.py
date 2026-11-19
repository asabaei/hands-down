# Joins the two signals (webcam habit events and the active window) and computes rates.
#
# The key idea is exposure: "12 skin-picking events on Reddit" means nothing until you know
# how long you were on Reddit while the webcam was watching. Every rate here is
# events per hour of observed time, and every comparison is against the rest of the observed
# time, with a confidence interval and an exact test. The LLM never does this arithmetic itself;
# it calls these functions through tools and explains the results.
#
# Observed time is split into small pieces that each have one context:
#   category   social, video, coding, chat, ...       (from the activity tracker)
#   where      the site for browsers, otherwise the app (reddit.com, Code, Discord)
#   hour       local hour of day, 0-23
#   daypart    night (23-5), morning (5-12), afternoon (12-17), evening (17-23)
#   daytype    weekday / weekend
#   streak     minutes into the current continuous session in that app: 0-15, 15-45, 45-90, 90+
# Time when the webcam ran but the activity tracker didn't is kept as category "untracked".

import math
import time
from collections import defaultdict

import config
from backend import db

DIMENSIONS = ["category", "where", "hour", "daypart", "daytype", "streak"]
PAIRS = [("category", "daypart"), ("where", "daypart"), ("category", "streak"),
         ("where", "streak"), ("category", "daytype"), ("where", "daytype")]
HABITS = list(config.HABIT_LABELS)


def daypart(hour):
    if hour >= 23 or hour < 5:
        return "night (23-5)"
    if hour < 12:
        return "morning (5-12)"
    if hour < 17:
        return "afternoon (12-17)"
    return "evening (17-23)"


def streak_label(minutes):
    edges = config.STREAK_BUCKETS_MIN
    for i in range(len(edges) - 1, -1, -1):
        if minutes >= edges[i]:
            if i == len(edges) - 1:
                return str(edges[i]) + "+ min"
            return str(edges[i]) + "-" + str(edges[i + 1]) + " min"
    return str(edges[0]) + "-" + str(edges[1]) + " min"


def next_hour_boundary(t):
    lt = time.localtime(t)
    start_of_hour = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, lt.tm_hour, 0, 0, 0, 0, -1))
    nxt = start_of_hour + 3600
    return nxt if nxt > t else t + 3600


def fmt_local(t):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(t))


# ---- statistics ----

def log_binom_pmf(k, n, p):
    if p <= 0:
        return 0.0 if k == 0 else -math.inf
    if p >= 1:
        return 0.0 if k == n else -math.inf
    return (math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
            + k * math.log(p) + (n - k) * math.log(1 - p))


def binom_two_sided(k, n, p):
    # exact two-sided binomial test (sum of outcomes at most as likely as the observed one)
    if n == 0:
        return 1.0
    observed = log_binom_pmf(k, n, p)
    total = 0.0
    for i in range(n + 1):
        lp = log_binom_pmf(i, n, p)
        if lp <= observed + 1e-9:
            total += math.exp(lp)
    return min(1.0, total)


def rate_ratio(n_a, hours_a, n_b, hours_b):
    # rate ratio a vs b with a 95% CI on the log scale (0.5 added to counts so zeros work)
    if hours_a <= 0 or hours_b <= 0:
        return None, None, None
    ra = (n_a + 0.5) / hours_a
    rb = (n_b + 0.5) / hours_b
    ratio = ra / rb
    se = math.sqrt(1 / (n_a + 0.5) + 1 / (n_b + 0.5))
    return ratio, ratio * math.exp(-1.96 * se), ratio * math.exp(1.96 * se)


def benjamini_hochberg(pvalues):
    # adjusted p-values (q-values), same order as the input
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    q = [0.0] * m
    running = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        running = min(running, pvalues[i] * m / rank)
        q[i] = running
    return q


# ---- building observed pieces ----

class Data:
    # everything needed for one time range, already split into context pieces

    def __init__(self, conn, start, end):
        self.start, self.end = start, end
        self.webcam = db.coverage(conn, "webcam", start, end)
        self.activity = db.rows(
            conn, "SELECT start, end, app, domain, category, idle FROM activity "
                  "WHERE end >= ? AND start <= ? ORDER BY start", (start, end))
        self.events = db.rows(
            conn, "SELECT start, end, region, behavior, alerted, duration FROM touch_events "
                  "WHERE start >= ? AND start <= ? ORDER BY start", (start, end))
        self.pieces = self.build_pieces()
        self.tag_events()

    def streaks(self):
        # continuous sessions in one app (short visits elsewhere don't break them)
        out = []   # (app, start, end)
        for seg in self.activity:
            if seg["idle"]:
                continue
            if out and out[-1][0] == seg["app"] and seg["start"] - out[-1][2] <= config.STREAK_GAP_SECONDS:
                out[-1] = (out[-1][0], out[-1][1], max(out[-1][2], seg["end"]))
            else:
                # a short visit to another app inside a long session: look back one streak
                if (len(out) >= 2 and out[-2][0] == seg["app"]
                        and seg["start"] - out[-2][2] <= config.STREAK_GAP_SECONDS
                        and out[-1][2] - out[-1][1] <= config.STREAK_GAP_SECONDS):
                    out.pop()
                    out[-1] = (out[-1][0], out[-1][1], max(out[-1][2], seg["end"]))
                    continue
                out.append((seg["app"], seg["start"], seg["end"]))
        return out

    def streak_start_for(self, streaks, app, t):
        for s_app, s, e in streaks:
            if s_app == app and s <= t <= e + 1e-6:
                return s
        return t

    def build_pieces(self):
        streaks = self.streaks()
        segments = []    # (start, end, attrs)
        for seg in self.activity:
            attrs = {"category": seg["category"] or "other",
                     "where": seg["domain"] or seg["app"] or "unknown",
                     "app": seg["app"]}
            if seg["idle"]:
                attrs = {"category": "idle", "where": "idle", "app": seg["app"]}
            segments.append((seg["start"], seg["end"], attrs, seg["idle"]))

        pieces = []
        for c_start, c_end in self.webcam:
            cursor = c_start
            for s, e, attrs, idle in segments:
                if e <= c_start or s >= c_end:
                    continue
                s2, e2 = max(s, c_start, cursor), min(e, c_end)   # overlapping rows count once
                if s2 > cursor:
                    pieces += self.split(cursor, s2, {"category": "untracked", "where": "untracked"}, None)
                if e2 > s2:
                    streak_start = None if idle else self.streak_start_for(streaks, attrs["app"], s2)
                    pieces += self.split(s2, e2, attrs, streak_start)
                cursor = max(cursor, e2)
            if c_end > cursor:
                pieces += self.split(cursor, c_end, {"category": "untracked", "where": "untracked"}, None)
        return pieces

    def split(self, s, e, attrs, streak_start):
        # cut [s, e) at local hour boundaries and streak bucket edges
        cuts = set()
        t = next_hour_boundary(s)
        while t < e:
            cuts.add(t)
            t = next_hour_boundary(t)
        if streak_start is not None:
            for m in config.STREAK_BUCKETS_MIN[1:]:
                edge = streak_start + m * 60
                if s < edge < e:
                    cuts.add(edge)
        points = [s] + sorted(cuts) + [e]
        out = []
        for a, b in zip(points, points[1:]):
            if b - a <= 0:
                continue
            out.append({"start": a, "end": b, "seconds": b - a, **self.context(a, attrs, streak_start)})
        return out

    def context(self, t, attrs, streak_start):
        lt = time.localtime(t)
        ctx = {"category": attrs["category"], "where": attrs["where"], "hour": lt.tm_hour,
               "daypart": daypart(lt.tm_hour), "daytype": "weekend" if lt.tm_wday >= 5 else "weekday"}
        if streak_start is None:
            ctx["streak"] = "n/a"
        else:
            ctx["streak"] = streak_label((t - streak_start) / 60 + 1e-6)
        return ctx

    def tag_events(self):
        # attach the context that was active when each touch started
        i = 0
        pieces = self.pieces
        for ev in self.events:
            ev["context"] = None
            while i < len(pieces) and pieces[i]["end"] <= ev["start"]:
                i += 1
            if i < len(pieces) and pieces[i]["start"] <= ev["start"] < pieces[i]["end"]:
                ev["context"] = pieces[i]

    def habit_events(self, behavior="any"):
        # habit touches that happened while the webcam was watching
        out = []
        for ev in self.events:
            if ev["context"] is None:
                continue
            if behavior in (None, "any"):
                is_habit = ev["behavior"] in HABITS or (ev["behavior"] == "unclassified" and ev["alerted"])
            else:
                is_habit = ev["behavior"] == behavior
            if is_habit:
                out.append(ev)
        return out


def key_of(ctx, dims):
    return " & ".join(d + "=" + str(ctx[d]) for d in dims)


class Analytics:
    def __init__(self, conn, now=None):
        self.conn = conn
        self.now_override = now

    def now(self):
        return self.now_override or time.time()

    def latest_time(self):
        r = self.conn.execute(
            "SELECT MAX(t) AS t FROM (SELECT MAX(COALESCE(end, last_seen)) AS t FROM sessions "
            "UNION SELECT MAX(end) FROM activity)").fetchone()
        return r["t"]

    def data(self, days=None):
        end = self.now()
        start = end - days * 86400 if days else 0
        return Data(self.conn, start, end)

    # ---- tool functions (each returns plain JSON-able dicts) ----

    def overview(self, days=None):
        d = self.data(days)
        observed = sum(p["seconds"] for p in d.pieces) / 3600
        by_behavior = defaultdict(int)
        for ev in d.habit_events("any"):
            by_behavior[ev["behavior"]] += 1
        time_by_cat = defaultdict(float)
        for p in d.pieces:
            time_by_cat[p["category"]] += p["seconds"] / 3600
        all_activity = defaultdict(float)
        for seg in d.activity:
            if not seg["idle"]:
                all_activity[seg["domain"] or seg["app"]] += (min(seg["end"], d.end) - max(seg["start"], d.start)) / 3600
        habits = sum(by_behavior.values())
        return {
            "range": {"from": fmt_local(d.start) if d.start else "all time", "to": fmt_local(d.end)},
            "webcam_observed_hours": round(observed, 2),
            "habit_events": habits,
            "habit_events_per_observed_hour": round(habits / observed, 2) if observed else None,
            "habit_events_by_behavior": dict(by_behavior),
            "all_touches_logged": len(d.events),
            "observed_hours_by_category": {k: round(v, 2) for k, v in
                                           sorted(time_by_cat.items(), key=lambda x: -x[1])},
            "top_apps_and_sites_hours": {k: round(v, 2) for k, v in
                                         sorted(all_activity.items(), key=lambda x: -x[1])[:10]},
        }

    def rates(self, d, dims, behavior="any", min_minutes=0):
        exposure = defaultdict(float)
        for p in d.pieces:
            exposure[key_of(p, dims)] += p["seconds"] / 3600
        counts = defaultdict(int)
        for ev in d.habit_events(behavior):
            counts[key_of(ev["context"], dims)] += 1
        total_n = sum(counts.values())
        total_h = sum(exposure.values())
        rows = []
        for key, hours in exposure.items():
            if hours * 60 < min_minutes:
                continue
            n = counts.get(key, 0)
            ratio, lo, hi = rate_ratio(n, hours, total_n - n, total_h - hours)
            p = binom_two_sided(n, total_n, hours / total_h) if total_h > 0 else 1.0
            rows.append({"context": key, "events": n, "observed_hours": round(hours, 2),
                         "events_per_hour": round(n / hours, 2) if hours > 0 else None,
                         "rate_ratio_vs_rest": round(ratio, 2) if ratio else None,
                         "ci95": [round(lo, 2), round(hi, 2)] if ratio else None,
                         "p_value": round(p, 4)})
        return rows, total_n, total_h

    def habit_rates(self, group_by="category", behavior="any", days=None, min_minutes=None):
        dims = [group_by] if isinstance(group_by, str) else list(group_by)
        for dim in dims:
            if dim not in DIMENSIONS:
                return {"error": "group_by must be one of " + ", ".join(DIMENSIONS)}
        if behavior not in HABITS + ["any"]:
            return {"error": "behavior must be one of " + ", ".join(HABITS + ["any"])}
        d = self.data(days)
        min_minutes = config.MIN_EXPOSURE_MINUTES if min_minutes is None else min_minutes
        rows, n, h = self.rates(d, dims, behavior, min_minutes)
        rows.sort(key=lambda r: -(r["events_per_hour"] or 0))
        return {"behavior": behavior, "group_by": dims, "total_events": n,
                "total_observed_hours": round(h, 2),
                "overall_events_per_hour": round(n / h, 2) if h else None,
                "groups": rows,
                "note": "groups with less than " + str(min_minutes) + " observed minutes are left out"}

    def find_patterns(self, behavior="any", days=None, max_results=8):
        # tests every single context and every pair from PAIRS, keeps the ones that
        # survive a Benjamini-Hochberg correction, ranked by how strong they are
        if behavior not in HABITS + ["any"]:
            return {"error": "behavior must be one of " + ", ".join(HABITS + ["any"])}
        d = self.data(days)
        behaviors = [behavior] if behavior != "any" else ["any"] + HABITS
        candidates = []
        for b in behaviors:
            for dims in [[x] for x in DIMENSIONS if x != "hour"] + [list(p) for p in PAIRS]:
                rows, total_n, total_h = self.rates(d, dims, b, config.MIN_EXPOSURE_MINUTES)
                if total_n < config.MIN_PATTERN_EVENTS:
                    continue
                for r in rows:
                    if "untracked" in r["context"] or "=n/a" in r["context"]:
                        continue
                    expected = total_n * r["observed_hours"] / total_h
                    if max(r["events"], expected) < config.MIN_PATTERN_EVENTS:
                        continue
                    r = dict(r, behavior=b, expected_events=round(expected, 1))
                    candidates.append(r)
        if not candidates:
            return {"behavior": behavior, "tested": 0, "patterns": [],
                    "note": "not enough data yet (need at least " + str(config.MIN_PATTERN_EVENTS)
                            + " habit events and " + str(config.MIN_EXPOSURE_MINUTES) + " observed minutes per context)"}
        qs = benjamini_hochberg([c["p_value"] for c in candidates])
        found = []
        for c, q in zip(candidates, qs):
            if q <= config.PATTERN_FDR:
                c["q_value"] = round(q, 4)
                c["direction"] = "higher" if c["rate_ratio_vs_rest"] > 1 else "lower"
                found.append(c)
        # strongest first: how far the 95% interval is from "no difference"
        for c in found:
            lo, hi = c["ci95"]
            c["strength"] = round(math.log(lo) if c["direction"] == "higher" else -math.log(hi), 3)
        found.sort(key=lambda c: -c["strength"])
        kept = []
        for c in found:
            if any(self.redundant(c, k) for k in kept):
                continue
            kept.append(c)
        return {"behavior": behavior, "tested": len(candidates),
                "false_discovery_rate": config.PATTERN_FDR,
                "patterns": kept[:max_results],
                "note": "rate_ratio_vs_rest compares the events per observed hour in this context "
                        "with all other observed time. These are associations, not causes."}

    @staticmethod
    def redundant(c, k):
        # same behavior and practically the same slice of time (e.g. where=Code and
        # category=coding), or a pair that is no stronger than a pattern already kept
        if c["behavior"] != k["behavior"]:
            return False
        same_slice = (abs(c["observed_hours"] - k["observed_hours"]) <= 0.1 * k["observed_hours"]
                      and abs(c["events"] - k["events"]) <= max(2, 0.1 * k["events"]))
        parts_c, parts_k = set(c["context"].split(" & ")), set(k["context"].split(" & "))
        return same_slice or (parts_k < parts_c and c["strength"] <= k["strength"])

    def trend(self, behavior="any", period="day", days=14):
        d = self.data(days)
        fmt = "%Y-%m-%d" if period == "day" else "%G-W%V"
        hours = defaultdict(float)
        counts = defaultdict(int)
        for p in d.pieces:
            hours[time.strftime(fmt, time.localtime(p["start"]))] += p["seconds"] / 3600
        for ev in d.habit_events(behavior):
            counts[time.strftime(fmt, time.localtime(ev["start"]))] += 1
        rows = [{"period": k, "events": counts.get(k, 0), "observed_hours": round(h, 2),
                 "events_per_hour": round(counts.get(k, 0) / h, 2) if h > 0 else None}
                for k, h in sorted(hours.items())]
        return {"behavior": behavior, "period": period, "rows": rows}

    def list_events(self, behavior="any", days=1, where=None, limit=20):
        d = self.data(days)
        out = []
        for ev in d.habit_events(behavior):
            ctx = ev["context"]
            if where and where.lower() not in str(ctx["where"]).lower() and where.lower() != ctx["category"]:
                continue
            out.append({"time": fmt_local(ev["start"]), "behavior": ev["behavior"], "region": ev["region"],
                        "seconds": round(ev["duration"], 1), "category": ctx["category"],
                        "where": ctx["where"], "streak": ctx["streak"]})
        return {"count": len(out), "events": out[-limit:]}

    def app_usage(self, group_by="where", days=None, limit=15):
        # time in apps/sites from the activity tracker (whether or not the webcam was on)
        if group_by not in ("where", "category", "hour", "daypart"):
            return {"error": "group_by must be where, category, hour or daypart"}
        d = self.data(days)
        totals = defaultdict(float)
        for seg in d.activity:
            if seg["idle"]:
                continue
            s, e = max(seg["start"], d.start), min(seg["end"], d.end)
            if group_by == "where":
                totals[seg["domain"] or seg["app"]] += (e - s) / 3600
            elif group_by == "category":
                totals[seg["category"]] += (e - s) / 3600
            else:
                t = s
                while t < e:
                    nxt = min(next_hour_boundary(t), e)
                    h = time.localtime(t).tm_hour
                    totals[h if group_by == "hour" else daypart(h)] += (nxt - t) / 3600
                    t = nxt
        rows = sorted(totals.items(), key=lambda x: -x[1])[:limit]
        return {"group_by": group_by, "hours": {str(k): round(v, 2) for k, v in rows}}

    def progress(self):
        # numbers for the Today screen: today vs yesterday, this week vs last week, and "calm streaks"
        # (time the webcam was watching without a habit, so time away from the desk doesn't count)
        now = self.now()
        lt = time.localtime(now)
        today = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
        yesterday = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday - 1, 0, 0, 0, 0, 0, -1))
        d = Data(self.conn, now - 15 * 86400, now)
        habits = d.habit_events("any")
        watched = d.webcam

        def observed(s, e):
            return sum(max(0.0, min(b, e) - max(a, s)) for a, b in watched)

        def window(s, e):
            n = sum(1 for ev in habits if s <= ev["start"] < e)
            h = observed(s, e) / 3600
            return {"events": n, "observed_hours": round(h, 2), "per_hour": round(n / h, 2) if h > 0 else None}

        # "this week" = the last 7 calendar days including today; "last week" = the 7 days before
        week_start = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday - 6, 0, 0, 0, 0, 0, -1))
        prev_start = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday - 13, 0, 0, 0, 0, 0, -1))
        this_week, last_week = window(week_start, now), window(prev_start, week_start)
        change = None
        if this_week["per_hour"] is not None and last_week["per_hour"]:
            change = round(this_week["per_hour"] / last_week["per_hour"] - 1, 3)

        # calm stretches: observed time between one habit and the next
        marks = [ev for ev in habits if ev["start"] >= week_start]
        best, edge = 0.0, week_start
        for ev in marks:
            best = max(best, observed(edge, ev["start"]))
            edge = ev["end"]
        current = observed(edge if marks else week_start, now)
        best = max(best, current)

        days = []
        for i in range(6, -1, -1):
            s = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday - i, 0, 0, 0, 0, 0, -1))
            e = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday - i + 1, 0, 0, 0, 0, 0, -1))
            days.append(dict(window(s, min(e, now)), date=time.strftime("%Y-%m-%d", time.localtime(s))))

        last = habits[-1] if habits else None
        return {
            "now": now,
            "today": window(today, now),
            "yesterday": window(yesterday, today),
            "this_week": this_week,
            "last_week": last_week,
            "week_change": change,    # -0.2 = 20% fewer habits per watched hour than last week
            "calm_streak_minutes": round(current / 60, 1),
            "best_calm_minutes_this_week": round(best / 60, 1),
            "days": days,
            "last_habit": {"ts": last["start"], "behavior": last["behavior"]} if last else None,
        }

    def timeline(self, start, end):
        # raw rows for the dashboard's two-lane timeline
        acts = db.rows(self.conn, "SELECT start, end, app, domain, category, idle FROM activity "
                                  "WHERE end >= ? AND start <= ? ORDER BY start", (start, end))
        touches = db.rows(self.conn, "SELECT start, end, region, behavior, alerted FROM touch_events "
                                     "WHERE start >= ? AND start <= ? ORDER BY start", (start, end))
        nudges = db.rows(self.conn, "SELECT ts, trigger, arm, policy, status FROM nudges "
                                    "WHERE ts >= ? AND ts <= ? ORDER BY ts", (start, end))
        return {"start": start, "end": end, "activity": acts, "touches": touches, "nudges": nudges,
                "webcam": db.coverage(self.conn, "webcam", start, end)}
