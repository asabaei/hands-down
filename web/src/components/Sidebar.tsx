import { Status } from "../api";
import { Page } from "../hooks";
import { BEHAVIOR_NAMES, CATEGORY_NAMES, ago, categoryColor } from "../labels";
import { NudgeIcon, PatternsIcon, TodayIcon } from "./Icons";
import { Logo } from "./Logo";

const NAV: [Page, string, () => React.ReactElement][] = [
  ["today", "Today", TodayIcon],
  ["patterns", "Patterns", PatternsIcon],
  ["nudges", "Nudges", NudgeIcon],
];

export function Sidebar({ page, setPage, status, lastHabit }: {
  page: Page;
  setPage: (p: Page) => void;
  status: Status | null;
  lastHabit: { ts: number; behavior: string } | null;
}) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <Logo size={40} />
        <div>
          <div className="brand-name">Hands Down</div>
          <div className="brand-tag">habits × screen time</div>
        </div>
      </div>
      <nav className="nav" aria-label="Pages">
        {NAV.map(([p, label, Icon]) => (
          <button key={p} className={"nav-item" + (page === p ? " active" : "")} onClick={() => setPage(p)}
                  aria-current={page === p ? "page" : undefined}>
            <Icon />
            {label}
          </button>
        ))}
      </nav>
      {status && <RightNow status={status} lastHabit={lastHabit} />}
    </aside>
  );
}

function RightNow({ status, lastHabit }: { status: Status; lastHabit: { ts: number; behavior: string } | null }) {
  const cur = status.current_activity;
  const nudge = status.last_nudge;
  return (
    <section className="right-now" aria-label="Right now">
      <div className="eyebrow">
        Right now {status.demo && <span className="demo-badge">demo data</span>}
      </div>
      <Row on={status.trackers.webcam.running} label="Webcam" value={status.trackers.webcam.running ? "watching" : "off"} />
      <Row on={status.trackers.activity.running} label="Screen"
           value={cur ? (cur.domain ?? cur.app) : status.trackers.activity.running ? "tracking" : "off"}
           swatch={cur ? categoryColor(cur.idle ? "idle" : cur.category) : undefined}
           title={cur ? CATEGORY_NAMES[cur.category] : undefined} />
      <Row on={status.llm.ok && status.llm.model_pulled} label="Assistant"
           value={status.llm.ok ? (status.llm.model_pulled ? status.llm.model.split(":")[0] : "model missing") : "offline"} />
      <div className="rn-divider" />
      <div className="rn-fact">
        <span className="rn-label">Last habit</span>
        <span>{lastHabit ? ago(lastHabit.ts, status.now) + " · " + (BEHAVIOR_NAMES[lastHabit.behavior] ?? "touch") : "none yet"}</span>
      </div>
      <div className="rn-fact">
        <span className="rn-label">Last nudge</span>
        <span>
          {nudge ? (
            <>
              {nudge.text}{" "}
              <span className={"rn-outcome " + nudge.status}>
                {nudge.status === "success" ? "✓ worked" : nudge.status === "failure" ? "✗ didn't" : "… waiting"}
              </span>
            </>
          ) : "none yet"}
        </span>
      </div>
    </section>
  );
}

function Row({ on, label, value, swatch, title }: { on: boolean; label: string; value: string; swatch?: string; title?: string }) {
  return (
    <div className="rn-row" title={title}>
      <span className={"dot " + (on ? "on" : "off")} aria-hidden="true" />
      <span className="rn-label">{label}</span>
      <span className="rn-value">
        {swatch && <span className="swatch" style={{ background: swatch }} aria-hidden="true" />}
        {value}
      </span>
    </div>
  );
}
