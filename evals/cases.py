# Eval questions for the assistant, run against the synthetic dataset (evals/synthetic.py)
# whose patterns are known. Each case checks:
#   tools     the model called at least one of the acceptable tools
#   args      the arguments that matter (e.g. behavior=skin_picking) were right
#   content   the answer says the right thing (regexes, checked case-insensitively)
# Grounding (every number in the answer appears in a tool result) is checked for every case.
#
# "truth" is computed from the analytics on the same database, so the expected values follow
# the data rather than being typed in by hand.

import re


def any_call(trace, names, **want):
    for call in trace:
        if call["name"] not in names:
            continue
        args = call["arguments"] or {}
        ok = True
        for k, v in want.items():
            got = args.get(k)
            if isinstance(v, (list, tuple, set)):
                if isinstance(got, list):
                    ok &= bool(set(got) & set(v))
                else:
                    ok &= got in v
            else:
                ok &= got == v
        if ok:
            return True
    return False


def has(answer, *patterns):
    return all(re.search(p, answer, re.I | re.S) for p in patterns)


def lacks(answer, *patterns):
    return not any(re.search(p, answer, re.I | re.S) for p in patterns)


NO_DATA = r"(no|not|isn't|wasn't|aren't|don't|doesn't|didn't|none|zero|0)\b.{0,60}(data|track|record|log|use|show|appear|any)"
NOT_SIG = (r"(no|not|isn't|wasn't|aren't|don't|didn't)\b.{0,40}(significant|clear|strong|reliable|consistent)"
           r"|could be (chance|noise|random)|no (clear |strong |real )?pattern|too (little|few)|can't (tell|say)"
           r"|inconclusive|not enough")

CASES = [
    {"id": "pick_when", "question": "When do I pick my skin the most?",
     "tools": lambda t: any_call(t, {"find_patterns", "habit_rates"}),
     "args": lambda t: any_call(t, {"find_patterns", "habit_rates"}, behavior="skin_picking"),
     "content": lambda a, truth: has(a, r"reddit", r"night|11 ?pm|23|late"),
     "about": "planted pattern 1 (skin picking 3x on Reddit at night)"},

    {"id": "bite_coding", "question": "Does my nail biting go up during long coding sessions?",
     "tools": lambda t: any_call(t, {"find_patterns", "habit_rates"}),
     "args": lambda t: any_call(t, {"find_patterns", "habit_rates"}, behavior="nail_biting"),
     "content": lambda a, truth: has(a, r"\byes\b|more|higher|increase|goes up|rise", r"45|long"),
     "about": "planted pattern 2 (nail biting 3.5x after 45 min in VS Code)"},

    {"id": "eye_null", "question": "Is there a pattern to when I rub my eyes?",
     "tools": lambda t: any_call(t, {"find_patterns", "habit_rates"}),
     "args": lambda t: any_call(t, {"find_patterns", "habit_rates"}, behavior="eye_rubbing"),
     "content": lambda a, truth: has(a, NOT_SIG),
     "about": "null behavior: eye rubbing has no planted pattern, the model must not invent one"},

    {"id": "total", "question": "How many habit events have I had in total?",
     "tools": lambda t: any_call(t, {"get_overview", "trend", "habit_rates"}),
     "args": lambda t: True,
     "content": lambda a, truth: str(truth["overview"]["habit_events"]) in a,
     "about": "simple lookup"},

    {"id": "top_app", "question": "Which app do I spend the most time in?",
     "tools": lambda t: any_call(t, {"app_usage", "get_overview"}),
     "args": lambda t: True,
     "content": lambda a, truth: has(a, re.escape(truth["top_app"]) + r"|vs ?code|visual studio"),
     "about": "simple lookup"},

    {"id": "tiktok", "question": "How much do I bite my nails while on TikTok?",
     "tools": lambda t: len(t) > 0,
     "args": lambda t: True,
     "content": lambda a, truth: has(a, r"tiktok") and has(a, NO_DATA),
     "about": "abstention: TikTok never appears in the data"},

    {"id": "trend", "question": "Are my habits getting better or worse over the last two weeks?",
     "tools": lambda t: any_call(t, {"trend"}),
     "args": lambda t: any_call(t, {"trend"}, days=[13, 14, 15]),
     "content": lambda a, truth: True,
     "about": "time-series tool with the right window"},

    {"id": "bandit_vs_random", "question": "Do the bandit's nudges actually work better than random ones?",
     "tools": lambda t: any_call(t, {"nudge_stats"}),
     "args": lambda t: True,
     "content": lambda a, truth: (has(a, re.escape(truth["bandit_pct"]), re.escape(truth["random_pct"]))
                                  and (truth["significant"] or has(a, NOT_SIG + r"|p ?[=≈] ?0\.1"))),
     "about": "must report both rates and that the difference isn't significant yet"},

    {"id": "best_swap", "question": "Which swap works best for me when I'm skin picking?",
     "tools": lambda t: any_call(t, {"nudge_stats"}),
     "args": lambda t: True,
     "content": lambda a, truth: has(a, truth["best_pick_arm_pattern"]),
     "about": "reads the per-context posteriors"},

    {"id": "weekend", "question": "Do I pick my skin more on weekends than weekdays?",
     "tools": lambda t: any_call(t, {"habit_rates", "find_patterns"}),
     "args": lambda t: any_call(t, {"habit_rates"}, behavior="skin_picking", group_by=["daytype"])
                       or any_call(t, {"find_patterns"}, behavior="skin_picking"),
     "content": lambda a, truth: True,
     "about": "picks the right dimension"},

    {"id": "youtube_cause", "question": "Does YouTube make me bite my nails?",
     "tools": lambda t: any_call(t, {"habit_rates", "find_patterns"}),
     "args": lambda t: any_call(t, {"habit_rates", "find_patterns"}, behavior="nail_biting"),
     "content": lambda a, truth: has(a, r"less|lower|fewer|\bno\b|not") and lacks(a, r"youtube (causes|makes you)"),
     "about": "causal trap: nail biting is actually LOWER on YouTube"},

    {"id": "reddit_night_number", "question": "How much higher is my skin picking rate on Reddit after 11pm than the rest of the time?",
     "tools": lambda t: any_call(t, {"habit_rates", "find_patterns"}),
     "args": lambda t: any_call(t, {"habit_rates"}, group_by=["where", "daypart"]) or any_call(t, {"find_patterns"}, behavior="skin_picking"),
     "content": lambda a, truth: any(x in a for x in truth["reddit_night_ratios"]),
     "about": "must quote the computed rate ratio, not make one up"},

    {"id": "today", "question": "What habit events did I have yesterday, and what was I doing?",
     "tools": lambda t: any_call(t, {"list_events"}),
     "args": lambda t: any_call(t, {"list_events"}, days=[1, 2]),
     "content": lambda a, truth: True,
     "about": "raw event lookup"},

    {"id": "interesting", "question": "Tell me the most interesting thing about my habits.",
     "tools": lambda t: any_call(t, {"find_patterns"}),
     "args": lambda t: True,
     "content": lambda a, truth: has(a, r"reddit|code|coding|vs ?code"),
     "about": "open question, should surface a planted pattern"},
]


def truth_for(conn, now):
    from backend import analytics, bandit
    a = analytics.Analytics(conn, now=now)
    ov = a.overview()
    usage = a.app_usage("where")["hours"]
    s = bandit.stats(conn)
    g = s["groups"]
    pick = s["arms_by_context"].get("habit:skin_picking", [])
    best = pick[0]["arm"] if pick else "fidget"
    best_words = {"walk": r"walk", "fidget": r"fidget|stress ball", "switch_task": r"switch",
                  "water": r"water", "breathe": r"breath", "stretch": r"stretch",
                  "hands_busy": r"hands busy|hold something|hands_busy", "close_tab": r"close"}
    rr = a.habit_rates(["where", "daypart"], "skin_picking")
    ratios = [str(r["rate_ratio_vs_rest"]) for r in rr["groups"] if r["context"].startswith("where=reddit.com & daypart=night")]
    fp = a.find_patterns("skin_picking")
    ratios += [str(p["rate_ratio_vs_rest"]) for p in fp["patterns"] if "reddit" in p["context"] or "social" in p["context"]]
    return {
        "overview": ov,
        "top_app": next(iter(usage)),
        "bandit_pct": str(round(g["bandit"]["success_rate"] * 100)) if g["bandit"]["success_rate"] else "?",
        "random_pct": str(round(g["random"]["success_rate"] * 100)) if g["random"]["success_rate"] else "?",
        "significant": (s["fisher_p_value"] or 1) < 0.05,
        "best_pick_arm_pattern": best_words[best],
        "reddit_night_ratios": ratios or ["?"],
    }
