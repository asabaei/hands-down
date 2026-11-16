# Thompson-sampling bandit that learns which swap works for you.
#
# Each (context, swap) pair has a Beta posterior over "the behavior stopped after this nudge".
# Contexts are specific ("habit:skin_picking", "doomscroll"), so a swap that works for nail
# biting isn't assumed to work for scrolling. To avoid starting every context from scratch,
# the prior for a context borrows up to PRIOR_STRENGTH pseudo-observations from how that swap
# did across the other contexts of the same trigger.
#
# A fixed share of nudges (NUDGE_RANDOM_FRACTION) is picked uniformly at random instead. That
# random group is the comparison: "bandit nudges worked X% of the time vs Y% for random ones".
# Both groups run interleaved over the same days, so time-of-day and mood affect them equally.
# The random group's outcomes also update the posteriors (more data for the bandit), which
# doesn't bias the random group's own success rate.

import math
import random
from collections import defaultdict

import config
from backend import db

PRIOR_STRENGTH = 5


def trigger_of(context):
    return context.split(":")[0]


class Bandit:
    def __init__(self, seed=None, random_fraction=None):
        self.rng = random.Random(seed)
        self.random_fraction = config.NUDGE_RANDOM_FRACTION if random_fraction is None else random_fraction
        self.counts = defaultdict(lambda: [0, 0])   # (context, arm) -> [successes, failures]

    @classmethod
    def from_db(cls, conn, seed=None):
        b = cls(seed)
        for r in conn.execute("SELECT context, arm, status FROM nudges WHERE status IN ('success', 'failure')"):
            b.update(r["context"], r["arm"], r["status"] == "success")
        return b

    def update(self, context, arm, success):
        self.counts[(context, arm)][0 if success else 1] += 1

    def posterior(self, context, arm):
        s, f = self.counts[(context, arm)]
        trigger = trigger_of(context)
        # how this swap did in the other contexts of the same trigger
        os_, of = 0, 0
        for (c, a), (cs, cf) in self.counts.items():
            if a == arm and c != context and trigger_of(c) == trigger:
                os_ += cs
                of += cf
        n_other = os_ + of
        strength = min(n_other, PRIOR_STRENGTH)
        mean = (os_ + 1) / (n_other + 2)
        return 1 + strength * mean + s, 1 + strength * (1 - mean) + f

    def choose(self, trigger, context):
        arms = config.NUDGE_ARMS_BY_TRIGGER[trigger]
        if self.rng.random() < self.random_fraction:
            return self.rng.choice(arms), "random"
        draws = {arm: self.rng.betavariate(*self.posterior(context, arm)) for arm in arms}
        return max(draws, key=draws.get), "bandit"

    def summary(self, context):
        arms = config.NUDGE_ARMS_BY_TRIGGER[trigger_of(context)]
        out = []
        for arm in arms:
            a, b = self.posterior(context, arm)
            s, f = self.counts[(context, arm)]
            out.append({"arm": arm, "text": config.NUDGE_ARMS[arm], "successes": s, "failures": f,
                        "posterior_mean": round(a / (a + b), 3)})
        return sorted(out, key=lambda r: -r["posterior_mean"])


# ---- statistics for the comparison ----

def wilson(successes, n, z=1.96):
    if n == 0:
        return None, None
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return center - half, center + half


def fisher_exact(a, b, c, d):
    # two-sided Fisher exact test for [[a, b], [c, d]]
    row1, row2, col1 = a + b, c + d, a + c
    n = row1 + row2

    def logp(x):
        return (math.lgamma(row1 + 1) - math.lgamma(x + 1) - math.lgamma(row1 - x + 1)
                + math.lgamma(row2 + 1) - math.lgamma(col1 - x + 1) - math.lgamma(row2 - col1 + x + 1)
                - math.lgamma(n + 1) + math.lgamma(col1 + 1) + math.lgamma(n - col1 + 1))
    observed = logp(a)
    lo, hi = max(0, col1 - row2), min(row1, col1)
    return min(1.0, sum(math.exp(logp(x)) for x in range(lo, hi + 1) if logp(x) <= observed + 1e-9))


def stats(conn):
    rows = db.rows(conn, "SELECT ts, trigger, context, arm, policy, status FROM nudges ORDER BY ts")
    resolved = [r for r in rows if r["status"] in ("success", "failure")]
    groups = {}
    for policy in ("bandit", "random"):
        g = [r for r in resolved if r["policy"] == policy]
        s = sum(1 for r in g if r["status"] == "success")
        lo, hi = wilson(s, len(g))
        groups[policy] = {"nudges": len(g), "successes": s,
                          "success_rate": round(s / len(g), 3) if g else None,
                          "ci95": [round(lo, 3), round(hi, 3)] if g else None}
    b, r_ = groups["bandit"], groups["random"]
    p = None
    if b["nudges"] and r_["nudges"]:
        p = round(fisher_exact(b["successes"], b["nudges"] - b["successes"],
                               r_["successes"], r_["nudges"] - r_["successes"]), 4)

    # running success rate of each group, for the chart
    series, seen = [], {"bandit": [0, 0], "random": [0, 0]}
    for r in resolved:
        seen[r["policy"]][0] += r["status"] == "success"
        seen[r["policy"]][1] += 1
        series.append({"ts": r["ts"],
                       "bandit": round(seen["bandit"][0] / seen["bandit"][1], 3) if seen["bandit"][1] else None,
                       "random": round(seen["random"][0] / seen["random"][1], 3) if seen["random"][1] else None})

    bandit = Bandit.from_db(conn)
    contexts = sorted({r["context"] for r in rows})
    return {
        "total_nudges": len(rows),
        "pending": sum(1 for r in rows if r["status"] == "pending"),
        "unknown_outcome": sum(1 for r in rows if r["status"] == "unknown"),
        "groups": groups,
        "fisher_p_value": p,
        "series": series[-400:],
        "arms_by_context": {c: bandit.summary(c) for c in contexts},
        "definition": ("success = no habit contact (or no doomscrolling) from " + str(config.NUDGE_GRACE_SECONDS)
                       + " s to " + str(config.NUDGE_OUTCOME_MINUTES) + " min after the nudge"),
    }
