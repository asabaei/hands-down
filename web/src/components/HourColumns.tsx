import { useState } from "react";
import { RateRow } from "../api";
import { roundedTop } from "./RateBars";
import { Tooltip } from "./Tooltip";
import { axis, fmtNum, useMeasure } from "./useMeasure";

// 24 columns, habit events per observed hour at each hour of the day
export function HourColumns({ rows }: { rows: RateRow[] }) {
  const [ref, width] = useMeasure<HTMLDivElement>();
  const [hover, setHover] = useState<{ h: number; x: number; y: number } | null>(null);
  const byHour = new Map(rows.map((r) => [Number(r.context.split("=")[1]), r]));
  const height = 180;
  const left = 32;
  const bottom = 22;
  const plotH = height - bottom - 8;
  const scale = axis(Math.max(...rows.map((r) => r.events_per_hour ?? 0), 0.1), 4);
  const max = scale.max;
  const slot = (width - left) / 24;
  const barW = Math.min(18, slot - 2);
  const y = (v: number) => 8 + plotH - (v / max) * plotH;
  return (
    <div ref={ref} className="chart" onMouseLeave={() => setHover(null)}>
      <svg width={width} height={height} role="img" aria-label="Habit events per observed hour by hour of day">
        {scale.ticks.map((t) => (
          <g key={t}>
            <line x1={left} x2={width} y1={y(t)} y2={y(t)} className="grid" />
            <text x={left - 6} y={y(t) + 4} className="tick" textAnchor="end">
              {fmtNum(t)}
            </text>
          </g>
        ))}
        {Array.from({ length: 24 }, (_, h) => {
          const r = byHour.get(h);
          const cx = left + h * slot + slot / 2;
          const v = r?.events_per_hour ?? 0;
          return (
            <g key={h} onMouseMove={(e) => setHover({ h, x: e.nativeEvent.offsetX, y: e.nativeEvent.offsetY })}>
              <rect x={cx - slot / 2} y={0} width={slot} height={height} fill="transparent" />
              {r && v > 0 && (
                <path d={roundedTop(cx - barW / 2, y(v), barW, 8 + plotH - y(v), 4)} fill="var(--series-1)"
                      opacity={hover && hover.h !== h ? 0.55 : 1} />
              )}
              {h % 3 === 0 && (
                <text x={cx} y={height - 6} className="tick" textAnchor="middle">
                  {String(h).padStart(2, "0")}
                </text>
              )}
            </g>
          );
        })}
        <line x1={left} x2={width} y1={8 + plotH} y2={8 + plotH} className="baseline" />
      </svg>
      {hover && (
        <Tooltip x={hover.x} y={hover.y} width={width}>
          <strong>
            {String(hover.h).padStart(2, "0")}:00–{String((hover.h + 1) % 24).padStart(2, "0")}:00
          </strong>
          {byHour.get(hover.h) ? (
            <>
              <div>{byHour.get(hover.h)!.events_per_hour?.toFixed(2)} events per observed hour</div>
              <div className="muted">
                {byHour.get(hover.h)!.events} events in {byHour.get(hover.h)!.observed_hours} h
              </div>
            </>
          ) : (
            <div className="muted">less than 30 observed minutes</div>
          )}
        </Tooltip>
      )}
    </div>
  );
}
