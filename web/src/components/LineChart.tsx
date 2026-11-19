import { useState } from "react";
import { Tooltip } from "./Tooltip";
import { axis, fmtNum, useMeasure } from "./useMeasure";

export interface Series {
  key: string;
  label: string;
  color: string;
  values: (number | null)[];
}

// 2px lines on one y-axis, crosshair + tooltip on hover, end labels on each series
export function LineChart(props: {
  xLabels: string[];
  series: Series[];
  yMax?: number;
  yFormat?: (v: number) => string;
  height?: number;
  tip?: (i: number) => React.ReactNode;
}) {
  const [ref, width] = useMeasure<HTMLDivElement>();
  const [hover, setHover] = useState<{ i: number; x: number; y: number } | null>(null);
  const height = props.height ?? 200;
  const left = 38;
  const right = props.series.length > 1 ? 70 : 16;
  const top = 10;
  const bottom = 22;
  const n = props.xLabels.length;
  const fmt = props.yFormat ?? fmtNum;
  const all = props.series.flatMap((s) => s.values.filter((v): v is number => v != null));
  const scale = axis(props.yMax ?? Math.max(...all, 0.1), 4);
  const max = scale.max;
  const x = (i: number) => left + (n <= 1 ? 0 : (i / (n - 1)) * (width - left - right));
  const y = (v: number) => top + (1 - v / max) * (height - top - bottom);
  // date labels need about 56px each; show fewer when the chart is narrow so they never overlap
  const labelEvery = Math.max(1, Math.ceil(n / 6), Math.ceil((n * 56) / Math.max(width - left - right, 1)));

  if (!n) return <p className="empty">No data yet.</p>;
  return (
    <div
      ref={ref}
      className="chart"
      onMouseMove={(e) => {
        const ox = e.nativeEvent.offsetX;
        const i = Math.round(((ox - left) / (width - left - right)) * (n - 1));
        setHover({ i: Math.max(0, Math.min(n - 1, i)), x: ox, y: e.nativeEvent.offsetY });
      }}
      onMouseLeave={() => setHover(null)}
    >
      <svg width={width} height={height} role="img" aria-label={props.series.map((s) => s.label).join(", ")}>
        {scale.ticks.map((t) => (
          <g key={t}>
            <line x1={left} x2={width - right} y1={y(t)} y2={y(t)} className="grid" />
            <text x={left - 6} y={y(t) + 4} className="tick" textAnchor="end">
              {fmt(t)}
            </text>
          </g>
        ))}
        {props.xLabels.map((l, i) =>
          i % labelEvery === 0 ? (
            <text key={i} x={x(i)} y={height - 6} className="tick" textAnchor="middle">
              {l}
            </text>
          ) : null,
        )}
        {hover && <line x1={x(hover.i)} x2={x(hover.i)} y1={top} y2={height - bottom} className="crosshair" />}
        {props.series.map((s) => {
          const pts = s.values.map((v, i) => (v == null ? null : `${x(i)},${y(v)}`)).filter(Boolean);
          const lastI = s.values.map((v, i) => (v == null ? -1 : i)).reduce((a, b) => Math.max(a, b), -1);
          return (
            <g key={s.key}>
              <polyline points={pts.join(" ")} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round"
                        strokeLinecap="round" />
              {lastI >= 0 && (
                <>
                  <circle cx={x(lastI)} cy={y(s.values[lastI]!)} r={4} fill={s.color} className="ringed" />
                  {props.series.length > 1 && (
                    <text x={x(lastI) + 8} y={y(s.values[lastI]!) + 4} className="label">
                      {s.label} {fmt(s.values[lastI]!)}
                    </text>
                  )}
                </>
              )}
              {hover && s.values[hover.i] != null && (
                <circle cx={x(hover.i)} cy={y(s.values[hover.i]!)} r={4} fill={s.color} className="ringed" />
              )}
            </g>
          );
        })}
      </svg>
      {hover && (
        <Tooltip x={hover.x} y={hover.y} width={width}>
          <strong>{props.xLabels[hover.i]}</strong>
          {props.tip
            ? props.tip(hover.i)
            : props.series.map((s) => (
                <div key={s.key}>
                  {s.label}: {s.values[hover.i] == null ? "–" : fmt(s.values[hover.i]!)}
                </div>
              ))}
        </Tooltip>
      )}
    </div>
  );
}
