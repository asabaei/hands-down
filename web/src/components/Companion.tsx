import { useEffect, useRef, useState } from "react";
import { Status } from "../api";
import { PipState } from "../pip";
import { Chat, ChatActivity } from "./Chat";
import { Pip } from "./Pip";

const GREETED_KEY = "handsdown.greeted";

// Pip lives in the bottom-right corner. Click Pip to chat from any page.
// Pip's mood follows the assistant: thinking while it looks at your data, talking while the answer
// streams in, cheering when it's done. It waves when you hover, and naps when the trackers are off.
export function Companion({ status, ask, open, setOpen }: {
  status: Status | null;
  ask: { question: string; id: number } | null;
  open: boolean;
  setOpen: (o: boolean) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [activity, setActivity] = useState<PipState>("idle");   // from the chat
  const [moment, setMoment] = useState<PipState | null>(null);  // short reactions (wave, cheer, shy)
  const [intro, setIntro] = useState<PipState | null>(null);    // talking and reacting during the mood check-in
  const [greet, setGreet] = useState(() => !localStorage.getItem(GREETED_KEY));
  const momentTimer = useRef<number | undefined>(undefined);
  const input = useRef<HTMLInputElement>(null);

  const react = (s: PipState, ms: number) => {
    window.clearTimeout(momentTimer.current);
    setMoment(s);
    momentTimer.current = window.setTimeout(() => setMoment(null), ms);
  };

  const onActivity = (a: ChatActivity) => {
    if (a === "thinking") setActivity("thinking");
    else if (a === "talking") setActivity("talking");
    else {
      setActivity("idle");
      if (a === "done") react("cheer", 1600);
    }
  };

  // wave hello on the first visit
  useEffect(() => {
    if (greet) react("wave", 1800);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!open) return;
    if (greet) {
      setGreet(false);
      localStorage.setItem(GREETED_KEY, "1");
    }
    react("cup", 1200);   // a shy little hello when the chat opens
    setTimeout(() => input.current?.focus(), 50);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const trackersOff = !!status && !status.demo && !status.trackers.webcam.running && !status.trackers.activity.running;
  const busy = activity !== "idle";
  const state: PipState = busy ? activity : intro ?? moment ?? (trackersOff ? "sleepy" : "idle");
  const caption = activity === "thinking" ? "looking at your data…" : activity === "talking" ? "typing…"
    : intro === "talking" ? "typing…"
    : status?.llm.ok ? "local · " + status.llm.model.split(":")[0] : "assistant offline";

  return (
    <div className={"companion" + (open ? " is-open" : "")}>
      {/* the panel stays mounted when closed, so the conversation is kept */}
      <section className={"companion-panel" + (expanded ? " expanded" : "")} role="dialog" aria-label="Pip, your habit assistant"
               hidden={!open}>
        <header className="companion-head">
          <div className="companion-title">
            <strong>Pip</strong>
            <span className="muted">{caption}</span>
          </div>
          <button className="icon-btn" onClick={() => setExpanded(!expanded)} aria-label={expanded ? "Make smaller" : "Expand"}
                  title={expanded ? "Make smaller" : "Expand"}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              {expanded ? <path d="M9 4v5H4M15 20v-5h5M20 9h-5V4M4 15h5v5" /> : <path d="M4 9V4h5M20 15v5h-5M15 4h5v5M9 20H4v-5" />}
            </svg>
          </button>
          <button className="icon-btn" onClick={() => setOpen(false)} aria-label="Close" title="Close (Esc)">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </header>
        <div className="companion-body">
          <Chat llm={status?.llm} initial={ask} onActivity={onActivity} inputRef={input} active={open} onPip={setIntro} />
        </div>
      </section>

      {greet && !open && (
        <button className="companion-greeting" onClick={() => setOpen(true)}>
          Hi, I'm <b>Pip</b>! Ask me anything about your habits.
        </button>
      )}
      <button className="companion-button"
              onClick={() => { setOpen(!open); if (!open) react("wave", 1200); }}
              onMouseEnter={() => !busy && react("wave", 1400)}
              aria-label={open ? "Close the chat with Pip" : "Chat with Pip"} aria-expanded={open}>
        <Pip state={state} size={66} />
      </button>
    </div>
  );
}
