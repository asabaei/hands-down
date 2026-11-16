# The local LLM assistant. It answers questions about your habits by calling tools that run
# the analytics in backend/analytics.py, then explains the results.
#
# Rules it is given (and that the evals check):
#   - every number in an answer must come from a tool result, never from its own arithmetic
#   - always give the sample size, and say when there is too little data
#   - patterns are associations, not causes
#
# It talks to Ollama's /api/chat with the "tools" field, so any Ollama model with tool calling
# works (qwen2.5, llama3.1, mistral-nemo, ...). Nothing leaves your machine.

import json
import time
import urllib.error
import urllib.request

import config
from backend import analytics, bandit, db

BEHAVIOR_ENUM = ["any", "nail_biting", "skin_picking", "eye_rubbing"]

TOOLS = [
    {"type": "function", "function": {
        "name": "get_overview",
        "description": "Totals for a time range: hours the webcam was watching, habit events by behavior, "
                       "time per app category, and the most used apps and sites. Good first call for broad questions.",
        "parameters": {"type": "object", "properties": {
            "days": {"type": "integer", "description": "look back this many days; omit for all data"}}}}},
    {"type": "function", "function": {
        "name": "find_patterns",
        "description": "Searches every context (app, site, category, time of day, weekday/weekend, minutes into an "
                       "app session, and pairs of these) for habit rates that are significantly higher or lower "
                       "than the rest of the time, corrected for multiple testing. Use for 'when / where do I ...' "
                       "and 'what triggers ...' questions.",
        "parameters": {"type": "object", "properties": {
            "behavior": {"type": "string", "enum": BEHAVIOR_ENUM},
            "days": {"type": "integer", "description": "look back this many days; omit for all data"}}}}},
    {"type": "function", "function": {
        "name": "habit_rates",
        "description": "Habit events per observed hour, split by one or two dimensions, each compared with the "
                       "rest of the time (rate ratio with 95% CI and p-value). Use to check a specific idea, "
                       "e.g. group_by=['where','daypart'] for 'Reddit at night'.",
        "parameters": {"type": "object", "required": ["group_by"], "properties": {
            "group_by": {"type": "array", "items": {"type": "string", "enum": analytics.DIMENSIONS},
                         "description": "category (social, video, coding...), where (site or app), hour (0-23), "
                                        "daypart, daytype (weekday/weekend), streak (minutes into the app session)"},
            "behavior": {"type": "string", "enum": BEHAVIOR_ENUM},
            "days": {"type": "integer"}}}}},
    {"type": "function", "function": {
        "name": "trend",
        "description": "Habit events and events per observed hour for each day or week, to see if things are "
                       "getting better or worse.",
        "parameters": {"type": "object", "properties": {
            "behavior": {"type": "string", "enum": BEHAVIOR_ENUM},
            "period": {"type": "string", "enum": ["day", "week"]},
            "days": {"type": "integer"}}}}},
    {"type": "function", "function": {
        "name": "list_events",
        "description": "Individual habit events with time, region, and what app/site was open. Use for "
                       "'what happened today / yesterday' questions.",
        "parameters": {"type": "object", "properties": {
            "behavior": {"type": "string", "enum": BEHAVIOR_ENUM},
            "days": {"type": "integer"},
            "where": {"type": "string", "description": "only events in this app, site, or category"},
            "limit": {"type": "integer"}}}}},
    {"type": "function", "function": {
        "name": "app_usage",
        "description": "Time spent in apps and sites (from the active-window tracker), grouped by app/site, "
                       "category, hour, or daypart.",
        "parameters": {"type": "object", "properties": {
            "group_by": {"type": "string", "enum": ["where", "category", "hour", "daypart"]},
            "days": {"type": "integer"}}}}},
    {"type": "function", "function": {
        "name": "nudge_stats",
        "description": "How well the swap nudges work: success rate of nudges picked by the bandit vs picked at "
                       "random (with 95% CIs and a Fisher exact test), and which swaps work best per context.",
        "parameters": {"type": "object", "properties": {}}}},
]

SYSTEM_PROMPT = """You are a habit-insight assistant inside a hand-to-face habit tracker. The user's data has two \
streams: webcam-detected hand-to-face habits (nail_biting, skin_picking, eye_rubbing) and which app or website was \
in the foreground. You answer questions about patterns across both.

Rules:
1. Always call tools to get data before answering. Never guess or invent numbers.
2. Every number you state must appear in a tool result. Do not do your own arithmetic; if you need a comparison, \
call habit_rates or find_patterns, which compute rate ratios for you.
3. Rates are per hour the webcam was watching ("observed hours"). Say this when you give a rate.
4. Mention the number of events behind a claim. If a tool reports too little data or no significant patterns, say \
so plainly instead of stretching the data.
5. Patterns are associations, not causes. Don't claim one thing causes another.
6. If the user asks about an app, site, or behavior that isn't in the data, say it isn't in the data.
7. Be brief: a short answer with the 1-3 most useful findings, then one practical suggestion if it fits.
8. Behavior names: nail_biting = nail biting, skin_picking = skin picking, eye_rubbing = eye rubbing.
"""


class OllamaClient:
    def __init__(self, url=None, model=None, timeout=180):
        self.url = (url or config.OLLAMA_URL).rstrip("/")
        self.model = model or config.OLLAMA_MODEL
        self.timeout = timeout

    def request(self, messages, tools, stream):
        body = json.dumps({"model": self.model, "messages": messages, "tools": tools, "stream": stream,
                           "keep_alive": config.OLLAMA_KEEP_ALIVE,
                           "options": {"temperature": 0, "num_ctx": config.OLLAMA_NUM_CTX}}).encode()
        req = urllib.request.Request(self.url + "/api/chat", data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            return urllib.request.urlopen(req, timeout=self.timeout)
        except urllib.error.URLError as error:
            raise RuntimeError("Can't reach Ollama at " + self.url + ". Is `ollama serve` running and is "
                               "the model pulled (ollama pull " + self.model + ")? " + str(error))

    def chat(self, messages, tools):
        with self.request(messages, tools, stream=False) as resp:
            return json.loads(resp.read())["message"]

    def chat_stream(self, messages, tools):
        # yields message pieces as the model writes them: {"content": "a few words"} and,
        # usually in one piece, {"tool_calls": [...]}
        with self.request(messages, tools, stream=True) as resp:
            for line in resp:
                if not line.strip():
                    continue
                chunk = json.loads(line)
                if chunk.get("error"):
                    raise RuntimeError("Ollama: " + chunk["error"])
                if chunk.get("message"):
                    yield chunk["message"]
                if chunk.get("done"):
                    return

    def warm_up(self):
        # loads the model into memory so the first question doesn't wait for it
        body = json.dumps({"model": self.model, "keep_alive": config.OLLAMA_KEEP_ALIVE}).encode()
        req = urllib.request.Request(self.url + "/api/generate", data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout):
                pass
        except (urllib.error.URLError, OSError):
            pass    # Ollama not running yet; the Ask tab will say so

    def available(self):
        try:
            with urllib.request.urlopen(self.url + "/api/tags", timeout=3) as resp:
                names = [m["name"] for m in json.loads(resp.read()).get("models", [])]
            return {"ok": True, "model": self.model, "model_pulled": any(n.startswith(self.model) for n in names)}
        except (urllib.error.URLError, OSError):
            return {"ok": False, "model": self.model, "model_pulled": False}


def clean_args(args):
    # small models sometimes send numbers as strings, a single string for a list, or empty values
    out = {}
    for k, v in (args or {}).items():
        if v in (None, "", [], "null"):
            continue
        if k in ("days", "limit") and isinstance(v, str):
            try:
                v = int(float(v))
            except ValueError:
                continue
        if k == "group_by" and isinstance(v, str):
            v = [x.strip() for x in v.split(",")] if "," in v else v
        out[k] = v
    return out


class ToolRunner:
    def __init__(self, conn, now=None):
        self.conn = conn
        self.analytics = analytics.Analytics(conn, now=now)

    def run(self, name, args):
        a = self.analytics
        args = clean_args(args)
        try:
            if name == "get_overview":
                return a.overview(args.get("days"))
            if name == "find_patterns":
                return a.find_patterns(args.get("behavior", "any"), args.get("days"))
            if name == "habit_rates":
                return a.habit_rates(args.get("group_by", "category"), args.get("behavior", "any"), args.get("days"))
            if name == "trend":
                return a.trend(args.get("behavior", "any"), args.get("period", "day"), args.get("days", 14))
            if name == "list_events":
                return a.list_events(args.get("behavior", "any"), args.get("days", 1), args.get("where"),
                                     min(int(args.get("limit", 20)), 50))
            if name == "app_usage":
                return a.app_usage(args.get("group_by", "where"), args.get("days"))
            if name == "nudge_stats":
                s = bandit.stats(self.conn)
                s.pop("series", None)
                return s
            return {"error": "unknown tool " + name}
        except (TypeError, ValueError) as error:
            return {"error": "bad arguments: " + str(error)}


# fields the model doesn't need: dropping them makes every prompt shorter and every answer faster
DROP_FOR_LLM = {"strength", "series", "definition"}


def slim(value):
    if isinstance(value, dict):
        return {k: slim(v) for k, v in value.items() if k not in DROP_FOR_LLM}
    if isinstance(value, list):
        return [slim(v) for v in value]
    return value


def compact(result, limit=3500):
    # keep tool results small enough for a local model's context
    result = slim(result)
    text = json.dumps(result, separators=(",", ":"), default=str)
    if len(text) <= limit:
        return text
    if isinstance(result, dict):
        for key in ("groups", "events", "rows", "patterns"):
            if isinstance(result.get(key), list) and len(result[key]) > 8:
                trimmed = dict(result)
                trimmed[key] = result[key][:8]
                trimmed["truncated"] = str(len(result[key]) - 8) + " more rows left out"
                return compact(trimmed, limit)
    return text[:limit]


def step_label(name, args):
    # what the chat shows while a tool runs, e.g. "Searching patterns for skin picking"
    args = clean_args(args)
    habit = BEHAVIOR_WORDS.get(args.get("behavior", "any"), "your habits")
    group = args.get("group_by", "category")
    if isinstance(group, list):
        group = " and ".join(GROUP_WORDS.get(g, g) for g in group)
    else:
        group = GROUP_WORDS.get(group, group)
    return {
        "get_overview": "Getting your overview",
        "find_patterns": "Searching patterns for " + habit,
        "habit_rates": "Comparing " + habit + " by " + group,
        "trend": "Checking the trend for " + habit,
        "list_events": "Looking up recent events",
        "app_usage": "Checking your app and site usage",
        "nudge_stats": "Checking how the nudges are doing",
    }.get(name, "Running " + str(name))


BEHAVIOR_WORDS = {"any": "all habits", "nail_biting": "nail biting", "skin_picking": "skin picking",
                  "eye_rubbing": "eye rubbing"}
GROUP_WORDS = {"category": "app category", "where": "app or site", "hour": "hour", "daypart": "time of day",
               "daytype": "weekday vs weekend", "streak": "session length"}


class Assistant:
    def __init__(self, conn=None, client=None, now=None):
        self.conn = conn or db.connect()
        self.client = client or OllamaClient()
        self.tools = ToolRunner(self.conn, now=now)

    def model_reply(self, messages, tools):
        # streams the reply if the client can, otherwise yields it as one piece
        if hasattr(self.client, "chat_stream"):
            yield from self.client.chat_stream(messages, tools)
        else:
            yield self.client.chat(messages, tools)

    def ask_stream(self, question, history=None):
        # yields events as they happen:
        #   {"type": "status", "text"}            what it's doing ("Thinking", "Writing answer")
        #   {"type": "step", "name", "arguments", "label"}   a tool call is starting
        #   {"type": "step_done", "name", "result"}          ...and its result
        #   {"type": "token", "text"}             a piece of the answer
        #   {"type": "reset"}                     drop the text streamed so far (the model went on to call a tool)
        #   {"type": "done", "answer", "tool_calls", "seconds"}
        started = time.time()
        today = time.strftime("%A %Y-%m-%d %H:%M", time.localtime(self.tools.analytics.now()))
        messages = [{"role": "system", "content": SYSTEM_PROMPT + "\nNow: " + today}]
        messages += history or []
        messages.append({"role": "user", "content": question})
        trace = []
        yield {"type": "status", "text": "Thinking"}
        for round_number in range(config.LLM_MAX_TOOL_ROUNDS + 1):
            last_round = round_number == config.LLM_MAX_TOOL_ROUNDS
            if last_round:   # out of rounds: ask for an answer without tools
                messages.append({"role": "user", "content": "Answer now using the tool results above."})
            content, calls = "", []
            for piece in self.model_reply(messages, [] if last_round else TOOLS):
                if piece.get("tool_calls"):
                    calls += piece["tool_calls"]
                text = piece.get("content") or ""
                if text:
                    if not content.strip() and not text.strip():
                        continue   # skip leading blank lines
                    content += text
                    yield {"type": "token", "text": text}
            messages.append({"role": "assistant", "content": content, "tool_calls": calls})
            if not calls:
                yield {"type": "done", "answer": content.strip(), "tool_calls": trace,
                       "seconds": round(time.time() - started, 2)}
                return
            if content:
                yield {"type": "reset"}   # text before a tool call was thinking out loud, not the answer
            for call in calls:
                fn = call.get("function", {})
                name, args = fn.get("name"), fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                yield {"type": "step", "name": name, "arguments": args, "label": step_label(name, args)}
                result = self.tools.run(name, args)
                trace.append({"name": name, "arguments": args, "result": result})
                messages.append({"role": "tool", "tool_name": name, "content": compact(result)})
                yield {"type": "step_done", "name": name, "result": result}
            yield {"type": "status", "text": "Reading the results"}

    def ask(self, question, history=None):
        # the same as ask_stream, but waits for the whole answer:
        # returns {"answer", "tool_calls": [{"name", "arguments", "result"}], "seconds"}
        for event in self.ask_stream(question, history):
            if event["type"] == "done":
                return {k: event[k] for k in ("answer", "tool_calls", "seconds")}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Ask the habit assistant a question")
    parser.add_argument("question", nargs="+")
    parser.add_argument("--db", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--show-tools", action="store_true")
    args = parser.parse_args()
    a = Assistant(db.connect(args.db), OllamaClient(model=args.model))
    out = a.ask(" ".join(args.question))
    if args.show_tools:
        for call in out["tool_calls"]:
            print("->", call["name"], json.dumps(call["arguments"]))
    print(out["answer"])


if __name__ == "__main__":
    main()
