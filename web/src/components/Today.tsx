import { useState } from "react";
import { Patterns, Progress, Status, Timeline } from "../api";
import { api } from "../api";
import { useData } from "../hooks";
import { BEHAVIOR_NAMES, contextPhrase, isoDate, minutesText, pct } from "../labels";
import { Card } from "./Card";
import { ArrowRight } from "./Icons";
import { roundedTop } from "./RateBars";
import { TimelineChart } from "./Timeline";

export function TodayPage({ status, progress, onAsk, onPatterns, tick }: {
  status: Status | null;
  progress: Progress | null;
  onAsk: (q: string) => void;
  onPatterns: () => void;
  tick: number;
}) {
  const patterns = useData<Patterns>(() => api.patterns("any", 28), [tick]);
  const nudges = useData(api.nudges, [tick]);
  const now = progress?.now ?? status?.now ?? Date.now() / 1000;
  const hour = new Date(now * 1000).getHours();
  const greeting = hour < 5 ? "Still up?" : hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";

  return (
    <>
      <header className="page-head">
        <div className="eyebrow">{new Date(now * 1000).toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" })}</div>
        <h1>{greeting}</h1>
      </header>
      {status && !status.has_data && (
        <p className="warn-box">No habit events yet. Run <code>python tracker.py --model</code>, or try <code>python -m backend.server --demo</code>.</p>
      )}
      <Headline data={patterns.data} onAsk={onAsk} onPatterns={onPatterns} />
      {progress && <ProgressTiles p={progress} nudgeRate={nudges.data?.groups.bandit.success_rate ?? null}
                                  randomRate={nudges.data?.groups.random.success_rate ?? null} />}
      {progress && <DayCard key={isoDate(now)} date={isoDate(now)} tick={tick} />}
    </>
  );
}

function Headline({ data, onAsk, onPatterns }: { data: Patterns | null; onAsk: (q: string) => void; onPatterns: () => void }) {
  if (!data) return <section className="headline loading" aria-busy="true" />;
  const top = data.patterns.find((p) => p.direction === "higher") ?? data.patterns[0];
  if (!top) {
    return (
      <section className="headline">
        <div className="eyebrow">Your biggest pattern</div>
        <p className="headline-text">Not enough data for patterns yet.</p>
        <p className="headline-meta">Keep the webcam and window tracker running. Patterns need at least a few days.</p>
      </section>
    );
  }
  const habit = top.behavior === "any" ? "Habits are" : BEHAVIOR_NAMES[top.behavior] + " is";
  const phrase = contextPhrase(top.context);
  return (
    <section className="headline">
      <div className="eyebrow">Your biggest pattern · last 28 days</div>
      <p className="headline-text">
        {habit} <span className="headline-ratio">{top.rate_ratio_vs_rest}×</span>{" "}
        {top.direction === "higher" ? "more" : "less"} frequent {phrase}.
      </p>
      <p className="headline-meta">
        {top.events} events where {top.expected_events} were expected · {top.observed_hours} h watched · 95% CI{" "}
        {top.ci95?.join("–")}× · an association, not a cause
      </p>
      <div className="headline-actions">
        <button className="primary" onClick={() => onAsk("Tell me more about my " + (BEHAVIOR_NAMES[top.behavior] ?? "habits").toLowerCase() + " " + phrase + ".")}>
          Ask about this <ArrowRight />
        </button>
        <button className="ghost" onClick={onPatterns}>See all {data.patterns.length} patterns</button>
      </div>
    </section>
  );
}

function Delta({ change, unit }: { change: number | null; unit: string }) {
  // fewer habits is the good direction
  if (change == null) return <span className="muted">no comparison yet</span>;
  const better = change < 0;
  const same = Math.abs(change) < 0.03;
  return (
    <span className={"delta " + (same ? "same" : better ? "good" : "worse")}>
      <span aria-hidden="true">{same ? "→" : better ? "↓" : "↑"}</span>{" "}
      {same ? "about the same as " : Math.round(Math.abs(change) * 100) + "% " + (better ? "fewer than " : "more than ")}{unit}
    </span>
  );
}

function ProgressTiles({ p, nudgeRate, randomRate }: { p: Progress; nudgeRate: number | null; randomRate: number | null }) {
  const dayChange = p.yesterday.events ? p.today.events / p.yesterday.events - 1 : null;
  return (
    <div className="tiles four">
      <div className="tile">
        <div className="tile-label">Today</div>
        <div className="tile-value">{p.today.events} <span className="tile-unit">habits</span></div>
        <Delta change={dayChange} unit={"yesterday (" + p.yesterday.events + ")"} />
      </div>
      <div className="tile">
        <div className="tile-label">This week, per watched hour</div>
        <div className="tile-value">{p.this_week.per_hour ?? "–"}</div>
        <Delta change={p.week_change} unit="last week" />
        <WeekBars days={p.days} />
      </div>
      <div className="tile calm">
        <div className="tile-label">Calm streak</div>
        <div className="tile-value">{minutesText(p.calm_streak_minutes)}</div>
        <span className="muted">habit-free watched time · best this week {minutesText(p.best_calm_minutes_this_week)}</span>
      </div>
      <div className="tile">
        <div className="tile-label">Nudges that worked</div>
        <div className="tile-value">{pct(nudgeRate)}</div>
        <span className="muted">{randomRate != null ? "vs " + pct(randomRate) + " for random swaps" : "picked by the bandit"}</span>
      </div>
    </div>
  );
}

function WeekBars({ days }: { days: Progress["days"] }) {
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(...days.map((d) => d.per_hour ?? 0), 0.1);
  const w = 168;
  const h = 34;
  const slot = w / days.length;
  const bw = 14;
  const d = hover != null ? days[hover] : null;
  return (
    <div className="weekbars">
      <svg width={w} height={h + 14} role="img" aria-label="Habits per watched hour, last 7 days" onMouseLeave={() => setHover(null)}>
        {days.map((day, i) => {
          const v = day.per_hour ?? 0;
          const bh = Math.max((v / max) * h, v > 0 ? 3 : 0);
          const x = i * slot + (slot - bw) / 2;
          const label = new Date(day.date + "T12:00:00").toLocaleDateString([], { weekday: "narrow" });
          return (
            <g key={day.date} onMouseEnter={() => setHover(i)}>
              <rect x={i * slot} y={0} width={slot} height={h + 14} fill="transparent" />
              {bh > 0 ? <path d={roundedTop(x, h - bh, bw, bh, 3)} fill={i === days.length - 1 ? "var(--series-1)" : "var(--series-1-soft)"} />
                      : <line x1={x} x2={x + bw} y1={h - 0.5} y2={h - 0.5} className="baseline" />}
              <text x={x + bw / 2} y={h + 12} textAnchor="middle" className="tick">{label}</text>
            </g>
          );
        })}
      </svg>
      <div className="weekbars-tip" aria-live="polite">
        {d ? new Date(d.date + "T12:00:00").toLocaleDateString([], { weekday: "short" }) + ": " +
             (d.per_hour ?? "–") + "/h · " + d.events + " in " + d.observed_hours + " h" : " "}
      </div>
    </div>
  );
}

function DayCard({ date: initial, tick }: { date: string; tick: number }) {
  const [date, setDate] = useState(initial);
  const { data } = useData<Timeline>(() => api.timeline(date), [date, tick]);
  const shift = (n: number) => {
    const d = new Date(date + "T12:00:00");
    d.setDate(d.getDate() + n);
    setDate(isoDate(d.getTime() / 1000));
  };
  return (
    <Card
      wide
      title={date === initial ? "Your day so far" : new Date(date + "T12:00:00").toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" })}
      subtitle="What was on screen, when your hands went to your face, and how the nudges went"
      controls={<>
        <button className="ghost icon" onClick={() => shift(-1)} aria-label="Previous day">←</button>
        <input type="date" value={date} onChange={(e) => e.target.value && setDate(e.target.value)} aria-label="Day" />
        <button className="ghost icon" onClick={() => shift(1)} aria-label="Next day" disabled={date >= initial}>→</button>
      </>}
    >
      {data ? (data.activity.length || data.touches.length ? <TimelineChart data={data} /> : <p className="empty">Nothing logged this day.</p>) : null}
    </Card>
  );
}
