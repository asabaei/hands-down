import { useEffect, useState } from "react";
import { api, Behavior, NudgeStats, Patterns, Progress, Rates, Status, TrendRow } from "./api";
import { Card, Select } from "./components/Card";
import { Companion } from "./components/Companion";
import { HourColumns } from "./components/HourColumns";
import { LineChart } from "./components/LineChart";
import { NudgePanel } from "./components/NudgePanel";
import { PatternList } from "./components/PatternList";
import { RateBars, RateTable } from "./components/RateBars";
import { Sidebar } from "./components/Sidebar";
import { TodayPage } from "./components/Today";
import { usePage, useData } from "./hooks";
import { BEHAVIOR_NAMES, CATEGORY_NAMES, categoryColor, DIMENSION_NAMES, fmtDate } from "./labels";

const BEHAVIORS: [Behavior, string][] = Object.entries(BEHAVIOR_NAMES) as [Behavior, string][];
const RANGES: [string, string][] = [["7", "Last 7 days"], ["28", "Last 28 days"], ["0", "All time"]];
const GROUPS: [string, string][] = [
  ["category", DIMENSION_NAMES.category], ["where", DIMENSION_NAMES.where], ["daypart", DIMENSION_NAMES.daypart],
  ["streak", DIMENSION_NAMES.streak], ["daytype", DIMENSION_NAMES.daytype], ["where,daypart", "App or site × time of day"],
];

export default function App() {
  const [page, setPage] = usePage();
  const [tick, setTick] = useState(0);
  const [ask, setAsk] = useState<{ question: string; id: number } | null>(null);
  const [chatOpen, setChatOpen] = useState(() => window.location.hash === "#ask");   // old links to the Ask page

  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 15000);   // live refresh
    return () => clearInterval(id);
  }, []);

  const status = useData<Status>(api.status, [tick]);
  const progress = useData<Progress>(api.progress, [tick]);

  return (
    <div className="app">
      <Sidebar page={page} setPage={setPage} status={status.data} lastHabit={progress.data?.last_habit ?? null} />
      <main className="main">
        {status.error && <p className="warn-box">Can't reach the API. Is <code>python -m backend.server</code> running?</p>}
        {page === "today" && (
          <TodayPage status={status.data} progress={progress.data} tick={tick}
                     onAsk={(q) => { setAsk({ question: q, id: Date.now() }); setChatOpen(true); }}
                     onPatterns={() => setPage("patterns")} />
        )}
        {page === "patterns" && <PatternsPage tick={tick} />}
        {page === "nudges" && <NudgesPage tick={tick} />}
      </main>
      <Companion status={status.data} ask={ask} open={chatOpen} setOpen={setChatOpen} />
    </div>
  );
}

function PatternsPage({ tick }: { tick: number }) {
  const [range, setRange] = useState("28");
  const [behavior, setBehavior] = useState<Behavior>("any");
  const [groupBy, setGroupBy] = useState("category");
  const days = range === "0" ? null : Number(range);
  return (
    <>
      <header className="page-head">
        <div className="eyebrow">Patterns</div>
        <h1>Where and when it happens</h1>
        <p className="lede">Every rate is habits per hour the webcam was watching, compared with the rest of your watched time.</p>
        <div className="filters">
          <Select label="Time range" value={range} onChange={setRange} options={RANGES} />
          <Select label="Behavior" value={behavior} onChange={setBehavior} options={BEHAVIORS} />
        </div>
      </header>
      <div className="grid2">
        <RatesCard days={days} behavior={behavior} groupBy={groupBy} setGroupBy={setGroupBy} tick={tick} />
        <PatternsCard days={days} behavior={behavior} tick={tick} />
      </div>
      <div className="grid2">
        <HourCard days={days} behavior={behavior} tick={tick} />
        <TrendCard days={days} behavior={behavior} tick={tick} />
      </div>
    </>
  );
}

function RatesCard(props: { days: number | null; behavior: Behavior; groupBy: string; setGroupBy: (g: string) => void; tick: number }) {
  const { data } = useData<Rates>(() => api.rates(props.groupBy, props.behavior, props.days), [props.groupBy, props.behavior, props.days, props.tick]);
  const colorFor = props.groupBy === "category" ? (ctx: string) => categoryColor(ctx.split("=")[1]) : undefined;
  return (
    <Card
      title={BEHAVIOR_NAMES[props.behavior] + " per watched hour"}
      subtitle={"By " + (GROUPS.find((g) => g[0] === props.groupBy)?.[1] ?? "").toLowerCase() + ". Hover a bar to compare it with the rest of the time."}
      controls={<Select label="Group by" value={props.groupBy} onChange={props.setGroupBy} options={GROUPS} />}
      table={data ? <RateTable rows={data.groups} /> : undefined}
    >
      {data && <RateBars rows={data.groups} overall={data.overall_events_per_hour} colorFor={colorFor} />}
      {props.groupBy === "category" && data && (
        <p className="note">Bar colors match the app categories on the day timeline: {data.groups.slice(0, 4).map((g) => CATEGORY_NAMES[g.context.split("=")[1]] ?? g.context).join(", ")}…</p>
      )}
    </Card>
  );
}

function PatternsCard({ days, behavior, tick }: { days: number | null; behavior: Behavior; tick: number }) {
  const { data } = useData<Patterns>(() => api.patterns(behavior, days), [behavior, days, tick]);
  return (
    <Card title="Patterns found" subtitle="Tested across both signals, corrected for multiple comparisons">
      {data && <PatternList data={data} />}
    </Card>
  );
}

function HourCard({ days, behavior, tick }: { days: number | null; behavior: Behavior; tick: number }) {
  const { data } = useData<Rates>(() => api.rates("hour", behavior, days), [behavior, days, tick]);
  return (
    <Card title="By hour of day" subtitle={BEHAVIOR_NAMES[behavior] + " per watched hour"}
          table={data ? <RateTable rows={[...data.groups].sort((a, b) => Number(a.context.split("=")[1]) - Number(b.context.split("=")[1]))} /> : undefined}>
      {data && <HourColumns rows={data.groups} />}
    </Card>
  );
}

function TrendCard({ days, behavior, tick }: { days: number | null; behavior: Behavior; tick: number }) {
  const { data } = useData<{ rows: TrendRow[] }>(() => api.trend(behavior, days), [behavior, days, tick]);
  const rows = data?.rows ?? [];
  return (
    <Card
      title="Day by day"
      subtitle={BEHAVIOR_NAMES[behavior] + " per watched hour"}
      table={
        <table>
          <thead><tr><th>Day</th><th className="num">Events</th><th className="num">Watched h</th><th className="num">Per hour</th></tr></thead>
          <tbody>{rows.map((r) => <tr key={r.period}><td>{r.period}</td><td className="num">{r.events}</td><td className="num">{r.observed_hours}</td><td className="num">{r.events_per_hour ?? "–"}</td></tr>)}</tbody>
        </table>
      }
    >
      <LineChart
        xLabels={rows.map((r) => fmtDate(new Date(r.period + "T12:00:00").getTime() / 1000))}
        series={[{ key: "rate", label: "Per watched hour", color: "var(--series-1)", values: rows.map((r) => r.events_per_hour) }]}
        tip={(i) => <><div>{rows[i].events_per_hour ?? "–"} per watched hour</div><div className="muted">{rows[i].events} events in {rows[i].observed_hours} h</div></>}
      />
    </Card>
  );
}

function NudgesPage({ tick }: { tick: number }) {
  const { data } = useData<NudgeStats>(api.nudges, [tick]);
  return (
    <>
      <header className="page-head">
        <div className="eyebrow">Nudges</div>
        <h1>What actually helps</h1>
        <p className="lede">
          When a habit starts or you've been scrolling for a while, Hands Down suggests a swap. A bandit learns which swaps
          work for you, and a random 20% of nudges keep it honest.
        </p>
      </header>
      {data && <NudgePanel data={data} />}
    </>
  );
}
