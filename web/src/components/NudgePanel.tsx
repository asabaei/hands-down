import { ReactNode, useState } from "react";
import { NudgeStats } from "../api";
import { BEHAVIOR_NAMES, fmtDate, fmtTime, pct } from "../labels";
import { Swatch } from "./Card";
import { LineChart } from "./LineChart";
import { Tip } from "./Tip";

// The Nudges page, simplest first: one big answer, your best swaps, Pip's one suggestion,
// and everything else folded away until you want it.

const contextName = (c: string) =>
  c === "doomscroll" ? "Scrolling" : BEHAVIOR_NAMES[c.split(":")[1]] ?? c;

export function NudgePanel({ data, advice, editor }: { data: NudgeStats; advice?: ReactNode; editor?: ReactNode }) {
  const { bandit, random } = data.groups;
  const sig = data.fisher_p_value != null && data.fisher_p_value < 0.05;
  const helped = bandit.successes + random.successes;
  const total = bandit.nudges + random.nudges;
  const overall = total ? helped / total : null;
  const better = (bandit.success_rate ?? 0) > (random.success_rate ?? 0);
  const verdict = random.nudges < 10 ? "Too early to compare with random guesses."
    : sig && better ? "Pip's picks clearly beat random guesses."
    : better ? "Pip's picks are doing a bit better than random guesses."
    : "Pip's picks aren't beating random guesses yet. Pip keeps learning.";
  const step = Math.max(1, Math.floor(data.series.length / 120));
  const series = data.series.filter((_, i) => i % step === 0 || i === data.series.length - 1);
  const swapCount = Object.values(data.arm_text).length;

  return (
    <>
      {/* 1. the one answer */}
      <section className="nudge-hero">
        <div className="nudge-hero-number">{pct(overall)}</div>
        <div>
          <div className="nudge-hero-text">of your nudges helped</div>
          <div className="muted">
            {verdict}{" "}
            <Tip tip={`${helped} of ${total} nudges helped (the habit stopped within 5 minutes). Pip's picks: ${pct(bandit.success_rate)}. Random swaps: ${pct(random.success_rate)}.`}>{""}</Tip>
          </div>
        </div>
      </section>

      {/* 2. Pip's one suggestion, if any */}
      {advice}

      {/* 3. your best swaps */}
      <BestSwaps data={data} />

      {/* 4. everything else, folded */}
      <Fold title="Edit your swaps" hint={`${swapCount} swaps · switch on/off, reword, add your own`}>{editor}</Fold>
      <Fold title="Recent nudges" hint={`last ${Math.min(10, data.recent.length)}`}>
        <ul className="recent">
          {data.recent.slice(0, 10).map((n, i) => (
            <li key={i}>
              <span className="muted">{fmtDate(n.ts)} {fmtTime(n.ts)}</span>
              <span className="recent-swap" title={data.arm_text[n.arm] ?? n.arm}>{data.arm_text[n.arm] ?? n.arm}</span>
              <Outcome status={n.status} />
            </li>
          ))}
        </ul>
      </Fold>
      <Fold title="How does Pip pick swaps?" hint="the science, for the curious">
        <p className="fold-text">
          Pip uses a <em>multi-armed bandit</em> (Thompson sampling): most of the time it suggests the swaps that have worked
          best for you so far, and 1 in 5 times it picks one at random. Comparing the two shows whether Pip's learning really
          helps. A nudge counts as helping when there's no habit (or no doomscrolling) from 1 to 5 minutes after it.
        </p>
        <div className="legend">
          <Swatch color="var(--series-1)" label="Pip's picks" />
          <Swatch color="var(--series-2)" label="Random" />
        </div>
        <LineChart
          xLabels={series.map((s) => fmtDate(s.ts))}
          series={[
            { key: "bandit", label: "Pip's picks", color: "var(--series-1)", values: series.map((s) => s.bandit) },
            { key: "random", label: "Random", color: "var(--series-2)", values: series.map((s) => s.random) },
          ]}
          yMax={1}
          yFormat={(v) => Math.round(v * 100) + "%"}
          height={190}
        />
        <p className="fold-text muted">
          Pip's picks: {bandit.successes} of {bandit.nudges} ({pct(bandit.success_rate)}, 95% CI {pct(bandit.ci95?.[0])}–{pct(bandit.ci95?.[1])}).
          Random: {random.successes} of {random.nudges} ({pct(random.success_rate)}, 95% CI {pct(random.ci95?.[0])}–{pct(random.ci95?.[1])}).
          Fisher exact test p = {data.fisher_p_value ?? "–"} ({sig ? "significant" : "not significant yet"}).
        </p>
      </Fold>
    </>
  );
}

// a section that stays closed until you click it
function Fold({ title, hint, children }: { title: string; hint: string; children: ReactNode }) {
  return (
    <details className="fold">
      <summary>
        <span className="fold-title">{title}</span>
        <span className="muted">{hint}</span>
        <span className="fold-chevron" aria-hidden="true">›</span>
      </summary>
      <div className="fold-body">{children}</div>
    </details>
  );
}

// one card: the top 3 swaps for the habit you pick in the tabs
function BestSwaps({ data }: { data: NudgeStats }) {
  const contexts = Object.keys(data.arms_by_context);
  const [ctx, setCtx] = useState(contexts.find((c) => c.includes("skin")) ?? contexts[0]);
  if (!contexts.length) return null;
  const arms = (data.arms_by_context[ctx] ?? []).slice(0, 3);
  return (
    <section className="card best-swaps">
      <div className="best-head">
        <h2>Your best swaps</h2>
        <div className="tabs-mini" role="tablist" aria-label="Habit">
          {contexts.map((c) => (
            <button key={c} role="tab" aria-selected={c === ctx} className={c === ctx ? "on" : ""} onClick={() => setCtx(c)}>
              {contextName(c)}
            </button>
          ))}
        </div>
      </div>
      <ol className="best-list">
        {arms.map((a, i) => (
          <li key={a.arm}>
            <span className="best-rank">{i + 1}</span>
            <span className="best-name">{a.text}</span>
            <span className="swap-bar"><span style={{ width: Math.max(3, a.posterior_mean * 100) + "%" }} /></span>
            <Tip tip={`Helped ${a.successes} of ${a.successes + a.failures} times. Pip's estimate: ${pct(a.posterior_mean)}.`}>
              <span className="best-pct">{pct(a.posterior_mean)}</span>
            </Tip>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Outcome({ status }: { status: string }) {
  if (status === "success") return <span className="status good">✓ helped</span>;
  if (status === "failure") return <span className="status critical">✗ didn't</span>;
  if (status === "pending") return <span className="status muted">… waiting</span>;
  return <span className="status muted">? tracker off</span>;
}
