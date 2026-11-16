from backend import activity, categories, db


def test_categorize():
    assert categories.categorize("Google Chrome", "www.reddit.com") == "social"
    assert categories.categorize("Google Chrome", "old.reddit.com") == "social"
    assert categories.categorize("Code") == "coding"
    assert categories.categorize("Discord.exe") == "chat"
    assert categories.categorize("firefox", None) == "browsing"
    assert categories.categorize("SomethingElse") == "other"
    assert categories.site_from_title("r/programming - Reddit - Google Chrome") == "reddit.com"


def test_tracker_merges_and_splits_segments(empty_db):
    windows = iter([("Code", "main.py", None)] * 3 + [("Google Chrome", "x", "https://www.youtube.com/watch")] * 2)
    idle = iter([0, 0, 0, 0, 500])
    t = activity.ActivityTracker(empty_db, reader=lambda: next(windows), idle_reader=lambda: next(idle))
    conn = db.connect(empty_db)
    sid = db.start_session(conn, "activity", 0)
    for i in range(5):
        t.step(conn, sid, 100 + i * 2)
    rows = db.rows(conn, "SELECT app, domain, category, idle, start, end FROM activity ORDER BY id")
    assert [(r["app"], r["category"]) for r in rows] == [("Code", "coding"), ("Google Chrome", "video"),
                                                         ("Google Chrome", "idle")]
    assert rows[0]["start"] == 100 and rows[0]["end"] == 106
    assert rows[1]["domain"] == "youtube.com"
    assert rows[2]["idle"] == 1


def test_titles_not_stored_by_default():
    assert activity.describe("Code", "secret_project.py", None, 0)[2] is None
