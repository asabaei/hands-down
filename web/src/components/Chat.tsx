import { FormEvent, useEffect, useRef, useState } from "react";
import { api, ChatEvent, SwapProposal, ToolCall } from "../api";
import { PipState } from "../pip";
import { PipIntro } from "./PipIntro";
import { SWAPS_CHANGED } from "./SwapsCard";


interface Step {
  label: string;
  done: boolean;
}

interface Turn {
  role: "user" | "assistant";
  content: string;
  status?: string;        // what it's doing right now, while it works
  steps?: Step[];         // tool calls, shown live
  toolCalls?: ToolCall[]; // full trace, once finished
  seconds?: number;
  live?: boolean;
  error?: boolean;
}

export type ChatActivity = "idle" | "thinking" | "talking" | "done";

export function Chat({ llm, initial, onActivity, inputRef, active = true, onPip }: {
  llm?: { ok: boolean; model: string; model_pulled: boolean };
  initial?: { question: string; id: number } | null;   // asked automatically, e.g. from the headline card
  onActivity?: (a: ChatActivity) => void;              // lets the companion change its mood
  inputRef?: React.RefObject<HTMLInputElement | null>;
  active?: boolean;                                    // the chat is visible (Pip's intro waits for this)
  onPip?: (s: PipState | null) => void;                // Pip's intro drives the companion directly
}) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "nearest" });
  }, [turns]);

  // tell the companion what's happening: thinking (no text yet), talking (text streaming), done
  const last = turns[turns.length - 1];
  const activity: ChatActivity = busy ? (last?.content ? "talking" : "thinking") : turns.length ? "done" : "idle";
  useEffect(() => {
    onActivity?.(activity);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activity]);

  useEffect(() => {
    if (initial) ask(initial.question);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial?.id]);

  useEffect(() => {
    if (!busy) return;
    const start = Date.now();
    setElapsed(0);
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 1000);
    return () => clearInterval(id);
  }, [busy]);

  // apply one streamed event to the assistant turn that is being written (always the last one)
  function apply(e: ChatEvent) {
    setTurns((all) => {
      const t = { ...all[all.length - 1] };
      if (e.type === "status") t.status = e.text;
      else if (e.type === "step") {
        t.steps = [...(t.steps ?? []), { label: e.label, done: false }];
        t.status = undefined;
      } else if (e.type === "step_done") {
        t.steps = (t.steps ?? []).map((s, i, arr) => (i === arr.length - 1 ? { ...s, done: true } : s));
      } else if (e.type === "token") {
        t.content += e.text;
        t.status = undefined;
      } else if (e.type === "reset") t.content = "";
      else if (e.type === "done") {
        t.content = e.answer;
        t.toolCalls = e.tool_calls;
        t.seconds = e.seconds;
        t.live = false;
        t.status = undefined;
      } else if (e.type === "error") {
        t.content = e.text;
        t.error = true;
        t.live = false;
        t.status = undefined;
      }
      return [...all.slice(0, -1), t];
    });
  }

  // a swap change waiting for an answer: typing "yes" or "no" answers it like the buttons do
  const pending = useRef<{ yes: () => void; no: () => void } | null>(null);

  async function ask(question: string) {
    if (!question.trim() || busy) return;
    const reply = question.trim().toLowerCase().replace(/[.!]+$/, "");
    if (pending.current && YES.test(reply)) {
      setTurns((t) => [...t, { role: "user", content: question }]);
      setInput("");
      pending.current.yes();
      return;
    }
    if (pending.current && NO.test(reply)) {
      setTurns((t) => [...t, { role: "user", content: question }]);
      setInput("");
      pending.current.no();
      return;
    }
    const history = turns.filter((t) => !t.error).map((t) => ({ role: t.role, content: t.content }));
    setTurns((t) => [...t, { role: "user", content: question },
                     { role: "assistant", content: "", status: "Starting", steps: [], live: true }]);
    setInput("");
    setBusy(true);
    try {
      await api.chatStream(question, history, apply);
    } catch (e) {
      apply({ type: "error", text: String((e as Error).message) });
    } finally {
      setTurns((all) => all.map((t) => (t.live ? { ...t, live: false, status: undefined } : t)));
      setBusy(false);
    }
  }

  const submit = (e: FormEvent) => {
    e.preventDefault();
    ask(input);
  };

  return (
    <div className="chat">
      {llm && !llm.ok && (
        <p className="warn-box">
          <span aria-hidden="true">⚠</span> Ollama isn't running. Start it with <code>ollama serve</code> and pull the
          model with <code>ollama pull {llm.model}</code>.
        </p>
      )}
      {llm && llm.ok && !llm.model_pulled && (
        <p className="warn-box">
          <span aria-hidden="true">⚠</span> Model not pulled yet: <code>ollama pull {llm.model}</code>
        </p>
      )}
      <div className="turns" aria-live="polite">
        {/* Pip's introduction stays at the top of the chat; the question ideas hide once you've asked something */}
        <PipIntro onAsk={ask} showIdeas={!turns.length} active={active} onPip={(st) => onPip?.(st)} />
        {turns.map((t, i) => (
          <div key={i} className={"turn " + t.role + (t.error ? " error" : "")}>
            {t.role === "assistant" && !!t.steps?.length && (
              <ul className="steps">
                {t.steps.map((s, j) => (
                  <li key={j} className={s.done ? "done" : "running"}>
                    <span className="step-icon" aria-hidden="true">{s.done ? "✓" : <span className="spinner" />}</span>
                    {s.label}{s.done ? "" : "…"}
                  </li>
                ))}
              </ul>
            )}
            {t.live && t.status && !t.content && (
              <div className="bubble muted working">
                <span className="spinner" aria-hidden="true" /> {statusText(t)} <span className="elapsed">{elapsed}s</span>
              </div>
            )}
            {t.content && (
              <div className="bubble">
                {t.content}
                {t.live && <span className="cursor" aria-hidden="true" />}
              </div>
            )}
            {!t.live && t.toolCalls?.map((c, j) => {
              const r = c.result as { proposal?: SwapProposal; summary?: string } | null;
              return r?.proposal ? <ProposalCard key={"p" + j} proposal={r.proposal} summary={r.summary ?? ""} pending={pending}
                                                 onDone={() => onActivity?.("done")} /> : null;
            })}
            {!t.live && t.toolCalls && t.toolCalls.length > 0 && (
              <details className="trace">
                <summary>
                  {t.toolCalls.length} tool call{t.toolCalls.length > 1 ? "s" : ""} · {t.seconds}s
                </summary>
                {t.toolCalls.map((c, j) => (
                  <div key={j} className="call">
                    <code>
                      {c.name}({JSON.stringify(c.arguments)})
                    </code>
                    <pre>{JSON.stringify(c.result, null, 1).slice(0, 1500)}</pre>
                  </div>
                ))}
              </details>
            )}
          </div>
        ))}
        <div ref={bottom} />
      </div>
      <form onSubmit={submit} className="ask">
        <input ref={inputRef} value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask about your habits…"
               aria-label="Question" />
        <button type="submit" disabled={busy || !input.trim()}>Ask</button>
      </form>
    </div>
  );
}

function statusText(t: Turn) {
  if (t.status === "Reading the results") return "Writing the answer";
  if (t.status === "Thinking" || t.status === "Starting") return "Thinking about which data to look at";
  return t.status;
}

// A change Pip proposed. Nothing happens until you press "Yes".
const YES = /^(y|yes|yeah|yep|yup|sure|ok|okay|do it|go ahead|please|yes please|sounds good|confirm)$/;
const NO = /^(n|no|nope|nah|never mind|nevermind|cancel|don't|dont|no thanks)$/;

function ProposalCard({ proposal, summary, onDone, pending }: {
  proposal: SwapProposal;
  summary: string;
  onDone: () => void;
  pending: React.MutableRefObject<{ yes: () => void; no: () => void } | null>;
}) {
  const [state, setState] = useState<"ask" | "saving" | "done" | "skipped" | "error">("ask");
  const yes = async () => {
    setState("saving");
    try {
      await api.applyProposal(proposal);
      setState("done");
      window.dispatchEvent(new Event(SWAPS_CHANGED));
      onDone();   // Pip cheers
    } catch {
      setState("error");
    }
  };
  useEffect(() => {
    if (state !== "ask") return;
    const handlers = { yes, no: () => setState("skipped") };
    pending.current = handlers;
    return () => { if (pending.current === handlers) pending.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state]);

  return (
    <div className={"proposal is-" + state} role="group" aria-label="Swap change">
      <div className="eyebrow">Change your swaps?</div>
      <p>{summary}</p>
      {state === "ask" || state === "saving" ? (
        <div className="proposal-actions">
          <button className="primary small" onClick={yes} disabled={state === "saving"}>Yes, do it</button>
          <button className="ghost" onClick={() => setState("skipped")}>Never mind</button>
        </div>
      ) : (
        <p className="proposal-result">
          {state === "done" ? "✓ Done. You can see it on the Nudges page." : state === "skipped" ? "Okay, nothing changed." : "That didn't work. Try again from the Nudges page."}
        </p>
      )}
    </div>
  );
}
