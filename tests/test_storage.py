import os
import sys
import types
from unittest import mock

from backend import db


def import_storage():
    # storage imports the MediaPipe code; stub it if MediaPipe isn't installed (CI, Python 3.13)
    try:
        import mediapipe  # noqa: F401
    except ImportError:
        fake = types.ModuleType("mediapipe")
        fake.solutions = mock.MagicMock()
        sys.modules["mediapipe"] = fake
    import storage
    return storage


def test_tracker_events_reach_sqlite(tmp_path):
    storage = import_storage()
    storage.setup(str(tmp_path))
    storage.log_alert(100.0, "mouth", "nail_biting")
    storage.log_event(99.0, "mouth", "nail_biting", True, 4.0)
    storage.log_session(90.0, 110.0, [("mouth", 4.0)])
    conn = db.connect(os.path.join(str(tmp_path), "habits.db"))
    assert db.rows(conn, "SELECT behavior, start, end FROM touch_events") == \
        [{"behavior": "nail_biting", "start": 99.0, "end": 103.0}]
    assert len(db.rows(conn, "SELECT * FROM alerts")) == 1
    assert conn.execute("SELECT end FROM sessions WHERE source = 'webcam'").fetchone()[0] == 110.0
    assert os.path.exists(os.path.join(str(tmp_path), "events.csv"))

