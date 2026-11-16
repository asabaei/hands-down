import { useState } from "react";
import { Timeline as TL } from "../api";
import { BEHAVIOR_NAMES, CATEGORY_NAMES, categoryColor, fmtTime } from "../labels";
import { Swatch } from "./Card";
import { Tooltip } from "./Tooltip";
import { useMeasure } from "./useMeasure";

// One day, two signals on a shared time axis:
//   lane 1  the focused app/site, colored by category
//   lane 2  habit touches (shape = behavior), over a band showing when the webcam was watching
//   lane 3  nudges (check = worked, cross = didn't)
const SHAPES: Record<string, "circle" | "triangle" | "square"> = {
  nail_biting: "circle", skin_picking: "triangle", eye_rubbing: "square",
};

type Hover = { x: number; y: number; body: React.ReactNode };

export function TimelineChart({ data }: { data: TL }) {
  const [ref, width] = useMeasure<HTMLDivElement>();
  const [hover, setHover] = useState<Hover | null>(null);
  const left = 78;
  const right = 8;
  // zoom to the part of the day that has data
  const times = [...data.activity.flatMap((a) => [a.start, a.end]), ...data.webcam.flat()];
  const startH = times.length ? Math.max(0, Math.floor((Math.min(...times) - data.start) / 3600)) : 8;
  const endH = times.length ? Math.min(24, Math.ceil((Math.max(...times) - data.start) / 3600)) : 20;
  const t0 = data.start + startH * 3600;
  const t1 = data.start + Math.max(endH, startH + 1) * 3600;
  const x = (t: number) => left + ((Math.min(Math.max(t, t0), t1) - t0) / (t1 - t0)) * (width - left - right);
  const lane = { act: 8, touch: 52, nudge: 96 };
  const height = 136;
  const habits = data.touches.filter((t) => t.behavior in SHAPES || (t.behavior === "unclassified" && t.alerted));
  const cats = [...new Set(data.activity.map((a) => (a.idle ? "idle" : a.category)))];
  // hour labels need about 44px each; skip hours on narrow screens so they never overlap
  const pxPerHour = (width - left - right) / Math.max(endH - startH, 1);
  const hourStep = [1, 2, 3, 4, 6].find((s) => s * pxPerHour >= 44) ?? 6;

  const show = (e: React.MouseEvent, body: React.ReactNode) =>
    setHover({ x: e.nativeEvent.offsetX, y: e.nativeEvent.offsetY, body });

  return (
    <>
      <div className="legend">
        {cats
          .sort((a, b) => (CATEGORY_NAMES[a] ?? a).localeCompare(CATEGORY_NAMES[b] ?? b))
          .map((c) => (
            <Swatch key={c} color={categoryColor(c)} label={CATEGORY_NAMES[c] ?? c} />
          ))}
        <span className="legend-sep" />
        {Object.entries(SHAPES).map(([b, s]) => (
          <Swatch key={b} color="var(--text-primary)" shape={s} label={BEHAVIOR_NAMES[b]} />
        ))}
      </div>
      <div ref={ref} className="chart" onMouseLeave={() => setHover(null)}>
        <svg width={width} height={height + 20} role="img" aria-label="Day timeline of apps, habit touches and nudges">
          <text x={0} y={lane.act + 18} className="lane-label">Focused app</text>
          <text x={0} y={lane.touch + 18} className="lane-label">Habits</text>
          <text x={0} y={lane.nudge + 18} className="lane-label">Nudges</text>
          {Array.from({ length: Math.floor((endH - startH) / hourStep) + 1 }, (_, i) => Math.ceil(startH / hourStep) * hourStep + i * hourStep).filter((h) => h <= endH).map((h) => (
            <g key={h}>
              <line x1={x(data.start + h * 3600)} x2={x(data.start + h * 3600)} y1={0} y2={height} className="grid" />
              <text x={x(data.start + h * 3600)} y={height + 14} className="tick" textAnchor="middle">
                {String(h % 24).padStart(2, "0")}:00
              </text>
            </g>
          ))}
          {data.webcam.map(([s, e], i) => (
            <rect key={i} x={x(s)} y={lane.touch} width={Math.max(x(e) - x(s), 1)} height={28} className="watch-band" />
          ))}
          {data.activity.map((a, i) => {
            const cat = a.idle ? "idle" : a.category;
            const w = x(a.end) - x(a.start) - 1;   // 1px surface gap between neighbours
            if (w <= 0) return null;
            return (
              <rect key={i} x={x(a.start)} y={lane.act} width={w} height={28} rx={2} fill={categoryColor(cat)}
                    onMouseMove={(e) =>
                      show(e, <>
                        <strong>{a.domain ?? a.app}</strong>
                        <div>{CATEGORY_NAMES[cat] ?? cat}</div>
                        <div className="muted">
                          {fmtTime(a.start)}–{fmtTime(a.end)} ({Math.round((a.end - a.start) / 60)} min)
                        </div>
                      </>)
                    } />
            );
          })}
          {habits.map((t, i) => {
            const cx = x(t.start);
            const cy = lane.touch + 14;
            const shape = SHAPES[t.behavior] ?? "circle";
            const props = {
              className: "ringed habit-mark",
              onMouseMove: (e: React.MouseEvent) =>
                show(e, <>
                  <strong>{BEHAVIOR_NAMES[t.behavior] ?? "Touch"}</strong>
                  <div>{t.region.replace("_", " / ")}</div>
                  <div className="muted">{fmtTime(t.start)}, {Math.round(t.end - t.start)} s</div>
                </>),
            };
            if (shape === "triangle") return <path key={i} d={`M${cx},${cy - 6} L${cx + 6},${cy + 5} L${cx - 6},${cy + 5} Z`} {...props} />;
            if (shape === "square") return <rect key={i} x={cx - 5} y={cy - 5} width={10} height={10} {...props} />;
            return <circle key={i} cx={cx} cy={cy} r={5} {...props} />;
          })}
          {data.nudges.map((n, i) => {
            const cx = x(n.ts);
            const cy = lane.nudge + 14;
            const ok = n.status === "success";
            const bad = n.status === "failure";
            return (
              <g key={i}
                 onMouseMove={(e) =>
                   show(e, <>
                     <strong>{n.arm.replace("_", " ")}</strong>
                     <div>{n.trigger === "habit" ? "after a habit alert" : "after doomscrolling"}, chosen by {n.policy}</div>
                     <div className="muted">{fmtTime(n.ts)}: {ok ? "✓ behavior stopped" : bad ? "✗ didn't stop" : n.status}</div>
                   </>)
                 }>
                <circle cx={cx} cy={cy} r={8} className={"nudge " + (ok ? "good" : bad ? "critical" : "pending")} />
                <text x={cx} y={cy + 4} textAnchor="middle" className="nudge-icon">{ok ? "✓" : bad ? "✗" : "…"}</text>
              </g>
            );
          })}
        </svg>
        {hover && (
          <Tooltip x={hover.x} y={hover.y} width={width}>
            {hover.body}
          </Tooltip>
        )}
      </div>
      <p className="note">Shaded band: when the webcam was watching. Habit rates only count that time.</p>
    </>
  );
}
