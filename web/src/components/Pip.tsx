import { useEffect, useMemo, useRef, useState } from "react";
import { drawPose, frameFor, Grid, N, PipState } from "../pip";

const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// Pip as crisp pixel art. Animates while `state` is active; frozen when the user prefers reduced motion.
export function Pip({ state = "idle", size = 64, accent, title }: {
  state?: PipState;
  size?: number;
  accent?: string;
  title?: string;
}) {
  const [t, setT] = useState(0);
  const start = useRef(performance.now());
  useEffect(() => {
    start.current = performance.now();
    setT(0);
    if (reducedMotion()) return;
    const id = window.setInterval(() => setT(performance.now() - start.current), 80);
    return () => window.clearInterval(id);
  }, [state]);
  const grid = useMemo(() => frameFor(state, t, accent), [state, t, accent]);
  return <PixelGrid grid={grid} size={size} title={title} />;
}

export function PixelGrid({ grid, size, crop = [0, 0, N], title }: {
  grid: Grid;
  size: number;
  crop?: [number, number, number];
  title?: string;
}) {
  const [x0, y0, w] = crop;
  const cells = [];
  for (let y = y0; y < y0 + w; y++)
    for (let x = x0; x < x0 + w; x++)
      if (grid[y]?.[x]) cells.push(<rect key={y * N + x} x={x - x0} y={y - y0} width={1.02} height={1.02} fill={grid[y][x]!} />);
  return (
    <svg width={size} height={size} viewBox={`0 0 ${w} ${w}`} shapeRendering="crispEdges" className="pixel"
         role={title ? "img" : undefined} aria-label={title} aria-hidden={title ? undefined : true}>
      {cells}
    </svg>
  );
}

// the logo: Pip cupping its face on a dusk indigo tile. Small sizes use just the head so it stays readable.
export function PipLogo({ size = 32 }: { size?: number }) {
  const small = size <= 20;
  const grid = useMemo(() => drawPose("cup", { accent: "#e1defd" }), []);
  const inner = small ? size : size * 0.88;
  return (
    <span className="pip-logo" style={{ width: size, height: size, borderRadius: size * 0.26 }} aria-hidden="true">
      <PixelGrid grid={grid} size={inner} crop={small ? [2, 4, 20] : [0, 1, 24]} />
    </span>
  );
}
