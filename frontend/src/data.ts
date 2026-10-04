/* eslint-disable @typescript-eslint/no-explicit-any */
// Data exported by backend/scripts/export_demo.py plus small helpers shared by all scenes.

export type Plan = {
  objectives: { cost_musd: number; wtw_kt: number; energy_kt: number };
  cost_breakdown: Record<string, number>;
  fuel_mix: Record<string, number>;
  vessels: { id: number; name: string; type: string; route: string | null; speed_kn: number; speed_pct: number;
    fuel: string | null; shore_power: boolean; cii: string | null; wtw_kt: number; fuel_t_per_day: number }[];
  routes: { key: string; demand_kt: number; capacity_kt: number; sailings: number }[];
  cii_counts: Record<string, number>;
};
export type Demo = any;

export const CII_COLORS: Record<string, string> = { A: "#3fb8af", B: "#7fd6b4", C: "#c9d86b", D: "#ffb547", E: "#ff5d5d" };

/** Resolve a file in public/ relative to the page, so the site works under any sub-path (e.g. GitHub Pages). */
export const asset = (p: string) => new URL(p, document.baseURI).href;

export function fuelColor(d: Demo, key: string | null): string {
  if (!key) return "#556677";
  return d.fuels.find((f: any) => f.key === key)?.color ?? "#888";
}
export function fuelName(d: Demo, key: string): string {
  return d.fuels.find((f: any) => f.key === key)?.name ?? key;
}

export const clamp = (x: number, a = 0, b = 1) => Math.min(b, Math.max(a, x));
export const ease = (x: number) => { const t = clamp(x); return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; };
export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
export const fmt = (x: number, d = 0) => x.toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d });

/** Demo clock: wall time normally; in render mode the recorder drives a virtual clock frame by frame. */
export const clock: { virtual: number | null } = { virtual: null };
export const clockNow = () => clock.virtual ?? Date.now();

/** Log a timed demo event to the console (the recorder reads these to align narration). */
const fired = new Set<string>();
export function act(name: string) {
  if (fired.has(name)) return;
  fired.add(name);
  console.log("[DEMO] " + JSON.stringify({ ev: name, at: clockNow() }));
}
/** Fire `name` once when scene time t passes `at` seconds; returns whether it has fired. */
export function cue(name: string, t: number, at: number): boolean {
  if (t >= at) { act(name); return true; }
  return false;
}
export function resetCues() { fired.clear(); }

// ---------------------------------------------------------------- ship kinematics
type Path = { pts: [number, number][]; cum: number[]; total: number };
const pathCache = new Map<string, Path>();
export function routePath(d: Demo, key: string): Path {
  if (pathCache.has(key)) return pathCache.get(key)!;
  const pts = d.routes.find((r: any) => r.key === key).path as [number, number][];
  const cum = [0];
  for (let i = 1; i < pts.length; i++) {
    const [x0, y0] = pts[i - 1], [x1, y1] = pts[i];
    const dx = (x1 - x0) * Math.cos(((y0 + y1) / 2) * Math.PI / 180), dy = y1 - y0;
    cum.push(cum[i - 1] + Math.hypot(dx, dy));
  }
  const p = { pts, cum, total: cum[cum.length - 1] };
  pathCache.set(key, p);
  return p;
}
export function pointAt(p: Path, s: number): [number, number] {
  const target = clamp(s) * p.total;
  let i = 1;
  while (i < p.cum.length - 1 && p.cum[i] < target) i++;
  const seg = p.cum[i] - p.cum[i - 1] || 1;
  const u = (target - p.cum[i - 1]) / seg;
  const [x0, y0] = p.pts[i - 1], [x1, y1] = p.pts[i];
  return [x0 + (x1 - x0) * u, y0 + (y1 - y0) * u];
}
/** Position of a ship on its route at sim time (hours); ping-pong between the two ports. */
export function shipPos(d: Demo, route: string, nm: number, speedKn: number, id: number, hours: number): [number, number] {
  const p = routePath(d, route);
  const leg = nm / Math.max(speedKn, 1);
  const phase = (id * 0.61803) % 1;
  const x = (hours / leg + phase * 2) % 2;
  return pointAt(p, x < 1 ? x : 2 - x);
}
