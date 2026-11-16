import { useState } from "react";
import { Patterns } from "../api";
import { BEHAVIOR_NAMES, confidence, describeContext, patternStats, plainCount } from "../labels";
import { Tip } from "./Tip";

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
                {plainCount(p.events, p.expected_events)} ·{" "}
                <Tip tip={patternStats(p)} className={"conf " + confidence(p.q_value).level}>{confidence(p.q_value).label}</Tip>
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
        Patterns are things that happen together, not proof that one causes the other.
      </p>
    </>
  );
}
