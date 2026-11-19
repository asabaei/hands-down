import { ReactNode } from "react";

// absolutely positioned inside a relatively positioned chart wrapper
export function Tooltip({ x, y, children, width }: { x: number; y: number; children: ReactNode; width: number }) {
  const left = Math.min(Math.max(x + 12, 0), width - 220);
  return (
    <div className="tooltip" style={{ left, top: Math.max(y - 10, 0) }} role="status">
      {children}
    </div>
  );
}

