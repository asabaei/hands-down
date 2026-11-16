import { useState } from "react";
import { Patterns } from "../api";
import { BEHAVIOR_NAMES, describeContext } from "../labels";

// The deterministic pattern search (no LLM involved): contexts where a habit is
// significantly more or less frequent than the rest of the observed time.
export function PatternList({ data }: { data: Patterns }) {
  const [all, setAll] = useState(false);
  if (!data.patterns.length) return <p className="empty">{data.note}</p>;
  return (
    <>
      <ol className="patterns">
        {(all ? data.patterns : data.patterns.slice(0, 6)).map((p) => (
          <li key={p.behavior + p.context}>
            <span className={"ratio " + p.direction}>
              {p.direction === "higher" ? "▲" : "▼"} {p.rate_ratio_vs_rest}×
            </span>
            <div>
              <div className="pattern-title">
                {BEHAVIOR_NAMES[p.behavior]} {p.direction === "higher" ? "more often" : "less often"}:{" "}
                <strong>{describeContext(p.context)}</strong>
              </div>
              <div className="muted">
                {p.events} events where {p.expected_events} were expected, in {p.observed_hours} observed h ·
                95% CI {p.ci95?.join("–")}× · q {p.q_value < 0.001 ? "< 0.001" : "= " + p.q_value}
              </div>
            </div>
          </li>
        ))}
      </ol>
      {data.patterns.length > 6 && (
        <button className="ghost" onClick={() => setAll(!all)}>
          {all ? "Show fewer" : "Show all " + data.patterns.length}
        </button>
      )}
      <p className="note">
        {data.tested} contexts tested, false discovery rate 10%. Associations, not causes.
      </p>
    </>
  );
}
