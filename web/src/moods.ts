// The mood check-in: five pixel faces, what Pip does for each, and what it says.
// Pip is kind but real: on hard days it offers comfort and no pressure, on good days it celebrates.

import { PipState } from "./pip";

export type MoodGroup = "low" | "mid" | "high";
export interface Mood { id: string; label: string; level: number; group: MoodGroup }

export const MOODS: Mood[] = [
  { id: "drained", label: "Drained", level: 0, group: "low" },
  { id: "low", label: "Low", level: 1, group: "low" },
  { id: "okay", label: "Okay", level: 2, group: "mid" },
  { id: "good", label: "Good", level: 3, group: "high" },
  { id: "great", label: "Great", level: 4, group: "high" },
];

export const INTRO =
  "Hi, I'm Pip! I'm kind of a detective but cuter, checking your little habits and what's on your screen " +
  "so we can figure out your patterns together. How are you doing today?";

// what Pip does (one is picked when there are several) and says for each mood
export const REPLIES: Record<string, { acts: PipState[]; lines: string[] }> = {
  drained: { acts: ["hug"], lines: [
    "Oof, running-on-empty days are real. Come here, big hug. No big goals needed today, okay?",
    "That sounds exhausting. You don't have to do anything special right now. Here's a big hug, I'm right here.",
    "Thank you for telling me. Drained days happen to everyone. Sending you a gentle hug, let's take it slow together.",
  ]},
  low: { acts: ["hug"], lines: [
    "I'm sorry today feels heavy. Sending you the biggest hug these tiny arms can manage.",
    "Low days are allowed, and they don't erase your progress. Here's a hug, just for you.",
    "Thanks for being honest with me. Here's a warm hug. Be extra kind to yourself today, I'm in your corner.",
  ]},
  okay: { acts: ["heart"], lines: [
    "Okay is a perfectly good place to be. Here, I saved this heart for you.",
    "Steady days are underrated. This little heart is yours.",
    "Middle of the road is still on the road. I'm holding this heart for you while you go.",
  ]},
  good: { acts: ["dance", "hop"], lines: [
    "Yay, that makes me so happy! Let's keep the good vibes rolling.",
    "Love that for you! Want to see what's been going right?",
    "A good day! I'm celebrating with you over here.",
  ]},
  great: { acts: ["dance", "hop"], lines: [
    "Amazing! I'm officially celebrating. Let's ride this energy.",
    "You're glowing and I'm jumping for joy! Let's see what's been working for you.",
    "Great days deserve a little party. Look at you go!",
  ]},
};

// said after the reaction, before the question ideas: no pressure, matched to the mood
export const TRANSITIONS: Record<MoodGroup, string[]> = {
  low: [
    "Whenever you feel up to it, I can show you a few things I've noticed. No rush at all.",
    "We can take a look at things together whenever you're ready, or just hang out. Either is fine with me.",
  ],
  mid: [
    "If you'd like, we can look at your patterns together. Here are a few places to start:",
    "Want to explore a little? Here are some things we could look at:",
  ],
  high: [
    "Want to dig in while you're feeling good? Here's what we could look at:",
    "Let's put that energy to use! Here are some things we could explore:",
  ],
};

export const REACTION_MS = 3000;

export const pick = <T,>(items: T[]): T => items[Math.floor(Math.random() * items.length)];

// a 13 x 13 pixel face for each mood: sleepy, sad, neutral, smiling, grinning
export function moodFace(level: number): (string | null)[][] {
  const S = 13;
  const g: (string | null)[][] = Array.from({ length: S }, () => Array<string | null>(S).fill(null));
  const inside = (x: number, y: number, r: number) => (x - 6) ** 2 + (y - 6) ** 2 <= r * r;
  for (let y = 0; y < S; y++)
    for (let x = 0; x < S; x++) if (inside(x, y, 6.2)) g[y][x] = inside(x, y, 5) ? "#a9a4f6" : "#2b2766";
  const ink = "#2b2766", blush = "#f4a3bf", tongue = "#e0607f";
  const set = (x: number, y: number, c = ink) => { g[y][x] = c; };
  const eyes = () => { set(4, 4); set(4, 5); set(8, 4); set(8, 5); };
  if (level === 0) { [3, 4, 8, 9].forEach((x) => set(x, 5)); [3, 4, 5, 6, 7, 8].forEach((x) => set(x, 9)); }
  if (level === 1) { eyes(); [5, 6, 7].forEach((x) => set(x, 8)); set(4, 9); set(8, 9); }
  if (level === 2) { eyes(); [4, 5, 6, 7, 8].forEach((x) => set(x, 8)); }
  if (level === 3) { eyes(); set(4, 8); set(8, 8); [5, 6, 7].forEach((x) => set(x, 9)); set(2, 7, blush); set(10, 7, blush); }
  if (level === 4) {
    [[3, 5], [4, 4], [5, 5], [7, 5], [8, 4], [9, 5]].forEach(([x, y]) => set(x, y));
    [4, 5, 6, 7, 8].forEach((x) => set(x, 8)); [5, 6, 7].forEach((x) => set(x, 9, tongue));
    set(2, 7, blush); set(10, 7, blush);
  }
  return g;
}
