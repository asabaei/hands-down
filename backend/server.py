# The dashboard API. Also starts the active-window tracker and the nudge engine in the
# background, so the whole app is two commands:
#
#   python tracker.py --model          # webcam (needs its own window)
#   python -m backend.server           # everything else, dashboard at http://localhost:8000
#
#   python -m backend.server --demo    # 4 weeks of synthetic data, no trackers, to try the dashboard

import argparse
import json
import os
import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
from backend import activity, analytics, assistant, bandit, db, nudges, swaps

WEB_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "dist")


class SwapRequest(BaseModel):
    text: str | None = None
    habit: bool | None = None
    doomscroll: bool | None = None
    active: bool | None = None


class ChatRequest(BaseModel):
    question: str
    history: list = []


def day_bounds(date):
    if date:
        try:
            t = time.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(400, "date must be YYYY-MM-DD")
    else:
        t = time.localtime()
    start = time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1))
    end = time.mktime((t.tm_year, t.tm_mon, t.tm_mday + 1, 0, 0, 0, 0, 0, -1))
    return start, end


def create_app(db_path=None, activity_tracker=None, nudge_engine=None, client=None, now=None, demo=False):
    app = FastAPI(title="Hand-Face Tracker")
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"],
                       allow_headers=["*"])
    llm = client or assistant.OllamaClient()

    def conn():
        return db.connect(db_path)

    def stats_obj(c):
        return analytics.Analytics(c, now=now)

    @app.get("/api/status")
    def status():
        c = conn()
        t = now or time.time()
        out = {"now": t, "db": db_path or db.default_path(), "trackers": {}}
        for source in ("webcam", "activity"):
            r = c.execute("SELECT MAX(COALESCE(end, last_seen)) AS t, "
                          "MAX(CASE WHEN end IS NULL THEN last_seen END) AS live FROM sessions WHERE source = ?",
                          (source,)).fetchone()
            alive = r["live"] is not None and t - r["live"] < 3 * config.HEARTBEAT_SECONDS
            out["trackers"][source] = {"running": bool(alive), "last_seen": r["t"]}
        out["current_activity"] = activity_tracker.last if activity_tracker else None
        out["latest_nudge"] = nudge_engine.latest if nudge_engine else None
        out["llm"] = llm.available() if hasattr(llm, "available") else {"ok": True}
        out["has_data"] = c.execute("SELECT COUNT(*) FROM touch_events").fetchone()[0] > 0
        out["demo"] = demo
        last = c.execute("SELECT ts, arm, status, trigger FROM nudges WHERE ts <= ? ORDER BY ts DESC LIMIT 1",
                         (t,)).fetchone()
        out["last_nudge"] = dict(last, text=swaps.text_for(c, last["arm"])) if last else None
        return out

    @app.get("/api/range")
    def data_range():
        c = conn()
        r = c.execute("SELECT MIN(start) AS s, MAX(end) AS e FROM activity").fetchone()
        r2 = c.execute("SELECT MIN(start) AS s, MAX(end) AS e FROM touch_events").fetchone()
        starts = [x for x in (r["s"], r2["s"]) if x]
        ends = [x for x in (r["e"], r2["e"]) if x]
        return {"start": min(starts) if starts else None, "end": max(ends) if ends else None}

    @app.get("/api/timeline")
    def timeline(date: str = None):
        start, end = day_bounds(date)
        return stats_obj(conn()).timeline(start, end)

    @app.get("/api/progress")
    def progress():
        return stats_obj(conn()).progress()

    @app.get("/api/overview")
    def overview(days: int = None):
        return stats_obj(conn()).overview(days)

    @app.get("/api/rates")
    def rates(group_by: str = "category", behavior: str = "any", days: int = None, min_minutes: int = None):
        dims = group_by.split(",")
        return stats_obj(conn()).habit_rates(dims if len(dims) > 1 else dims[0], behavior, days, min_minutes)

    @app.get("/api/patterns")
    def patterns(behavior: str = "any", days: int = None):
        return stats_obj(conn()).find_patterns(behavior, days, max_results=12)

    @app.get("/api/trend")
    def trend(behavior: str = "any", period: str = "day", days: int = 28):
        return stats_obj(conn()).trend(behavior, period, days)

    @app.get("/api/usage")
    def usage(group_by: str = "category", days: int = None):
        return stats_obj(conn()).app_usage(group_by, days)

    @app.get("/api/nudges")
    def nudge_stats(limit: int = 30):
        c = conn()
        s = bandit.stats(c)
        s["recent"] = db.rows(c, "SELECT ts, trigger, context, detail, arm, policy, status FROM nudges "
                                 "ORDER BY ts DESC LIMIT ?", (limit,))
        s["arm_text"] = swaps.texts(c)
        return s

    # ---- your swaps ----
    @app.get("/api/swaps")
    def list_swaps():
        return swaps.listing(conn())

    @app.post("/api/swaps")
    def add_swap(req: SwapRequest):
        c = conn()
        try:
            key = swaps.add(c, req.text or "", req.habit if req.habit is not None else True, bool(req.doomscroll))
        except ValueError as error:
            raise HTTPException(400, str(error))
        return {"key": key, **swaps.listing(c)}

    @app.patch("/api/swaps/{key}")
    def change_swap(key: str, req: SwapRequest):
        c = conn()
        try:
            swaps.update(c, key, req.text, req.habit, req.doomscroll, req.active)
        except KeyError:
            raise HTTPException(404, "no swap called " + key)
        return swaps.listing(c)

    @app.post("/api/swaps/apply")
    def apply_proposal(proposal: dict):
        # a change Pip proposed in the chat, applied only after you press "Yes"
        c = conn()
        try:
            key = swaps.apply(c, proposal)
        except (KeyError, ValueError) as error:
            raise HTTPException(400, str(error))
        return {"key": key, **swaps.listing(c)}

    @app.post("/api/chat")
    def chat(req: ChatRequest):
        bot = assistant.Assistant(conn(), llm, now=now)
        try:
            return bot.ask(req.question, req.history[-8:])
        except RuntimeError as error:
            raise HTTPException(503, str(error))

    @app.post("/api/chat/stream")
    def chat_stream(req: ChatRequest):
        # one JSON event per line (see Assistant.ask_stream), so the page can show each step and
        # the answer as it is written
        bot = assistant.Assistant(conn(), llm, now=now)

        def events():
            try:
                for event in bot.ask_stream(req.question, req.history[-8:]):
                    yield json.dumps(event, default=str) + "\n"
            except RuntimeError as error:
                yield json.dumps({"type": "error", "text": str(error)}) + "\n"

        return StreamingResponse(events(), media_type="application/x-ndjson")

    # the dashboard is looked up on every request, so building it while the server runs works too
    app.mount("/assets", StaticFiles(directory=os.path.join(WEB_DIST, "assets"), check_dir=False), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        file = os.path.realpath(os.path.join(WEB_DIST, path))
        if path and file.startswith(os.path.realpath(WEB_DIST) + os.sep) and os.path.isfile(file):
            return FileResponse(file)    # favicon and other files from web/public
        index = os.path.join(WEB_DIST, "index.html")
        if not os.path.exists(index):
            return HTMLResponse("<h3>The dashboard isn't built yet.</h3><p>Run <code>cd web &amp;&amp; npm install "
                                "&amp;&amp; npm run build</code>, then reload this page. The API is running.</p>",
                                status_code=503)
        return FileResponse(index)

    return app


def main():
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=None, help="database file (default: data/habits.db)")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-activity", action="store_true", help="don't start the active-window tracker")
    parser.add_argument("--no-nudges", action="store_true", help="don't send nudges")
    parser.add_argument("--demo", action="store_true", help="serve synthetic data (no trackers, no nudges)")
    args = parser.parse_args()

    tracker = engine = None
    db_path = args.db
    if args.demo:
        from evals import synthetic
        db_path = synthetic.generate("data_demo/habits.db")
        print("demo data written to", db_path)
        # pretend it's late on the last demo day, so "today" has data
        demo_now = analytics.Analytics(db.connect(db_path)).latest_time() + 600
    else:
        if not args.no_activity:
            tracker = activity.ActivityTracker(db_path)
            tracker.start_background()
        if not args.no_nudges and config.NUDGES_ENABLED:
            engine = nudges.NudgeEngine(db_path)
            engine.start_background()
    import threading
    threading.Thread(target=assistant.OllamaClient().warm_up, daemon=True).start()   # load the model now
    if not os.path.isdir(WEB_DIST):
        print("dashboard not built yet: cd web && npm install && npm run build (API still works)")
    print("dashboard: http://localhost:" + str(args.port))
    app = create_app(db_path, tracker, engine, now=demo_now if args.demo else None, demo=args.demo)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    if tracker:
        tracker.stop()
    if engine:
        engine.stop()


if __name__ == "__main__":
    main()
