import { ReactNode } from "react";

// Shows `tip` on hover or keyboard focus. Used to keep the exact stats (CIs, p-values) out of the way
// while leaving them one hover away.
export function Tip({ tip, children, className }: { tip: string; children: ReactNode; className?: string }) {
  return (
    <span className={"tip" + (className ? " " + className : "")} tabIndex={0} aria-label={tip} data-tip={tip}>
      {children}
      <span className="tip-mark" aria-hidden="true">i</span>
    </span>
  );
}
