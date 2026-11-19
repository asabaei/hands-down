import { useState } from "react";
import { RateRow } from "../api";
import { describeContext } from "../labels";
import { Tooltip } from "./Tooltip";
import { axis, fmtNum, useMeasure } from "./useMeasure";

// Horizontal bars: habit events per observed hour in each context, with the overall rate
// as a reference line. One series, so no legend box; the card title names it.
export function RateBars({ rows, overall, colorFor }: { rows: RateRow[]; overall: number | null; colorFor?: (ctx: string) => string }) {
  const [ref, width] = useMeasure<HTMLDivElement>();
  const [hover, setHover] = useState<{ i: number; x: number; y: number } | null>(null);
  const shown = rows.slice(0, 12);
  const labelW = Math.min(170, width * 0.35);
  const valueW = 44;
  const rowH = 30;
  const top = 18;
  const height = top + shown.length * rowH + 6;
  const scale = axis(Math.max(overall ?? 0, ...shown.map((r) => r.events_per_hour ?? 0)), 4);
  const max = scale.max;
  const plotW = width - labelW - valueW;
  const x = (v: number) => labelW + (v / max) * plotW;

  if (!shown.length) return <p className="empty">Not enough observed time in any group yet.</p>;
  return (
    <div ref={ref} className="chart" onMouseLeave={() => setHover(null)}>
      <svg width={width} height={height} role="img" aria-label="Habit events per observed hour by context">
        {scale.ticks.map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={top - 4} y2={height - 4} className="grid" />
            <text x={x(t)} y={10} className="tick" textAnchor="middle">
              {fmtNum(t)}
            </text>
          </g>
        ))}
        {shown.map((r, i) => {
          const y = top + i * rowH + 6;
          const w = Math.max(x(r.events_per_hour ?? 0) - labelW, 0);
          const barH = 18;
          return (
            <g key={r.context} onMouseMove={(e) => setHover({ i, x: e.nativeEvent.offsetX, y: e.nativeEvent.offsetY })}>
              <rect x={0} y={y - 6} width={width} height={rowH} fill="transparent" />
              <text x={labelW - 8} y={y + barH / 2 + 4} className="label" textAnchor="end">
                {truncate(describeContext(r.context), 24)}
              </text>
              {w > 0 && (
                <path
                  d={roundedRight(labelW, y, w, barH, 4)}
                  fill={colorFor ? colorFor(r.context) : "var(--series-1)"}
                  opacity={hover && hover.i !== i ? 0.55 : 1}
                />
              )}
              <text x={labelW + w + 6} y={y + barH / 2 + 4} className="value">
                {r.events_per_hour?.toFixed(2)}
              </text>
            </g>
          );
        })}
        {overall != null && (
          <g>
            <line x1={x(overall)} x2={x(overall)} y1={top - 4} y2={height - 4} className="refline" />
            <text x={x(overall) + 4} y={height - 6} className="tick">
              overall {overall.toFixed(2)}
            </text>
          </g>
        )}
      </svg>
      {hover && shown[hover.i] && (
        <Tooltip x={hover.x} y={hover.y} width={width}>
          <RateTip r={shown[hover.i]} />
        </Tooltip>
      )}
    </div>
  );
}

export function RateTip({ r }: { r: RateRow }) {
  return (
    <>
      <strong>{describeContext(r.context)}</strong>
      <div>
        {r.events} events in {r.observed_hours} observed h
      </div>
      <div>{r.events_per_hour?.toFixed(2)} per hour</div>
      {r.rate_ratio_vs_rest != null && r.ci95 && (
        <div className="muted">
          {r.rate_ratio_vs_rest}× the rest of the time (95% CI {r.ci95[0]}–{r.ci95[1]}, p = {r.p_value})
        </div>
      )}
    </>
  );
}

export function RateTable({ rows }: { rows: RateRow[] }) {
  return (
    <table>
      <thead>
        <tr>
          <th>Context</th>
          <th className="num">Events</th>
          <th className="num">Observed h</th>
          <th className="num">Per hour</th>
          <th className="num">vs rest</th>
          <th className="num">95% CI</th>
          <th className="num">p</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.context}>
            <td>{describeContext(r.context)}</td>
            <td className="num">{r.events}</td>
            <td className="num">{r.observed_hours}</td>
            <td className="num">{r.events_per_hour?.toFixed(2)}</td>
            <td className="num">{r.rate_ratio_vs_rest}×</td>
            <td className="num">{r.ci95 ? r.ci95.join("–") : "–"}</td>
            <td className="num">{r.p_value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function truncate(s: string, n: number) {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

// square at the baseline (left), 4px rounded at the data end (right)
export function roundedRight(x: number, y: number, w: number, h: number, r: number) {
  r = Math.min(r, w, h / 2);
  return `M${x},${y} H${x + w - r} Q${x + w},${y} ${x + w},${y + r} V${y + h - r} Q${x + w},${y + h} ${x + w - r},${y + h} H${x} Z`;
}

export function roundedTop(x: number, y: number, w: number, h: number, r: number) {
  r = Math.min(r, h, w / 2);
  return `M${x},${y + h} V${y + r} Q${x},${y} ${x + r},${y} H${x + w - r} Q${x + w},${y} ${x + w},${y + r} V${y + h} Z`;
}
