import random

import config
from backend import bandit, db, nudges


def setup(path, start=0, end=10_000):
    conn = db.connect(path)
    for source in ("webcam", "activity"):
        conn.execute("INSERT INTO sessions (source, start, end, last_seen) VALUES (?, ?, ?, ?)",
                     (source, start, end, end))
    conn.commit()
    return conn


def engine(path):
    sent = []
    e = nudges.NudgeEngine(path, notify=lambda title, text: sent.append(text), seed=1)
    return e, sent


def test_alert_triggers_one_nudge_with_cooldown(empty_db):
    conn = setup(empty_db)
    e, sent = engine(empty_db)
    e.step(conn, 1000)                     # remembers where the alerts table is
    db.log_alert(conn, 1, 1000, "cheek_chin", "skin_picking")
    e.step(conn, 1001)
    db.log_alert(conn, 1, 1100, "cheek_chin", "skin_picking")
    e.step(conn, 1101)                     # inside the cooldown
    rows = db.rows(conn, "SELECT * FROM nudges")
    assert len(rows) == 1 and len(sent) == 1
    assert rows[0]["context"] == "habit:skin_picking" and rows[0]["status"] == "pending"


def test_habit_outcomes(empty_db):
    conn = setup(empty_db)
    for ts in (1000, 3000):
        conn.execute("INSERT INTO nudges (ts, trigger, context, arm, policy, status) "
                     "VALUES (?, 'habit', 'habit:skin_picking', 'walk', 'bandit', 'pending')", (ts,))
    conn.commit()
    db.log_touch(conn, 1, 1000 + 120, 1000 + 125, "cheek_chin", "skin_picking", True)   # came back: failure
    db.log_touch(conn, 1, 3000 + 10, 3000 + 20, "cheek_chin", "skin_picking", True)     # stopped in time: success
    e, _ = engine(empty_db)
    e.step(conn, 5000)
    status = [r["status"] for r in db.rows(conn, "SELECT status FROM nudges ORDER BY ts")]
    assert status == ["failure", "success"]


def test_unknown_when_tracker_was_off(empty_db):
    conn = setup(empty_db, 0, 1100)       # webcam stopped right after the nudge
    conn.execute("INSERT INTO nudges (ts, trigger, context, arm, policy, status) "
                 "VALUES (1000, 'habit', 'habit:any', 'walk', 'bandit', 'pending')")
    conn.commit()
    e, _ = engine(empty_db)
    e.step(conn, 5000)
    assert db.rows(conn, "SELECT status FROM nudges")[0]["status"] == "unknown"


def test_doomscroll_trigger_and_outcome(empty_db):
    conn = setup(empty_db, 0, 20_000)
    start = 1000
    now = start + config.DOOMSCROLL_MINUTES * 60 + 5
    db.open_activity(conn, 1, start, "Google Chrome", "reddit.com", None, "social", False)
    conn.execute("UPDATE activity SET end = ?", (now,))
    conn.commit()
    e, sent = engine(empty_db)
    e.step(conn, now)
    rows = db.rows(conn, "SELECT * FROM nudges")
    assert len(rows) == 1 and rows[0]["trigger"] == "doomscroll" and rows[0]["detail"] == "reddit.com"
    # user switches to VS Code right away: success
    db.open_activity(conn, 1, now + 1, "Code", None, None, "coding", False)
    conn.execute("UPDATE activity SET end = ? WHERE app = 'Code'", (now + 3600,))
    conn.commit()
    e.step(conn, now + 3600)
    assert db.rows(conn, "SELECT status FROM nudges")[0]["status"] == "success"


def test_bandit_learns_the_best_arm():
    rng = random.Random(0)
    truth = {arm: 0.2 for arm in config.NUDGE_ARMS_BY_TRIGGER["habit"]}
    truth["fidget"] = 0.8
    b = bandit.Bandit(seed=3, random_fraction=0.2)
    picks = []
    for _ in range(400):
        arm, who = b.choose("habit", "habit:any")
        b.update("habit:any", arm, rng.random() < truth[arm])
        if who == "bandit":
            picks.append(arm)
    assert picks[-100:].count("fidget") > 80
    assert b.summary("habit:any")[0]["arm"] == "fidget"


def test_random_group_share():
    b = bandit.Bandit(seed=1, random_fraction=0.2)
    share = sum(b.choose("habit", "habit:any")[1] == "random" for _ in range(5000)) / 5000
    assert 0.18 < share < 0.22


def test_prior_borrows_from_other_contexts():
    b = bandit.Bandit(seed=1)
    for _ in range(20):
        b.update("habit:nail_biting", "fidget", True)
    a, beta = b.posterior("habit:skin_picking", "fidget")
    assert a / (a + beta) > 0.7          # leans toward what worked elsewhere...
    assert a + beta <= 2 + bandit.PRIOR_STRENGTH + 1e-9   # ...but only a few pseudo-observations


def test_fisher_and_wilson():
    assert abs(bandit.fisher_exact(1, 9, 11, 3) - 0.002759) < 1e-4    # textbook tea-tasting style table
    lo, hi = bandit.wilson(50, 100)
    assert abs(lo - 0.404) < 0.01 and abs(hi - 0.596) < 0.01
