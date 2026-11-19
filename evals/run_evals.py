# Runs the assistant eval suite against a local Ollama model.
#
#   ollama pull qwen2.5:7b-instruct
#   python -m evals.run_evals                                  # default model from config.py
#   python -m evals.run_evals --models qwen2.5:7b-instruct llama3.1:8b --repeats 3
#   python -m evals.run_evals --baseline                       # also run a no-tools baseline
#
# The baseline gives the model the raw event log (time, behavior, app/site) in the prompt and no
# tools. It shows what the tool layer adds: without exposure time it can't compute real rates.
#
# Writes evals/results/<model>.json and prints a table.

import argparse
import json
import os
import re
import time

import config
from backend import assistant, db
from evals import cases as case_mod
from evals import synthetic

EVAL_DB = "evals/results/eval.db"
EVAL_END = time.mktime((2026, 11, 1, 12, 0, 0, 0, 0, -1))   # fixed so the data is the same on every run
NUMBER = re.compile(r"(?<![\w.:])(\d+(?:\.\d+)?)(?![\d:])(%?)")   # skips clock times like 7:58
CONFIDENCE = re.compile(r"\b95 ?% ?(confidence|CI)\b", re.I)


def numbers_in(text):
    return [(m.group(1), m.group(2)) for m in NUMBER.finditer(text)]


def grounded(answer, question, trace):
    # share of the numbers in the answer that also appear in a tool result (or the question),
    # at the precision the answer uses: "2.7x" matches 2.65, "59%" matches 0.586, "3.4x" doesn't match 2.65
    # the tool arguments count too: "in the last 7 days" is fine when the model asked for days=7
    source = question + " " + " ".join(json.dumps([c.get("arguments"), c["result"]], default=str) for c in trace)
    answer = CONFIDENCE.sub("", answer)
    known = []
    for value, _ in numbers_in(source):
        v = float(value)
        known += [v, v * 100]
    # "11 PM" is hour 23 in the data
    answer = re.sub(r"\b(1[0-2]|[1-9]) ?(pm|p\.m\.)", lambda m: str(12 if m.group(1) == "12" else int(m.group(1)) + 12), answer, flags=re.I)
    answer = re.sub(r"\b12 ?(am|a\.m\.)", "0", answer, flags=re.I)
    checked = [(v, pct) for v, pct in numbers_in(answer) if not (len(v) == 4 and v.startswith("20"))]   # skip years
    if not checked:
        return 1.0, []
    bad = []
    for value, pct in checked:
        v = float(value)
        decimals = len(value.split(".")[1]) if "." in value else 0
        tolerance = 0.5 * 10 ** -decimals + 1e-9
        if not (any(abs(k - v) <= tolerance for k in known) or (decimals == 0 and v <= 2)):
            bad.append(value + pct)
    return 1 - len(bad) / len(checked), bad


class BaselineClient:
    # no tools: the raw event log goes into the system prompt instead
    def __init__(self, inner, conn):
        self.inner = inner
        rows = conn.execute(
            "SELECT t.start, t.behavior, (SELECT COALESCE(a.domain, a.app) FROM activity a "
            "WHERE a.start <= t.start AND a.end >= t.start LIMIT 1) AS where_ FROM touch_events t "
            "WHERE t.alerted = 1 ORDER BY t.start").fetchall()
        lines = [time.strftime("%Y-%m-%d %H:%M", time.localtime(r[0])) + " " + r[1] + " " + str(r[2]) for r in rows]
        self.log = "Habit event log (time, behavior, app/site in focus):\n" + "\n".join(lines)

    def chat(self, messages, tools):
        messages = [dict(messages[0], content=messages[0]["content"] + "\n\n" + self.log)] + messages[1:]
        return self.inner.chat(messages, [])


def run_model(model, repeats, baseline=False):
    conn = db.connect(EVAL_DB)
    truth = case_mod.truth_for(conn, EVAL_END)
    client = assistant.OllamaClient(model=model)
    if baseline:
        client = BaselineClient(client, conn)
    bot = assistant.Assistant(conn, client, now=EVAL_END)
    results = []
    for case in case_mod.CASES:
        for r in range(repeats):
            try:
                out = bot.ask(case["question"])
            except RuntimeError as error:
                print(error)
                raise SystemExit(1)
            trace = out["tool_calls"]
            g, bad = grounded(out["answer"], case["question"], trace)
            res = {"id": case["id"], "repeat": r, "answer": out["answer"], "seconds": out["seconds"],
                   "tools_called": [{"name": c["name"], "arguments": c["arguments"]} for c in trace],
                   "tool_ok": bool(case["tools"](trace)) if not baseline else None,
                   "args_ok": bool(case["args"](trace)) if not baseline else None,
                   "content_ok": bool(case["content"](out["answer"], truth)),
                   "grounded": round(g, 3), "ungrounded_numbers": bad}
            res["pass"] = all(res[k] is not False for k in ("tool_ok", "args_ok", "content_ok")) and g >= 0.999
            results.append(res)
            print(("PASS " if res["pass"] else "FAIL ") + case["id"] + "  tools=" +
                  ",".join(c["name"] for c in trace) + ("  ungrounded=" + ",".join(bad) if bad else ""))
    return results


def summarize(results):
    n = len(results)
    def rate(key):
        vals = [r[key] for r in results if r[key] is not None]
        return round(sum(vals) / len(vals), 3) if vals else None
    return {"cases": n, "pass_rate": rate("pass"), "tool_accuracy": rate("tool_ok"),
            "arg_accuracy": rate("args_ok"), "content_accuracy": rate("content_ok"),
            "grounded_numbers": round(sum(r["grounded"] for r in results) / n, 3),
            "median_seconds": sorted(r["seconds"] for r in results)[n // 2]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", default=[config.OLLAMA_MODEL])
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--baseline", action="store_true", help="also run the no-tools baseline")
    args = parser.parse_args()

    os.makedirs("evals/results", exist_ok=True)
    synthetic.generate(EVAL_DB, days=28, seed=7, end=EVAL_END)

    table = []
    for model in args.models:
        runs = [("tools", False)] + ([("no tools (raw log)", True)] if args.baseline else [])
        for label, base in runs:
            print("\n== " + model + " / " + label)
            results = run_model(model, args.repeats, base)
            summary = summarize(results)
            table.append((model, label, summary))
            name = model.replace(":", "_").replace("/", "_") + ("_baseline" if base else "")
            with open("evals/results/" + name + ".json", "w") as f:
                json.dump({"model": model, "mode": label, "summary": summary, "results": results}, f, indent=2)

    print("\n| model | mode | pass | tools | args | content | grounded numbers | median s |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    pct = lambda x: "-" if x is None else str(round(x * 100)) + "%"
    for model, label, s in table:
        print("| " + " | ".join([model, label, pct(s["pass_rate"]), pct(s["tool_accuracy"]), pct(s["arg_accuracy"]),
                                 pct(s["content_accuracy"]), pct(s["grounded_numbers"]), str(s["median_seconds"])]) + " |")


if __name__ == "__main__":
    main()
