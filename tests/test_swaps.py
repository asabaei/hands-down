import config
from fastapi.testclient import TestClient

from backend import assistant, db, nudges, server, swaps


def test_defaults_are_copied_from_config(empty_db):
    conn = db.connect(empty_db)
    keys = [r["key"] for r in swaps.all_swaps(conn)]
    assert keys == list(config.NUDGE_ARMS)
    assert swaps.arms_for(conn, "habit") == config.NUDGE_ARMS_BY_TRIGGER["habit"]
    assert swaps.arms_for(conn, "doomscroll") == config.NUDGE_ARMS_BY_TRIGGER["doomscroll"]


def test_add_pause_reword(empty_db):
    conn = db.connect(empty_db)
    key = swaps.add(conn, "Put on some hand lotion", habit=True, doomscroll=False)
    assert key in swaps.arms_for(conn, "habit") and key not in swaps.arms_for(conn, "doomscroll")
    swaps.update(conn, "walk", active=False)
    assert "walk" not in swaps.arms_for(conn, "habit")
    swaps.update(conn, "fidget", text="Squeeze a stress ball")
    assert swaps.text_for(conn, "fidget") == "Squeeze a stress ball"


def test_find_by_loose_words(empty_db):
    conn = db.connect(empty_db)
    assert swaps.find(conn, "walk")["key"] == "walk"
    assert swaps.find(conn, "the stress ball one")["key"] == "fidget"
    assert swaps.find(conn, "glass of water")["key"] == "water"


def test_proposals_change_nothing_until_applied(empty_db):
    conn = db.connect(empty_db)
    before = swaps.all_swaps(conn)
    p = swaps.propose(conn, "add", text="put on hand lotion", when="both")
    assert p["proposal"] == {"action": "add", "text": "Put on hand lotion", "habit": True, "doomscroll": True}
    assert swaps.propose(conn, "remove", swap="walking")["proposal"]["action"] == "pause"
    assert swaps.all_swaps(conn) == before                       # nothing changed yet
    key = swaps.apply(conn, p["proposal"])
    assert key in swaps.arms_for(conn, "doomscroll")
    assert "error" in swaps.propose(conn, "pause", swap="juggling chainsaws")
    assert "error" in swaps.propose(conn, "dance")


def test_advice_needs_enough_tries(empty_db):
    conn = db.connect(empty_db)
    def nudges_for(arm, ok, n):
        for i in range(n):
            conn.execute("INSERT INTO nudges (ts, trigger, context, arm, policy, status) VALUES (?, 'habit', 'habit:any', ?, 'bandit', ?)",
                         (i, arm, "success" if i < ok else "failure"))
        conn.commit()
    nudges_for("fidget", 7, 10)
    nudges_for("breathe", 1, 5)
    assert swaps.advice(conn) == []                              # breathe has only 5 tries
    nudges_for("breathe", 0, 4)
    tips = swaps.advice(conn)
    assert len(tips) == 1 and tips[0]["key"] == "breathe" and tips[0]["best_key"] == "fidget"


def test_engine_only_suggests_switched_on_swaps(empty_db):
    conn = db.connect(empty_db)
    conn.execute("INSERT INTO sessions (source, start, end, last_seen) VALUES ('webcam', 0, 9999, 9999)")
    conn.commit()
    for key in swaps.arms_for(conn, "habit"):
        if key != "water":
            swaps.update(conn, key, active=False)
    e = nudges.NudgeEngine(empty_db, notify=lambda *a: None, seed=1)
    e.step(conn, 1000)
    db.log_alert(conn, 1, 1000, "mouth", "nail_biting")
    e.step(conn, 1001)
    assert [r["arm"] for r in db.rows(conn, "SELECT arm FROM nudges")] == ["water"]


def test_swap_api(empty_db):
    app = TestClient(server.create_app(empty_db))
    r = app.post("/api/swaps", json={"text": "Drink some tea", "habit": True, "doomscroll": True})
    key = r.json()["key"]
    assert any(s["key"] == key and s["doomscroll"] for s in r.json()["swaps"])
    r = app.patch("/api/swaps/" + key, json={"active": False})
    assert not next(s for s in r.json()["swaps"] if s["key"] == key)["active"]
    r = app.post("/api/swaps/apply", json={"action": "reword", "key": "walk", "text": "Walk around the block"})
    assert next(s for s in r.json()["swaps"] if s["key"] == "walk")["text"] == "Walk around the block"
    assert app.patch("/api/swaps/nope", json={"active": False}).status_code == 404


def test_pip_tools_for_swaps(empty_db):
    runner = assistant.ToolRunner(db.connect(empty_db))
    assert runner.run("list_swaps", {})["swaps"]
    out = runner.run("propose_swap_change", {"action": "add", "text": "Put on hand lotion"})
    assert out["proposal"]["action"] == "add" and "Add" in out["summary"]
    assert assistant.step_label("propose_swap_change", {}) == "Getting a swap change ready for you"


def test_swap_listed_for_a_trigger_but_missing_text_still_works(empty_db, monkeypatch):
    # e.g. "hands_busy" left in NUDGE_ARMS_BY_TRIGGER after its NUDGE_ARMS line was deleted
    arms = dict(config.NUDGE_ARMS)
    del arms["hands_busy"]
    monkeypatch.setattr(config, "NUDGE_ARMS", arms)
    conn = db.connect(empty_db)
    assert "hands_busy" in swaps.arms_for(conn, "habit")
    assert swaps.text_for(conn, "hands_busy") == "Hands busy"


def test_pip_never_claims_a_swap_change_is_done(empty_db):
    # after proposing a change, Pip's reply is a fixed "tap Yes" sentence; the model isn't asked again
    from tests.test_assistant import ScriptedClient, call
    client = ScriptedClient([call("propose_swap_change", action="add", text="put on hand lotion"),
                             {"role": "assistant", "content": "Great! I've added it."}])
    out = assistant.Assistant(db.connect(empty_db), client).ask("add hand lotion as a swap")
    assert out["answer"].startswith("Ooh, good idea! Tap Yes below") and "added it" not in out["answer"]
    assert len(client.replies) == 1          # the model's "I've added it" was never requested
    assert "lotion" not in [r["text"].lower() for r in swaps.all_swaps(db.connect(empty_db))]


def test_no_tap_yes_when_there_is_nothing_to_tap(empty_db):
    from tests.test_assistant import ScriptedClient, call
    conn = db.connect(empty_db)
    swaps.add(conn, "Put on hand lotion")
    bot = assistant.Assistant(conn, ScriptedClient([call("propose_swap_change", action="add", text="put on hand lotion")]))
    assert bot.ask("add hand lotion")["answer"].startswith("Good news")
    bot = assistant.Assistant(conn, ScriptedClient([call("propose_swap_change", action="pause", swap="juggling chainsaws")]))
    answer = bot.ask("stop the chainsaw one")["answer"]
    assert "couldn't find" in answer and "Tap Yes" not in answer
