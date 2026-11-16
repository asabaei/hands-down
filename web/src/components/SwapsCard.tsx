import { FormEvent, useEffect, useState } from "react";
import { api, Swap, SwapList } from "../api";
import { Card } from "./Card";

export const SWAPS_CHANGED = "handsdown:swaps-changed";   // fired when Pip changes a swap from the chat

// Your swaps: switch them on and off, reword them, choose when they're suggested, or add your own.
// Pip's advice (from how often each swap actually worked) shows at the top.
// part="advice": just Pip's suggestion (shown near the top of the Nudges page)
// part="editor": the list of swaps and the "add your own" box (inside a folded section)
export function SwapsCard({ part = "all" }: { part?: "all" | "advice" | "editor" }) {
  const [data, setData] = useState<SwapList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [allAdvice, setAllAdvice] = useState(false);
  const [dismissed, setDismissed] = useState<string[]>(() => JSON.parse(localStorage.getItem("handsdown.dismissedAdvice") ?? "[]"));

  const load = () => api.swaps().then(setData).catch((e) => setError(String(e.message ?? e)));
  useEffect(() => {
    load();
    window.addEventListener(SWAPS_CHANGED, load);
    return () => window.removeEventListener(SWAPS_CHANGED, load);
  }, []);

  const run = async (p: Promise<SwapList>) => {
    try {
      setData(await p);
      setError(null);
      window.dispatchEvent(new Event(SWAPS_CHANGED));   // keep the other part in sync
    } catch (e) {
      setError(String((e as Error).message));
    }
  };
  const dismiss = (id: string) => {
    const next = [...dismissed, id];
    setDismissed(next);
    localStorage.setItem("handsdown.dismissedAdvice", JSON.stringify(next));
  };

  if (!data) return part === "all" ? <Card title="Your swaps">{error ? <p className="warn-box">{error}</p> : null}</Card> : null;
  const advice = data.advice.filter((a) => !dismissed.includes(a.key + ":" + a.tried));
  const on = data.swaps.filter((s) => s.active).length;

  if (part === "advice") {
    const a = advice[0];
    return a ? (
      <div className="advice">
        <div className="eyebrow">Pip noticed</div>
        <p>{a.message}</p>
        <div className="advice-actions">
          <button className="primary small" onClick={() => run(api.updateSwap(a.key, { active: false }))}>Pause it</button>
          <button className="ghost" onClick={() => dismiss(a.key + ":" + a.tried)}>Keep it</button>
        </div>
      </div>
    ) : null;
  }
  if (part === "editor") {
    return (
      <>
        <p className="muted fold-hint">{on} switched on. Click a swap to reword it, or just ask Pip.</p>
        {error && <p className="warn-box">{error}</p>}
        <ul className="swap-list">{data.swaps.map((s) => <SwapRow key={s.key} swap={s} run={run} />)}</ul>
        <AddSwap run={run} />
      </>
    );
  }

  return (
    <Card title="Your swaps"
          subtitle={`What a nudge can suggest. ${on} switched on. Turn them on or off, reword them, or add your own. You can also just ask Pip.`}>
      {(allAdvice ? advice : advice.slice(0, 1)).map((a) => (
        <div key={a.key} className="advice">
          <div className="eyebrow">Pip noticed</div>
          <p>{a.message}</p>
          <div className="advice-actions">
            <button className="primary small" onClick={() => run(api.updateSwap(a.key, { active: false }))}>Pause it</button>
            <button className="ghost" onClick={() => dismiss(a.key + ":" + a.tried)}>Keep it</button>
          </div>
        </div>
      ))}
      {!allAdvice && advice.length > 1 && (
        <button className="more-advice" onClick={() => setAllAdvice(true)}>
          Pip has {advice.length - 1} more suggestion{advice.length > 2 ? "s" : ""}
        </button>
      )}
      {error && <p className="warn-box">{error}</p>}
      <ul className="swap-list">
        {data.swaps.map((s) => <SwapRow key={s.key} swap={s} run={run} />)}
      </ul>
      <AddSwap run={run} />
    </Card>
  );
}

function SwapRow({ swap: s, run }: { swap: Swap; run: (p: Promise<SwapList>) => void }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(s.text);
  const save = (e: FormEvent) => {
    e.preventDefault();
    if (text.trim() && text.trim() !== s.text) run(api.updateSwap(s.key, { text: text.trim() }));
    setEditing(false);
  };
  return (
    <li className={"swap" + (s.active ? "" : " off")}>
      <button className={"switch" + (s.active ? " on" : "")} role="switch" aria-checked={s.active}
              aria-label={(s.active ? "Switch off: " : "Switch on: ") + s.text}
              onClick={() => run(api.updateSwap(s.key, { active: !s.active }))}>
        <span />
      </button>
      <div className="swap-main">
        {editing ? (
          <form onSubmit={save} className="swap-edit">
            <input value={text} onChange={(e) => setText(e.target.value)} autoFocus aria-label="Swap wording"
                   onKeyDown={(e) => e.key === "Escape" && (setText(s.text), setEditing(false))} />
            <button className="primary small" type="submit">Save</button>
          </form>
        ) : (
          <button className="swap-text" onClick={() => setEditing(true)} title="Click to reword">{s.text}</button>
        )}
        <div className="swap-when">
          <span className="muted">Suggest after</span>
          <button className={"tag-toggle" + (s.habit ? " on" : "")} aria-pressed={s.habit}
                  onClick={() => run(api.updateSwap(s.key, { habit: !s.habit }))}>habits</button>
          <button className={"tag-toggle" + (s.doomscroll ? " on" : "")} aria-pressed={s.doomscroll}
                  onClick={() => run(api.updateSwap(s.key, { doomscroll: !s.doomscroll }))}>scrolling</button>
          {s.added_by !== "default" && <span className="mine">your own</span>}
        </div>
      </div>
      <div className="swap-result" title={s.tried ? `Worked ${s.worked} of ${s.tried} times` : "Not tried yet"}>
        {s.tried ? (
          <>
            <span className="swap-rate">{Math.round((s.rate ?? 0) * 100)}%</span>
            <span className="swap-bar"><span style={{ width: Math.max(4, (s.rate ?? 0) * 100) + "%" }} /></span>
            <span className="muted">{s.worked} of {s.tried}</span>
          </>
        ) : <span className="muted">not tried yet</span>}
      </div>
    </li>
  );
}

function AddSwap({ run }: { run: (p: Promise<SwapList>) => void }) {
  const [text, setText] = useState("");
  const [habit, setHabit] = useState(true);
  const [doomscroll, setDoomscroll] = useState(false);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!text.trim()) return;
    run(api.addSwap({ text: text.trim(), habit, doomscroll }));
    setText("");
  };
  return (
    <form className="add-swap" onSubmit={submit}>
      <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Add your own, e.g. Put on some hand lotion"
             aria-label="New swap" />
      <div className="swap-when">
        <span className="muted">after</span>
        <button type="button" className={"tag-toggle" + (habit ? " on" : "")} aria-pressed={habit} onClick={() => setHabit(!habit)}>habits</button>
        <button type="button" className={"tag-toggle" + (doomscroll ? " on" : "")} aria-pressed={doomscroll}
                onClick={() => setDoomscroll(!doomscroll)}>scrolling</button>
      </div>
      <button className="primary small" type="submit" disabled={!text.trim() || (!habit && !doomscroll)}>Add</button>
    </form>
  );
}
