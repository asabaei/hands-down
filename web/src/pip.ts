// Pip, the Hands Down mascot, drawn on a 24 x 24 pixel grid.
// drawPose() returns a grid of colors (null = transparent); framesFor() animates a state over time.

export const N = 24;
export type Grid = (string | null)[][];
export type PipState = "idle" | "wave" | "thinking" | "talking" | "cheer" | "cup" | "sleepy";

const C = {
  outline: "#2b2766", body: "#a9a4f6", light: "#cdc9fb", shade: "#8d87ee",
  eye: "#2b2766", blush: "#f4a3bf", mouth: "#2b2766", tongue: "#e0607f",
  hand: "#bdb8f9", handLight: "#e1defd", spark: "#f6c453",
};
const CX = 11.5;

interface Pose {
  hands: [number, number][];
  face: "smile" | "open" | "flat" | "joy" | "sleep";
  look?: [number, number];
  blushBig?: boolean;
}

const POSES: Record<string, Pose> = {
  down: { hands: [[3, 17], [21, 17]], face: "smile" },
  wave: { hands: [[3, 17], [21, 6]], face: "open" },
  wave2: { hands: [[3, 17], [22, 4]], face: "open" },
  think: { hands: [[3, 17], [14, 18]], face: "flat", look: [1, -1] },
  talk: { hands: [[3, 16], [21, 16]], face: "open" },
  talk2: { hands: [[3, 17], [21, 17]], face: "smile" },
  cheer: { hands: [[2, 6], [21, 6]], face: "joy" },
  cup: { hands: [[6, 15], [17, 15]], face: "joy", blushBig: true },
  sleepy: { hands: [[3, 17], [21, 17]], face: "sleep" },
};

const empty = (): Grid => Array.from({ length: N }, () => Array<string | null>(N).fill(null));
const mask = () => Array.from({ length: N }, () => Array<number>(N).fill(0));

function bodyMask(dy: number, squash: number) {
  const m = mask();
  const rx = 8 + squash, ry = 7 - squash, cy = 13 + dy + squash;
  for (let y = 0; y < N; y++)
    for (let x = 0; x < N; x++) {
      const nx = (x + 0.5 - (CX + 0.5)) / rx, ny = (y + 0.5 - cy) / ry;
      if (nx * nx + ny * ny <= 1) m[y][x] = 1;
    }
  const fy = Math.round(cy + ry - 0.5);   // little feet
  for (const [a, b] of [[8, 9], [14, 15]]) for (let x = a; x <= b; x++) if (fy < N) m[fy][x] = 1;
  return m;
}

function handMask(cx: number, cy: number) {   // a round 4 x 4 mitten
  const m = mask();
  for (let y = cy - 2; y < cy + 2; y++)
    for (let x = cx - 2; x < cx + 2; x++) {
      const corner = (y === cy - 2 || y === cy + 1) && (x === cx - 2 || x === cx + 1);
      if (!corner && y >= 0 && y < N && x >= 0 && x < N) m[y][x] = 1;
    }
  return m;
}

function paint(g: Grid, m: number[][], fill: string, light: string, shade: string) {
  const at = (x: number, y: number) => y >= 0 && y < N && x >= 0 && x < N && m[y][x] === 1;
  for (let y = 0; y < N; y++)
    for (let x = 0; x < N; x++) {
      if (m[y][x]) g[y][x] = !at(x, y - 1) || !at(x - 1, y) ? light : !at(x, y + 1) || !at(x + 1, y) ? shade : fill;
      else if (at(x - 1, y) || at(x + 1, y) || at(x, y - 1) || at(x, y + 1)) g[y][x] = C.outline;
    }
}

const px = (g: Grid, x: number, y: number, c: string) => {
  if (y >= 0 && y < N && x >= 0 && x < N) g[y][x] = c;
};

interface Opts {
  dy?: number;
  blink?: boolean;
  squash?: number;
  sparkle?: boolean;
  dots?: number;        // thinking dots shown (0-3)
  zs?: boolean;
  accent?: string;      // color for dots and Zs (light on the indigo tile, indigo elsewhere)
}

export function drawPose(name: keyof typeof POSES, o: Opts = {}): Grid {
  const p = POSES[name];
  const dy = o.dy ?? 0, squash = o.squash ?? 0, y0 = dy + squash;
  const accent = o.accent ?? "#4b46b2";
  const g = empty();
  paint(g, bodyMask(dy, squash), C.body, C.light, C.shade);

  // eyes
  const eyeY = 11 + y0, [lx, ly] = p.look ?? [0, 0];
  if (p.face === "joy") for (const [x, d] of [[8, 1], [9, 0], [10, 1], [13, 1], [14, 0], [15, 1]]) px(g, x, eyeY + d, C.eye);
  else if (p.face === "sleep" || o.blink) for (const x of [8, 9, 14, 15]) px(g, x, eyeY + 1, C.eye);
  else for (const [x, y] of [[9, eyeY], [9, eyeY + 1], [14, eyeY], [14, eyeY + 1]]) px(g, x + lx, y + ly, C.eye);

  // cheeks
  const by = 14 + y0;
  for (const x of [7, 8, 15, 16]) px(g, x, by, C.blush);
  if (p.blushBig) { px(g, 7, by - 1, C.blush); px(g, 16, by - 1, C.blush); }

  // mouth
  const my = 14 + y0;
  if (p.face === "smile" || p.face === "joy") { px(g, 10, my, C.mouth); px(g, 13, my, C.mouth); px(g, 11, my + 1, C.mouth); px(g, 12, my + 1, C.mouth); }
  else if (p.face === "open") { px(g, 11, my, C.mouth); px(g, 12, my, C.mouth); px(g, 11, my + 1, C.tongue); px(g, 12, my + 1, C.tongue); }
  else { px(g, 11, my + 1, C.mouth); px(g, 12, my + 1, C.mouth); }

  // hands drawn on top of the body
  for (const [hx, hy] of p.hands) {
    const hg = empty();
    paint(hg, handMask(hx, hy + (hy > 12 ? y0 : 0)), C.hand, C.handLight, C.body);
    for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) if (hg[y][x]) g[y][x] = hg[y][x];
  }

  if (o.dots) for (const [x, y] of [[17, 2], [19, 2], [21, 2]].slice(0, o.dots)) px(g, x, y, accent);
  if (o.zs) for (const [x, y] of [[18, 3], [19, 3], [19, 4], [18, 5], [19, 5], [21, 0], [22, 0], [22, 1], [21, 2], [22, 2]]) px(g, x, y, accent);
  if (o.sparkle)
    for (const [x, y] of [[2, 2], [21, 1], [1, 10], [22, 11]])
      for (const [dx, dy2] of [[0, 0], [1, 0], [-1, 0], [0, 1], [0, -1]]) px(g, x + dx, y + dy2, C.spark);
  return g;
}

// one frame of an animated state; t is milliseconds since the state started
export function frameFor(state: PipState, t: number, accent?: string): Grid {
  const step = (ms: number) => Math.floor(t / ms) % 2;
  switch (state) {
    case "wave": return drawPose(step(180) ? "wave2" : "wave", { accent });
    case "thinking": return drawPose("think", { dy: step(700), dots: Math.floor(t / 350) % 4, accent });
    case "talking": return drawPose(step(160) ? "talk" : "talk2", { dy: step(160) ? -1 : 0, accent });
    case "cheer": return drawPose("cheer", { dy: step(200) ? -1 : 0, sparkle: step(200) === 0, accent });
    case "cup": return drawPose("cup", { squash: step(300), accent });
    case "sleepy": return drawPose("sleepy", { dy: step(900), zs: true, accent });
    default: return drawPose("down", { dy: step(500), blink: t % 3600 < 160, accent });
  }
}

// SVG markup for a grid (used for the favicon and anywhere a static image is easier)
export function gridToSvg(g: Grid, crop: [number, number, number] = [0, 0, N]): string {
  const [x0, y0, w] = crop;
  let rects = "";
  for (let y = 0; y < N; y++)
    for (let x = 0; x < N; x++)
      if (g[y][x] && x >= x0 && x < x0 + w && y >= y0 && y < y0 + w)
        rects += `<rect x="${x - x0}" y="${y - y0}" width="1.02" height="1.02" fill="${g[y][x]}"/>`;
  return rects;
}
