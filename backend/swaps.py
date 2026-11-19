# Your personal list of swaps (the suggestions a nudge can make).
#
# The swaps in config.py are only the starting set: the first time the database is used they are
# copied into the `swaps` table, and from then on you change them from the dashboard (Nudges page)
# or by asking Pip. A swap is never deleted, only switched off, so its history stays with it and the
# bandit remembers what it learned if you switch it back on.
#
# Each swap has a short key (what the bandit tracks), the text shown in the notification, and
# whether it can be suggested after a habit alert, after doomscrolling, or both.

import re
import time

import config
from backend import db

TRIGGERS = ("habit", "doomscroll")
MIN_TRIES_FOR_ADVICE = 8      # Pip only suggests changes once a swap has been tried this often
ADVICE_GAP = 0.3              # ...and works this much less often than your best swap

SCHEMA = """
CREATE TABLE IF NOT EXISTS swaps (
    key TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    habit INTEGER NOT NULL DEFAULT 1,       -- can be suggested after a habit alert
    doomscroll INTEGER NOT NULL DEFAULT 0,  -- can be suggested after doomscrolling
    active INTEGER NOT NULL DEFAULT 1,      -- switched off swaps are never suggested
    position INTEGER NOT NULL DEFAULT 0,
    added_by TEXT NOT NULL DEFAULT 'default',
    created REAL NOT NULL
);
"""


def ensure(conn):
    # create the table and copy in the defaults from config.py the first time
    conn.executescript(SCHEMA)
    if conn.execute("SELECT COUNT(*) FROM swaps").fetchone()[0] == 0:
        now = time.time()
        # every swap in NUDGE_ARMS, plus any listed for a trigger but missing from NUDGE_ARMS
        # (its text is made from its name, e.g. hands_busy -> "Hands busy")
        defaults = dict(config.NUDGE_ARMS)
        for keys in config.NUDGE_ARMS_BY_TRIGGER.values():
            for key in keys:
                defaults.setdefault(key, key.replace("_", " ").capitalize())
        for i, (key, text) in enumerate(defaults.items()):
            conn.execute(
                "INSERT INTO swaps (key, text, habit, doomscroll, active, position, added_by, created) "
                "VALUES (?, ?, ?, ?, 1, ?, 'default', ?)",
                (key, text, int(key in config.NUDGE_ARMS_BY_TRIGGER.get("habit", [])),
                 int(key in config.NUDGE_ARMS_BY_TRIGGER.get("doomscroll", [])), i, now))
        conn.commit()


def all_swaps(conn):
    ensure(conn)
    return db.rows(conn, "SELECT key, text, habit, doomscroll, active, added_by FROM swaps ORDER BY position, created")


def arms_for(conn, trigger):
    # the swaps that can be suggested for this trigger right now
    ensure(conn)
    col = "habit" if trigger == "habit" else "doomscroll"
    return [r["key"] for r in conn.execute(
        "SELECT key FROM swaps WHERE active = 1 AND " + col + " = 1 ORDER BY position, created")]


def text_for(conn, key):
    ensure(conn)
    r = conn.execute("SELECT text FROM swaps WHERE key = ?", (key,)).fetchone()
    return r["text"] if r else config.NUDGE_ARMS.get(key, key.replace("_", " "))


def texts(conn):
    ensure(conn)
    return {r["key"]: r["text"] for r in conn.execute("SELECT key, text FROM swaps")}


def find(conn, name):
    # look a swap up by its key or (loosely) by its words, e.g. "walk" or "the stress ball one"
    ensure(conn)
    name = (name or "").strip().lower()
    if not name:
        return None
    rows = all_swaps(conn)
    for r in rows:
        if r["key"] == name or r["key"].replace("_", " ") == name or r["text"].lower() == name:
            return r
    words = stems(name) - {"the", "a", "an", "one", "swap", "my", "to", "and", "or", "for", "of"}
    best, score = None, 0
    for r in rows:
        hay = stems(r["key"].replace("_", " ") + " " + r["text"])
        s = len(words & hay)
        if s > score:
            best, score = r, s
    return best


def stems(text):
    # rough word stems so "walking", "walks" and "walk" match
    out = set()
    for w in re.findall(r"[a-z]+", text.lower()):
        if w.endswith("ing") and len(w) > 5:
            w = w[:-3]
        elif w.endswith("s") and len(w) > 3 and not w.endswith("ss"):
            w = w[:-1]
        out.add(w)
    return out


def make_key(conn, text):
    base = "_".join(re.findall(r"[a-z0-9]+", text.lower())[:3]) or "swap"
    key, n = base, 2
    while conn.execute("SELECT 1 FROM swaps WHERE key = ?", (key,)).fetchone():
        key, n = base + "_" + str(n), n + 1
    return key


def add(conn, text, habit=True, doomscroll=False, added_by="you"):
    ensure(conn)
    text = text.strip()
    if not text:
        raise ValueError("a swap needs some text")
    existing = find(conn, text)
    if existing and existing["text"].lower() == text.lower():
        update(conn, existing["key"], active=True, habit=habit or existing["habit"],
               doomscroll=doomscroll or existing["doomscroll"])
        return existing["key"]
    key = make_key(conn, text)
    pos = conn.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM swaps").fetchone()[0]
    conn.execute("INSERT INTO swaps (key, text, habit, doomscroll, active, position, added_by, created) "
                 "VALUES (?, ?, ?, ?, 1, ?, ?, ?)", (key, text, int(habit), int(doomscroll), pos, added_by, time.time()))
    conn.commit()
    return key


def update(conn, key, text=None, habit=None, doomscroll=None, active=None):
    ensure(conn)
    if not conn.execute("SELECT 1 FROM swaps WHERE key = ?", (key,)).fetchone():
        raise KeyError(key)
    sets, params = [], []
    for col, val in (("text", text), ("habit", habit), ("doomscroll", doomscroll), ("active", active)):
        if val is not None:
            sets.append(col + " = ?")
            params.append(val.strip() if col == "text" else int(bool(val)))
    if sets:
        conn.execute("UPDATE swaps SET " + ", ".join(sets) + " WHERE key = ?", (*params, key))
        conn.commit()


def results(conn):
    # how often each swap worked, over all triggers: key -> (worked, tried)
    out = {}
    for r in conn.execute("SELECT arm, SUM(status = 'success') AS ok, COUNT(*) AS n FROM nudges "
                          "WHERE status IN ('success', 'failure') GROUP BY arm"):
        out[r["arm"]] = (r["ok"], r["n"])
    return out


def advice(conn):
    # data-based suggestions: pause a swap that clearly works less often than your best one.
    # Only once there are enough tries, so one bad afternoon doesn't get a swap switched off.
    res = results(conn)
    tips = []
    for trigger in TRIGGERS:
        arms = [a for a in arms_for(conn, trigger) if res.get(a, (0, 0))[1] >= MIN_TRIES_FOR_ADVICE]
        if len(arms) < 2:
            continue
        rate = {a: res[a][0] / res[a][1] for a in arms}
        best = max(arms, key=rate.get)
        for a in arms:
            if a != best and rate[best] - rate[a] >= ADVICE_GAP and not any(t["key"] == a for t in tips):
                tips.append({
                    "key": a, "action": "pause", "trigger": trigger,
                    "text": text_for(conn, a), "worked": res[a][0], "tried": res[a][1],
                    "best_key": best, "best_text": text_for(conn, best), "best_worked": res[best][0], "best_tried": res[best][1],
                    "gap": round(rate[best] - rate[a], 3),
                    "message": ("\u201c" + text_for(conn, a) + "\u201d has worked " + str(res[a][0]) + " of " + str(res[a][1])
                                + " times for you, while \u201c" + text_for(conn, best) + "\u201d has worked "
                                + str(res[best][0]) + " of " + str(res[best][1]) + ". Want to pause it?"),
                })
    return sorted(tips, key=lambda t: -t["gap"])    # the clearest case first


def listing(conn):
    # everything the Nudges page and Pip need about your swaps
    res = results(conn)
    rows = []
    for r in all_swaps(conn):
        worked, tried = res.get(r["key"], (0, 0))
        rows.append(dict(r, habit=bool(r["habit"]), doomscroll=bool(r["doomscroll"]), active=bool(r["active"]),
                         worked=worked, tried=tried, rate=round(worked / tried, 3) if tried else None))
    return {"swaps": rows, "advice": advice(conn)}


# ---- proposals from Pip: checked here, applied only when you press "Yes" ----

def propose(conn, action, swap=None, text=None, when=None):
    ensure(conn)
    action = (action or "").lower()
    when = (when or "").lower() or None
    triggers = {"habit": (True, False), "doomscroll": (False, True), "both": (True, True)}
    if action not in ("add", "remove", "pause", "resume", "reword", "change_when"):
        return {"error": "action must be add, remove, pause, resume, reword or change_when"}
    if when and when not in triggers:
        return {"error": "when must be habit, doomscroll or both"}
    if action == "add":
        if not (text or swap):
            return {"error": "say what the new swap is"}
        new = (text or swap).strip().rstrip(".")
        new = new[0].upper() + new[1:]
        habit, doom = triggers[when or "habit"]
        existing = find(conn, new)
        if existing and existing["text"].lower() == new.lower():
            if existing["active"]:
                return {"note": "you already have this swap", "swap": existing}
            return {"proposal": {"action": "resume", "key": existing["key"], "text": existing["text"]},
                    "summary": "Switch \"" + existing["text"] + "\" back on"}
        where = {"habit": "after habit alerts", "doomscroll": "after doomscrolling", "both": "after habit alerts and doomscrolling"}[when or "habit"]
        return {"proposal": {"action": "add", "text": new, "habit": habit, "doomscroll": doom},
                "summary": "Add \"" + new + "\" " + where}
    found = find(conn, swap or "")
    if not found:
        return {"error": "no swap matches \"" + str(swap) + "\"", "your_swaps": [r["text"] for r in all_swaps(conn)]}
    key, cur = found["key"], found["text"]
    if action in ("remove", "pause"):
        return {"proposal": {"action": "pause", "key": key, "text": cur},
                "summary": "Stop suggesting \"" + cur + "\" (you can switch it back on any time)"}
    if action == "resume":
        return {"proposal": {"action": "resume", "key": key, "text": cur}, "summary": "Start suggesting \"" + cur + "\" again"}
    if action == "reword":
        if not text:
            return {"error": "say what the new wording should be"}
        return {"proposal": {"action": "reword", "key": key, "text": text.strip(), "old_text": cur},
                "summary": "Change \"" + cur + "\" to \"" + text.strip() + "\""}
    habit, doom = triggers[when or "both"]
    where = {"habit": "only after habit alerts", "doomscroll": "only after doomscrolling", "both": "after habit alerts and doomscrolling"}[when or "both"]
    return {"proposal": {"action": "change_when", "key": key, "text": cur, "habit": habit, "doomscroll": doom},
            "summary": "Suggest \"" + cur + "\" " + where}


def apply(conn, proposal):
    # carries out a proposal the user confirmed
    a = proposal.get("action")
    if a == "add":
        key = add(conn, proposal["text"], proposal.get("habit", True), proposal.get("doomscroll", False))
    elif a == "pause":
        key = proposal["key"]; update(conn, key, active=False)
    elif a == "resume":
        key = proposal["key"]; update(conn, key, active=True)
    elif a == "reword":
        key = proposal["key"]; update(conn, key, text=proposal["text"])
    elif a == "change_when":
        key = proposal["key"]; update(conn, key, habit=proposal["habit"], doomscroll=proposal["doomscroll"], active=True)
    else:
        raise ValueError("unknown action " + str(a))
    return key

