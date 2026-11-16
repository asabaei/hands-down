// Typed wrappers around the Python API (backend/server.py)

export type Behavior = "any" | "nail_biting" | "skin_picking" | "eye_rubbing";
export type Dimension = "category" | "where" | "hour" | "daypart" | "daytype" | "streak";

export interface Status {
  now: number;
  trackers: Record<"webcam" | "activity", { running: boolean; last_seen: number | null }>;
  current_activity: { app: string; domain: string | null; category: string; idle: boolean; since: number } | null;
  latest_nudge: { ts: number; text: string; trigger: string; policy: string } | null;
  llm: { ok: boolean; model: string; model_pulled: boolean };
  has_data: boolean;
  demo: boolean;
  last_nudge: { ts: number; arm: string; status: string; trigger: string; text: string } | null;
}

export interface Window {
  events: number;
  observed_hours: number;
  per_hour: number | null;
}

export interface Progress {
  now: number;
  today: Window;
  yesterday: Window;
  this_week: Window;
  last_week: Window;
  week_change: number | null;
  calm_streak_minutes: number;
  best_calm_minutes_this_week: number;
  days: (Window & { date: string })[];
  last_habit: { ts: number; behavior: string } | null;
}

export interface Overview {
  webcam_observed_hours: number;
  habit_events: number;
  habit_events_per_observed_hour: number | null;
  habit_events_by_behavior: Record<string, number>;
  observed_hours_by_category: Record<string, number>;
}

export interface RateRow {
  context: string;
  events: number;
  observed_hours: number;
  events_per_hour: number | null;
  rate_ratio_vs_rest: number | null;
  ci95: [number, number] | null;
  p_value: number;
}

export interface Rates {
  total_events: number;
  total_observed_hours: number;
  overall_events_per_hour: number | null;
  groups: RateRow[];
}

export interface Pattern extends RateRow {
  behavior: Behavior;
  expected_events: number;
  q_value: number;
  direction: "higher" | "lower";
}

export interface Patterns {
  tested: number;
  patterns: Pattern[];
  note: string;
}

export interface TrendRow {
  period: string;
  events: number;
  observed_hours: number;
  events_per_hour: number | null;
}

export interface Timeline {
  start: number;
  end: number;
  activity: { start: number; end: number; app: string; domain: string | null; category: string; idle: number }[];
  touches: { start: number; end: number; region: string; behavior: string; alerted: number }[];
  nudges: { ts: number; trigger: string; arm: string; policy: string; status: string }[];
  webcam: [number, number][];
}

export interface Group {
  nudges: number;
  successes: number;
  success_rate: number | null;
  ci95: [number, number] | null;
}

export interface NudgeStats {
  total_nudges: number;
  pending: number;
  unknown_outcome: number;
  groups: { bandit: Group; random: Group };
  fisher_p_value: number | null;
  series: { ts: number; bandit: number | null; random: number | null }[];
  arms_by_context: Record<string, { arm: string; text: string; successes: number; failures: number; posterior_mean: number }[]>;
  recent: { ts: number; trigger: string; context: string; detail: string; arm: string; policy: string; status: string }[];
  arm_text: Record<string, string>;
  definition: string;
}

export interface ToolCall {
  name: string;
  arguments: Record<string, unknown>;
  result: unknown;
}

export type ChatEvent =
  | { type: "status"; text: string }
  | { type: "step"; name: string; arguments: Record<string, unknown>; label: string }
  | { type: "step_done"; name: string; result: unknown }
  | { type: "token"; text: string }
  | { type: "reset" }
  | { type: "done"; answer: string; tool_calls: ToolCall[]; seconds: number }
  | { type: "error"; text: string };

export interface ChatReply {
  answer: string;
  tool_calls: ToolCall[];
  seconds: number;
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) throw new Error(path + ": " + r.status);
  return r.json();
}

const days = (d: number | null) => (d ? "days=" + d : "");

export const api = {
  status: () => get<Status>("/api/status"),
  progress: () => get<Progress>("/api/progress"),
  range: () => get<{ start: number | null; end: number | null }>("/api/range"),
  overview: (d: number | null) => get<Overview>("/api/overview?" + days(d)),
  rates: (groupBy: string, behavior: Behavior, d: number | null) =>
    get<Rates>(`/api/rates?group_by=${groupBy}&behavior=${behavior}&` + days(d)),
  patterns: (behavior: Behavior, d: number | null) => get<Patterns>(`/api/patterns?behavior=${behavior}&` + days(d)),
  trend: (behavior: Behavior, d: number | null) =>
    get<{ rows: TrendRow[] }>(`/api/trend?behavior=${behavior}&period=day&days=${d ?? 3650}`),
  timeline: (date: string) => get<Timeline>("/api/timeline?date=" + date),
  nudges: () => get<NudgeStats>("/api/nudges"),
  // streams the assistant's progress: one JSON event per line, handed to onEvent as it arrives
  chatStream: async (question: string, history: { role: string; content: string }[],
                     onEvent: (e: ChatEvent) => void): Promise<void> => {
    const r = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, history }),
    });
    if (!r.ok || !r.body) throw new Error("chat failed: " + r.status);
    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) if (line.trim()) onEvent(JSON.parse(line));
    }
    if (buffer.trim()) onEvent(JSON.parse(buffer));
  },
};
