import { ReactNode, useState } from "react";

// A chart card with a title, optional controls, and a "Table" toggle so every chart's
// numbers are readable without the chart.
export function Card(props: {
  title: string;
  subtitle?: string;
  controls?: ReactNode;
  table?: ReactNode;
  legend?: ReactNode;
  children: ReactNode;
  wide?: boolean;
}) {
  const [showTable, setShowTable] = useState(false);
  return (
    <section className={"card" + (props.wide ? " wide" : "")}>
      <header className="card-head">
        <div>
          <h2>{props.title}</h2>
          {props.subtitle && <p className="subtitle">{props.subtitle}</p>}
        </div>
        <div className="card-controls">
          {props.controls}
          {props.table && (
            <button className="ghost" onClick={() => setShowTable(!showTable)} aria-pressed={showTable}>
              {showTable ? "Chart" : "Table"}
            </button>
          )}
        </div>
      </header>
      {props.legend && !showTable && <div className="legend">{props.legend}</div>}
      {showTable ? <div className="table-wrap">{props.table}</div> : props.children}
    </section>
  );
}

export function Swatch({ color, label, shape }: { color: string; label: string; shape?: "circle" | "square" | "triangle" | "bar" }) {
  return (
    <span className="legend-item">
      <svg width="12" height="12" aria-hidden="true">
        {shape === "circle" && <circle cx="6" cy="6" r="4.5" fill={color} />}
        {shape === "triangle" && <path d="M6 1.5 L10.5 10.5 L1.5 10.5 Z" fill={color} />}
        {shape === "square" && <rect x="2" y="2" width="8" height="8" fill={color} />}
        {(!shape || shape === "bar") && <rect x="0" y="2" width="12" height="8" rx="2" fill={color} />}
      </svg>
      {label}
    </span>
  );
}

export function Select<T extends string>(props: { value: T; onChange: (v: T) => void; options: [T, string][]; label: string }) {
  return (
    <label className="select">
      <span className="sr-only">{props.label}</span>
      <select value={props.value} onChange={(e) => props.onChange(e.target.value as T)} aria-label={props.label}>
        {props.options.map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </select>
    </label>
  );
}
