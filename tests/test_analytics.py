from backend import analytics, db
from tests.conftest import END


def test_exposure_matches_webcam_coverage(demo_db):
    conn = db.connect(demo_db)
    d = analytics.Analytics(conn, now=END).data()
    covered = sum(e - s for s, e in db.coverage(conn, "webcam"))
    assert abs(sum(p["seconds"] for p in d.pieces) - covered) < 1


def test_every_habit_event_gets_a_context(demo_db):
    conn = db.connect(demo_db)
    d = analytics.Analytics(conn, now=END).data()
    assert all(ev["context"] is not None for ev in d.events)


def test_planted_patterns_are_found_and_null_is_not(demo_db):
    conn = db.connect(demo_db)
    found = analytics.Analytics(conn, now=END).find_patterns(max_results=50)["patterns"]
    assert any(p["behavior"] == "nail_biting" and "45-90" in p["context"] and p["direction"] == "higher"
               for p in found[:5])
    assert any(p["behavior"] == "skin_picking" and "night" in p["context"] and p["direction"] == "higher"
               for p in found[:10])
    assert not any(p["behavior"] == "eye_rubbing" for p in found)


def test_habit_rates_rows_add_up(demo_db):
    conn = db.connect(demo_db)
    r = analytics.Analytics(conn, now=END).habit_rates("category", "any", min_minutes=0)
    assert sum(g["events"] for g in r["groups"]) == r["total_events"]
    assert abs(sum(g["observed_hours"] for g in r["groups"]) - r["total_observed_hours"]) < 0.1


def test_bad_arguments_return_errors(demo_db):
    a = analytics.Analytics(db.connect(demo_db), now=END)
    assert "error" in a.habit_rates("planet")
    assert "error" in a.find_patterns("sneezing")


def test_stats_helpers():
    assert abs(analytics.binom_two_sided(5, 10, 0.5) - 1.0) < 1e-9
    assert analytics.binom_two_sided(10, 10, 0.5) < 0.01
    ratio, lo, hi = analytics.rate_ratio(30, 10, 10, 10)
    assert lo < ratio < hi and ratio > 2
    assert analytics.benjamini_hochberg([0.01, 0.04, 0.03]) == [0.03, 0.04, 0.04]


def test_streak_buckets():
    assert analytics.streak_label(0) == "0-15 min"
    assert analytics.streak_label(50) == "45-90 min"
    assert analytics.streak_label(200) == "90+ min"
    assert analytics.daypart(23) == analytics.daypart(2) == "night (23-5)"


def test_progress_numbers_are_consistent(demo_db):
    p = analytics.Analytics(db.connect(demo_db), now=END).progress()
    assert p["this_week"]["events"] == sum(d["events"] for d in p["days"])
    assert p["best_calm_minutes_this_week"] >= p["calm_streak_minutes"] >= 0
    assert len(p["days"]) == 7 and p["last_habit"]["ts"] <= END
