// Display names and fixed colors. Colors follow the entity (a category always has the same
// color, whatever else is on screen), in the validated palette's slot order.

export const BEHAVIOR_NAMES: Record<string, string> = {
  any: "All habits",
  nail_biting: "Nail biting",
  skin_picking: "Skin picking",
  eye_rubbing: "Eye rubbing",
};

// categories get the categorical slots in a fixed order; everything else is "Other" gray
export const CATEGORY_SLOTS: Record<string, number> = {
  coding: 1, social: 2, video: 3, chat: 4, docs: 5, music: 6, games: 7, email: 8,
};

export function categoryColor(cat: string): string {
  if (cat === "idle") return "var(--idle)";
  const slot = CATEGORY_SLOTS[cat];
  return slot ? `var(--series-${slot})` : "var(--other)";
}

export const CATEGORY_NAMES: Record<string, string> = {
  coding: "Coding", social: "Social", video: "Video", chat: "Chat", docs: "Docs",
  music: "Music", games: "Games", email: "Email", browsing: "Other browsing",
  shopping: "Shopping", news: "News", other: "Other", idle: "Idle", untracked: "Untracked",
};

export const DIMENSION_NAMES: Record<string, string> = {
  category: "App category", where: "App or site", hour: "Hour of day", daypart: "Time of day",
  daytype: "Weekday / weekend", streak: "Minutes into app session",
};

export function describeContext(ctx: string): string {
  // "where=reddit.com & daypart=night (23-5)" -> "reddit.com, night (23-5)"
  return ctx
    .split(" & ")
    .map((part) => {
      const [k, v] = part.split("=");
      if (k === "category") return CATEGORY_NAMES[v] ?? v;
      if (k === "streak") return v + " into a session";
      if (k === "hour") return v.padStart(2, "0") + ":00";
      return v;
    })
    .join(", ");
}

export const fmtTime = (t: number) =>
  new Date(t * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
export const fmtDate = (t: number) => new Date(t * 1000).toLocaleDateString([], { month: "short", day: "numeric" });
export const pct = (x: number | null | undefined) => (x == null ? "–" : Math.round(x * 100) + "%");
export const isoDate = (t: number) => {
  const d = new Date(t * 1000);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

// "where=reddit.com & daypart=night (23-5)" -> "on reddit.com at night (11pm–5am)"
const CATEGORY_PHRASES: Record<string, string> = {
  coding: "while coding", social: "on social media", video: "while watching videos", chat: "in chat apps",
  docs: "while writing docs", music: "with music on", games: "while gaming", email: "while doing email",
  browsing: "while browsing", shopping: "while shopping", news: "while reading news", other: "in other apps",
};
const DAYPART_PHRASES: Record<string, string> = {
  "night (23-5)": "at night (11pm–5am)", "morning (5-12)": "in the morning",
  "afternoon (12-17)": "in the afternoon", "evening (17-23)": "in the evening",
};

export function contextPhrase(ctx: string): string {
  return ctx
    .split(" & ")
    .map((part) => {
      const [k, v] = part.split("=");
      if (k === "category") return CATEGORY_PHRASES[v] ?? "in " + v;
      if (k === "where") return v.includes(".") ? "on " + v : "in " + v;
      if (k === "daypart") return DAYPART_PHRASES[v] ?? v;
      if (k === "daytype") return v === "weekend" ? "on weekends" : "on weekdays";
      if (k === "streak") return v.replace("-", "–").replace(" min", " minutes") + " into a session";
      if (k === "hour") return "around " + v.padStart(2, "0") + ":00";
      return v;
    })
    .join(" ");
}

export function minutesText(m: number): string {
  if (m < 60) return Math.round(m) + " min";
  const h = Math.floor(m / 60);
  const rest = Math.round(m - h * 60);
  return h + " h" + (rest ? " " + rest + " min" : "");
}

export function ago(ts: number, now: number): string {
  const m = Math.max(0, (now - ts) / 60);
  if (m < 1) return "just now";
  if (m < 60) return Math.round(m) + " min ago";
  if (m < 60 * 24) return Math.round(m / 60) + " h ago";
  return Math.round(m / 60 / 24) + " d ago";
}
