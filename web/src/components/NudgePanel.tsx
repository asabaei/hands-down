import { NudgeStats } from "../api";
import { BEHAVIOR_NAMES, fmtDate, fmtTime, pct } from "../labels";
import { Card, Swatch } from "./Card";
import { LineChart } from "./LineChart";
import { roundedRight } from "./RateBars";
import { useMeasure } from "./useMeasure";

const contextName = (c: string) =>
  c === "doomscroll" ? "Doomscrolling" : BEHAVIOR_NAMES[c.split(":")[1]] ?? c;

export function NudgePanel({ data }: { data: NudgeStats }) {
  const { bandit, random } = data.groups;
  const sig = data.fisher_p_value != null && data.fisher_p_value < 0.05;
  const step = Math.max(1, Math.floor(data.series.length / 120));
  const series = data.series.filter((_, i) => i % step === 0 || i === data.series.length - 1);
  return (
    <>
      <div className="tiles">
        <div className="tile">
          <div className="tile-label">Bandit's nudges worked</div>
          <div className="tile-value">{pct(bandit.success_rate)}</div>
          <div className="muted">
            {bandit.successes} of {bandit.nudges} · 95% CI {pct(bandit.ci95?.[0])}–{pct(bandit.ci95?.[1])}
          </div>
        </div>
        <div className="tile">
          <div className="tile-label">Random nudges worked</div>
          <div className="tile-value">{pct(random.success_rate)}</div>
          <div className="muted">
            {random.successes} of {random.nudges} · 95% CI {pct(random.ci95?.[0])}–{pct(random.ci95?.[1])}
          </div>
        </div>
        <div className="tile">
          <div className="tile-label">Difference</div>
          <div className="tile-value small">
            {data.fisher_p_value == null ? "–" : sig ? "Significant" : "Not significant yet"}
          </div>
          <div className="muted">
            Fisher exact p = {data.fisher_p_value ?? "–"} · {data.pending} pending · {data.unknown_outcome} unknown
          </div>
        </div>
      </div>
      <p className="note">{data.definition}. A random 20% of nudges are the comparison group.</p>

      <div className="grid2">
        <Card
          title="Success rate so far"
          subtitle="Running share of nudges that worked"
          legend={<>
            <Swatch color="var(--series-1)" label="Bandit" />
            <Swatch color="var(--series-2)" label="Random" />
          </>}
          table={
            <table>
              <thead><tr><th>Group</th><th className="num">Nudges</th><th className="num">Worked</th><th className="num">Rate</th><th className="num">95% CI</th></tr></thead>
              <tbody>
                {(["bandit", "random"] as const).map((g) => (
                  <tr key={g}>
                    <td>{g}</td><td className="num">{data.groups[g].nudges}</td><td className="num">{data.groups[g].successes}</td>
                    <td className="num">{pct(data.groups[g].success_rate)}</td>
                    <td className="num">{pct(data.groups[g].ci95?.[0])}–{pct(data.groups[g].ci95?.[1])}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          }
        >
          <LineChart
            xLabels={series.map((s) => fmtDate(s.ts))}
            series={[
              { key: "bandit", label: "Bandit", color: "var(--series-1)", values: series.map((s) => s.bandit) },
              { key: "random", label: "Random", color: "var(--series-2)", values: series.map((s) => s.random) },
            ]}
            yMax={1}
            yFormat={(v) => Math.round(v * 100) + "%"}
          />
        </Card>
        <Card title="What works for you" subtitle="Bandit's estimate that each swap stops the behavior">
          <div className="arm-groups">
            {Object.entries(data.arms_by_context).map(([ctx, arms]) => (
              <ArmBars key={ctx} title={contextName(ctx)} arms={arms} />
            ))}
            {!Object.keys(data.arms_by_context).length && <p className="empty">No nudges yet.</p>}
          </div>
        </Card>
      </div>

      <Card title="Recent nudges">
        <div className="table-wrap">
          <table>
            <thead><tr><th>When</th><th>Trigger</th><th>Swap</th><th>Chosen by</th><th>Outcome</th></tr></thead>
            <tbody>
              {data.recent.map((n, i) => (
                <tr key={i}>
                  <td>{fmtDate(n.ts)} {fmtTime(n.ts)}</td>
                  <td>{contextName(n.context)}{n.detail ? " · " + n.detail.replace("_", " / ") : ""}</td>
                  <td>{data.arm_text[n.arm] ?? n.arm}</td>
                  <td>{n.policy}</td>
                  <td><Outcome status={n.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}

function Outcome({ status }: { status: string }) {
  if (status === "success") return <span className="status good">✓ stopped</span>;
  if (status === "failure") return <span className="status critical">✗ continued</span>;
  if (status === "pending") return <span className="status muted">… waiting</span>;
  return <span className="status muted">? tracker off</span>;
}

function ArmBars({ title, arms }: { title: string; arms: NudgeStats["arms_by_context"][string] }) {
  const [ref, width] = useMeasure<HTMLDivElement>();
  const labelW = 110;
  const valueW = 92;
  const rowH = 24;
  const plotW = width - labelW - valueW;
  return (
    <div ref={ref} className="arm-group">
      <h3>{title}</h3>
      <svg width={width} height={arms.length * rowH} role="img" aria-label={"Swap success estimates for " + title}>
        {arms.map((a, i) => {
          const y = i * rowH + 4;
          const w = Math.max(a.posterior_mean * plotW, 2);
          return (
            <g key={a.arm}>
              <title>{a.text}: {a.successes} worked, {a.failures} didn't</title>
              <text x={labelW - 8} y={y + 12} className="label" textAnchor="end">{a.arm.replace("_", " ")}</text>
              <path d={roundedRight(labelW, y, w, 16, 4)} fill={i === 0 ? "var(--series-1)" : "var(--series-1-soft)"} />
              <text x={labelW + w + 6} y={y + 12} className="value">
                {pct(a.posterior_mean)} <tspan className="muted">({a.successes}/{a.successes + a.failures})</tspan>
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
