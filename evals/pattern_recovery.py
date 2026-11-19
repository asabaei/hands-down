# Checks the analytics layer on its own (no LLM): across many synthetic datasets, does
# find_patterns recover the two planted patterns, and how often does it report a pattern
# for eye rubbing, which has none?
#
#   python -m evals.pattern_recovery --seeds 50

import argparse
import os

from backend import analytics, db
from evals import synthetic


def is_reddit_night(p):
    return p["behavior"] == "skin_picking" and ("reddit.com" in p["context"] or "social" in p["context"]) \
        and "night" in p["context"] and p["direction"] == "higher"


def is_code_streak(p):
    return p["behavior"] == "nail_biting" and ("Code" in p["context"] or "coding" in p["context"]) \
        and ("45-90" in p["context"] or "90+" in p["context"]) and p["direction"] == "higher"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=30)
    parser.add_argument("--days", type=int, default=28)
    parser.add_argument("--top", type=int, default=8, help="a pattern counts as found if it's in the top N")
    args = parser.parse_args()
    path = "evals/results/recovery.db"
    os.makedirs("evals/results", exist_ok=True)
    found_a = found_b = false_eye = 0
    for seed in range(args.seeds):
        synthetic.generate(path, days=args.days, seed=1000 + seed, nudges=False)
        conn = db.connect(path)
        patterns = analytics.Analytics(conn).find_patterns(max_results=50)["patterns"]
        conn.close()
        top = patterns[:args.top]
        found_a += any(is_reddit_night(p) for p in top)
        found_b += any(is_code_streak(p) for p in top)
        false_eye += any(p["behavior"] == "eye_rubbing" for p in patterns)
    n = args.seeds
    print("datasets:", n, " days each:", args.days)
    print("skin picking on Reddit at night found (top " + str(args.top) + "): " + str(found_a) + "/" + str(n))
    print("nail biting in long VS Code sessions found (top " + str(args.top) + "): " + str(found_b) + "/" + str(n))
    print("datasets with a false eye-rubbing pattern: " + str(false_eye) + "/" + str(n))


if __name__ == "__main__":
    main()
