// small line icons for the sidebar (24px grid, 1.8px stroke)
const base = { width: 18, height: 18, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
               strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };

export const TodayIcon = () => (
  <svg {...base}><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
);
export const PatternsIcon = () => (
  <svg {...base}><path d="M3 20h18" /><path d="M6 16v-5M11 16V7M16 16v-3M20 16V5" /></svg>
);
export const AskIcon = () => (
  <svg {...base}><path d="M20 12a8 8 0 0 1-11.6 7.1L4 20l1-4.2A8 8 0 1 1 20 12Z" /><path d="M9 11h6M9 14h4" /></svg>
);
export const NudgeIcon = () => (
  <svg {...base}><path d="M12 3a5 5 0 0 0-5 5v3.5L5.5 15h13L17 11.5V8a5 5 0 0 0-5-5Z" /><path d="M10 18a2 2 0 0 0 4 0" /></svg>
);
export const ArrowRight = () => (
  <svg {...base} width={16} height={16}><path d="M5 12h14M13 6l6 6-6 6" /></svg>
);
