# Simulated users, to see how the bandit should behave before trusting real numbers.
#
#   python -m evals.bandit_sim --nudges 300 --runs 200
#
# Each simulated user has a true chance that each swap stops the behavior (true_success() in
# synthetic.py, plus random per-user noise so the best swap differs from user to user). Every
# run uses the real Bandit class with the same 20% random group as the app, and reports:
#   - success rate of the bandit's nudges vs the random group's nudges in that run
#   - how often the difference is significant (Fisher p < 0.05) at a few sample sizes,
#     i.e. how many nudges you need before the real-data comparison means anything
#   - the best possible rate (always using the user's truly best swap)
# These are simulations, not results. They only show what the method can detect.

import argparse
import random

import config
from backend import bandit
from evals.synthetic import true_success


def simulate(rng, n_nudges, noise):
    truth = {t: {a: min(0.95, max(0.05, true_success(t, a) + rng.gauss(0, noise))) for a in arms}
             for t, arms in config.NUDGE_ARMS_BY_TRIGGER.items()}
    policy = bandit.Bandit(seed=rng.randrange(1 << 30))
    contexts = [("habit", "habit:skin_picking"), ("habit", "habit:nail_biting"),
                ("habit", "habit:eye_rubbing"), ("doomscroll", "doomscroll")]
    log = []
    best = []
    for _ in range(n_nudges):
        trigger, context = rng.choice(contexts)
        arm, who = policy.choose(trigger, context)
        success = rng.random() < truth[trigger][arm]
        policy.update(context, arm, success)
        log.append((who, success))
        best.append(max(truth[trigger].values()))
    return log, sum(best) / len(best)


def rates(log):
    out = {}
    for who in ("bandit", "random"):
        g = [s for w, s in log if w == who]
        out[who] = (sum(g), len(g))
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--nudges", type=int, default=300)
    parser.add_argument("--runs", type=int, default=200)
    parser.add_argument("--noise", type=float, default=0.1, help="per-user spread of the true swap success rates")
    args = parser.parse_args()
    rng = random.Random(0)
    checkpoints = [50, 100, 200, 300, 500]
    checkpoints = [c for c in checkpoints if c <= args.nudges]
    sig = {c: 0 for c in checkpoints}
    bandit_rates, random_rates, best_rates = [], [], []
    for _ in range(args.runs):
        log, best = simulate(rng, args.nudges, args.noise)
        for c in checkpoints:
            r = rates(log[:c])
            (bs, bn), (rs, rn) = r["bandit"], r["random"]
            if bn and rn and bs / bn > rs / rn and bandit.fisher_exact(bs, bn - bs, rs, rn - rs) < 0.05:
                sig[c] += 1
        r = rates(log)
        bandit_rates.append(r["bandit"][0] / max(r["bandit"][1], 1))
        random_rates.append(r["random"][0] / max(r["random"][1], 1))
        best_rates.append(best)
    mean = lambda xs: sum(xs) / len(xs)
    print("simulated users:", args.runs, " nudges each:", args.nudges,
          " random share:", config.NUDGE_RANDOM_FRACTION)
    print("bandit nudges success:  " + str(round(mean(bandit_rates) * 100, 1)) + "%")
    print("random nudges success:  " + str(round(mean(random_rates) * 100, 1)) + "%")
    print("best possible (oracle): " + str(round(mean(best_rates) * 100, 1)) + "%")
    print("share of users where bandit > random is significant (Fisher p < 0.05):")
    for c in checkpoints:
        print("  after " + str(c).rjust(3) + " nudges: " + str(round(sig[c] / args.runs * 100)) + "%")


if __name__ == "__main__":
    main()
