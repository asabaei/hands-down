from fastapi.testclient import TestClient

from backend import assistant, db, server
from evals import run_evals
from tests.conftest import END


class ScriptedClient:
    # plays back a fixed conversation, standing in for Ollama
    def __init__(self, replies):
        self.replies = list(replies)
        self.seen = []

    def chat(self, messages, tools):
        self.seen.append(messages)
        return self.replies.pop(0)

    def available(self):
        return {"ok": True, "model": "scripted", "model_pulled": True}


def call(name, **args):
    return {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": name, "arguments": args}}]}


def test_tool_loop_runs_tools_and_returns_answer(demo_db):
    client = ScriptedClient([call("find_patterns", behavior="skin_picking"),
                             {"role": "assistant", "content": "Mostly on Reddit at night."}])
    out = assistant.Assistant(db.connect(demo_db), client, now=END).ask("When do I pick?")
    assert out["answer"] == "Mostly on Reddit at night."
    assert out["tool_calls"][0]["name"] == "find_patterns"
    assert out["tool_calls"][0]["result"]["patterns"]
    tool_msgs = [m for m in client.seen[1] if m["role"] == "tool"]
    assert tool_msgs and tool_msgs[0]["tool_name"] == "find_patterns"


def test_every_tool_runs(demo_db):
    runner = assistant.ToolRunner(db.connect(demo_db), now=END)
    for tool in assistant.TOOLS:
        name = tool["function"]["name"]
        args = {"habit_rates": {"group_by": ["where"]},
                "propose_swap_change": {"action": "add", "text": "Put on hand lotion"}}.get(name, {})
        result = runner.run(name, args)
        assert "error" not in result, name


def test_clean_args_handles_sloppy_models():
    assert assistant.clean_args({"days": "7", "behavior": "", "group_by": "where,daypart"}) == \
        {"days": 7, "group_by": ["where", "daypart"]}


def test_grounding_check():
    trace = [{"result": {"rate_ratio_vs_rest": 2.65, "events": 18, "success_rate": 0.586}}]
    score, bad = run_evals.grounded("18 events, 2.65x higher, works 58.6% of the time", "q", trace)
    assert score == 1.0 and bad == []
    score, bad = run_evals.grounded("about 3.4x higher", "q", trace)
    assert bad == ["3.4"]


def test_eval_cases_have_truth(demo_db):
    from evals import cases
    truth = cases.truth_for(db.connect(demo_db), END)
    assert truth["overview"]["habit_events"] > 0 and truth["reddit_night_ratios"] != ["?"]


def test_chat_endpoint(demo_db):
    client = ScriptedClient([call("get_overview"), {"role": "assistant", "content": "ok"}])
    app = TestClient(server.create_app(demo_db, client=client, now=END))
    r = app.post("/api/chat", json={"question": "overview?"})
    assert r.status_code == 200 and r.json()["answer"] == "ok"


def test_api_endpoints(demo_db):
    app = TestClient(server.create_app(demo_db, client=ScriptedClient([]), now=END))
    for url in ["/api/status", "/api/range", "/api/overview", "/api/patterns", "/api/trend",
                "/api/nudges", "/api/usage", "/api/progress", "/api/rates?group_by=where,daypart", "/api/timeline?date=2026-10-30"]:
        assert app.get(url).status_code == 200, url


class StreamingClient(ScriptedClient):
    # like Ollama with stream=true: a reply arrives in pieces
    def chat_stream(self, messages, tools):
        self.seen.append(messages)
        reply = self.replies.pop(0)
        if reply.get("tool_calls"):
            yield {"content": reply.get("content", "")}
            yield {"tool_calls": reply["tool_calls"]}
        else:
            for word in reply["content"].split(" "):
                yield {"content": word + " "}


def test_stream_events_in_order(demo_db):
    client = StreamingClient([call("find_patterns", behavior="skin_picking"),
                              {"role": "assistant", "content": "Mostly on Reddit at night."}])
    events = list(assistant.Assistant(db.connect(demo_db), client, now=END).ask_stream("When do I pick?"))
    kinds = [e["type"] for e in events]
    assert kinds[0] == "status"
    assert kinds.index("step") < kinds.index("step_done") < kinds.index("token") < kinds.index("done")
    step = next(e for e in events if e["type"] == "step")
    assert step["label"] == "Searching patterns for skin picking"
    assert "".join(e["text"] for e in events if e["type"] == "token").strip() == "Mostly on Reddit at night."
    assert events[-1]["answer"] == "Mostly on Reddit at night."


def test_text_before_a_tool_call_is_reset(demo_db):
    thinking = dict(call("get_overview"), content="Let me check.")
    client = StreamingClient([thinking, {"role": "assistant", "content": "Done."}])
    events = list(assistant.Assistant(db.connect(demo_db), client, now=END).ask_stream("q"))
    kinds = [e["type"] for e in events]
    assert kinds.index("token") < kinds.index("reset") < kinds.index("step")
    assert events[-1]["answer"] == "Done."


def test_stream_endpoint(demo_db):
    import json
    client = StreamingClient([call("get_overview"), {"role": "assistant", "content": "All good."}])
    app = TestClient(server.create_app(demo_db, client=client, now=END))
    r = app.post("/api/chat/stream", json={"question": "overview?"})
    events = [json.loads(line) for line in r.text.splitlines()]
    assert events[-1]["type"] == "done" and events[-1]["answer"] == "All good."
    assert any(e["type"] == "step" and e["label"] == "Getting your overview" for e in events)


def test_step_labels():
    assert assistant.step_label("habit_rates", {"behavior": "nail_biting", "group_by": ["where", "daypart"]}) == \
        "Comparing nail biting by app or site and time of day"
    assert assistant.step_label("find_patterns", {}) == "Searching patterns for all habits"
