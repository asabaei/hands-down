import { useEffect, useRef, useState } from "react";
import { api, Patterns } from "../api";
import { useData } from "../hooks";
import { BEHAVIOR_NAMES, contextPhrase } from "../labels";
import { INTRO, Mood, MoodGroup, MOODS, moodFace, pick, REACTION_MS, REPLIES, TRANSITIONS } from "../moods";
import { PipState } from "../pip";
import { PixelGrid } from "./Pip";

// How a chat with Pip begins: Pip introduces itself, asks how you're doing, reacts to your mood
// (a hug on hard days, a heart on okay days, a dance or hops on good days), then gently offers ideas.
// Everything happens one step at a time: Pip talks while each message types out, then reacts.

type Line = { from: "pip" | "me"; text: string; mood?: Mood };

const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export function PipIntro({ onAsk, showIdeas, active, onPip }: {
  onAsk: (q: string) => void;
  showIdeas: boolean;                         // false once a question has been asked
  active: boolean;                            // the chat is open (nothing starts until it is)
  onPip: (s: PipState | null) => void;        // drives the Pip in the corner
}) {
  const [lines, setLines] = useState<Line[]>([]);
  const [typing, setTyping] = useState<{ text: string; shown: number } | null>(null);
  const [stage, setStage] = useState<"start" | "intro" | "moods" | "reply" | "react" | "transition" | "ideas">("start");
  const [mood, setMood] = useState<Mood | null>(null);
  const timers = useRef<number[]>([]);
  const skip = useRef(false);

  const end = useRef<HTMLDivElement>(null);
  const later = (fn: () => void, ms: number) => { timers.current.push(window.setTimeout(fn, ms)); };

  // keep the newest message in view as Pip types
  useEffect(() => {
    if (!active) return;
    if (stage === "ideas") {
      // show Pip's transition line at the top, with the ideas under it
      const said = end.current?.parentElement?.querySelectorAll(".pip-says");
      said?.[said.length - 1]?.scrollIntoView({ block: "start", behavior: "smooth" });
    } else end.current?.scrollIntoView({ block: "nearest" });
  }, [active, lines.length, typing?.shown, stage]);
  useEffect(() => () => timers.current.forEach(window.clearTimeout), []);

  // types a message out letter by letter while Pip talks, then calls done
  const say = (text: string, done: () => void) => {
    skip.current = false;
    onPip("talking");
    if (reducedMotion()) {
      setLines((l) => [...l, { from: "pip", text }]);
      onPip(null);
      done();
      return;
    }
    let shown = 0;
    const tick = () => {
      shown = skip.current ? text.length : Math.min(text.length, shown + (text[shown] === " " ? 2 : 1));
      setTyping({ text, shown });
      if (shown < text.length) later(tick, ".!?,".includes(text[shown - 1]) ? 140 : 24);
      else {
        setTyping(null);
        setLines((l) => [...l, { from: "pip", text }]);
        onPip(null);
        done();
      }
    };
    tick();
  };

  // start the introduction the first time the chat opens
  useEffect(() => {
    if (!active || stage !== "start") return;
    setStage("intro");
    later(() => say(INTRO, () => setStage("moods")), 450);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  const choose = (m: Mood) => {
    setMood(m);
    setLines((l) => [...l, { from: "me", text: m.label, mood: m }]);
    setStage("reply");
    const reply = REPLIES[m.id];
    later(() => say(pick(reply.lines), () => {
      // after talking, Pip plays its reaction, then a gentle transition line, then the ideas
      setStage("react");
      onPip(pick(reply.acts));
      later(() => {
        onPip(null);
        setStage("transition");
        say(pick(TRANSITIONS[m.group]), () => setStage("ideas"));
      }, reducedMotion() ? 600 : REACTION_MS);
    }), 400);
  };

  return (
    <div className="pip-intro">
      {lines.map((l, i) =>
        l.from === "pip" ? (
          <div key={i} className="bubble pip-says">{l.text}</div>
        ) : (
          <div key={i} className="bubble me-says"><PixelGrid grid={moodFace(l.mood!.level)} size={20} crop={[0, 0, 13]} />{l.text}</div>
        ),
      )}
      {typing && (
        <button className="bubble pip-says typing" onClick={() => (skip.current = true)} title="Click to skip">
          {typing.text.slice(0, typing.shown)}<span className="cursor" aria-hidden="true" />
        </button>
      )}
      {stage === "moods" && showIdeas && (
        <div className="moods" role="group" aria-label="How are you doing today?">
          {MOODS.map((m) => (
            <button key={m.id} className="mood" onClick={() => choose(m)}>
              <PixelGrid grid={moodFace(m.level)} size={36} crop={[0, 0, 13]} />
              {m.label}
            </button>
          ))}
        </div>
      )}
      {stage === "ideas" && showIdeas && mood && <Ideas group={mood.group} onAsk={onAsk} />}
      <div ref={end} />
    </div>
  );
}

const GENTLE: [string, string[]][] = [
  ["Something kind", ["What's been going well lately?", "When am I usually calmest?", "Which swap helps me the most?"]],
];
const ALL: [string, string[]][] = [
  ["Patterns", ["When do I pick my skin the most?", "Does nail biting go up during long coding sessions?"]],
  ["Progress", ["Am I doing better this week than last week?", "What happened yesterday?"]],
  ["Screen time", ["Which apps am I using when my habits happen?"]],
  ["Nudges", ["Which swap works best for me?", "Do the bandit's nudges work better than random ones?"]],
];

function Ideas({ group, onAsk }: { group: MoodGroup; onAsk: (q: string) => void }) {
  // on low days, lead with kinder questions; everything else is one tap away
  const [all, setAll] = useState(group !== "low");
  const { data } = useData<Patterns>(() => api.patterns("any", 28), []);
  const top = data?.patterns.find((p) => p.direction === "higher");
  const personal = top && group !== "low"
    ? "Why is my " + (top.behavior === "any" ? "habit" : (BEHAVIOR_NAMES[top.behavior] ?? "habit").toLowerCase()) +
      " rate higher " + contextPhrase(top.context) + "?"
    : null;
  const groups = group === "low" ? (all ? [...GENTLE, ...ALL] : GENTLE) : ALL;
  return (
    <div className="pip-ideas">
      {personal && (
        <div className="idea-group">
          <div className="idea-topic">From your data</div>
          <button className="chip personal" onClick={() => onAsk(personal)}><span aria-hidden="true">✦</span> {personal}</button>
        </div>
      )}
      {groups.map(([topic, qs]) => (
        <div key={topic} className="idea-group">
          <div className="idea-topic">{topic}</div>
          {qs.map((q) => <button key={q} className="chip" onClick={() => onAsk(q)}>{q}</button>)}
        </div>
      ))}
      {!all && <button className="chip more" onClick={() => setAll(true)}>Show me everything</button>}
    </div>
  );
}
