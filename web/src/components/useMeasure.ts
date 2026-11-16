import { useEffect, useState } from "react";

// measures an element's width. Uses a callback ref, so it also works when the element only
// appears after the first render (e.g. a chart that shows "No data yet" until its data arrives)
export function useMeasure<T extends HTMLElement>() {
  const [el, setEl] = useState<T | null>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    if (!el) return;
    setWidth(Math.max(240, el.getBoundingClientRect().width));
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(240, e.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, [el]);
  return [setEl, width || 240] as const;
}

export function niceMax(v: number) {
  if (v <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  const n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p;
}

// clean tick values (0, 0.5, 1, 1.5 ...) up to max
export function ticks(max: number, count = 4) {
  const raw = max / count;
  const p = Math.pow(10, Math.floor(Math.log10(raw)));
  const n = raw / p;
  const step = (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p;
  const out = [];
  for (let v = 0; v <= max + 1e-9; v += step) out.push(Number(v.toFixed(6)));
  return out;
}

export const fmtNum = (v: number) => String(Number(v.toFixed(2)));

// a y/x scale whose top is a clean tick at or above the largest value
export function axis(maxValue: number, count = 4) {
  const t = ticks(niceMax(maxValue), count);
  const step = t[1] ?? 1;
  while (t[t.length - 1] < maxValue - 1e-9) t.push(Number((t[t.length - 1] + step).toFixed(6)));
  return { max: t[t.length - 1], ticks: t };
}
