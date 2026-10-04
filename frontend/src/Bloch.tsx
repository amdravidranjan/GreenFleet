/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useRef } from "react";
import { type Demo, fuelColor } from "./data";

/** One ship: its three fuel qubits drawn as Bloch spheres, and the fuel probabilities they imply. */
export function BlochTile({ d, name, type, thetas, spin }: { d: Demo; name: string; type: string; thetas: number[]; spin: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const p1 = thetas.map((th) => Math.sin(th) ** 2);
  const probs = Array.from({ length: 8 }, (_, k) =>
    [0, 1, 2].reduce((acc, b) => acc * (((k >> (2 - b)) & 1) ? p1[b] : 1 - p1[b]), 1));
  const top = probs.indexOf(Math.max(...probs));
  const settled = probs[top] > 0.8;

  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const dpr = window.devicePixelRatio || 1;
    const w = c.clientWidth, h = c.clientHeight;
    if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) { c.width = Math.round(w * dpr); c.height = Math.round(h * dpr); }
    const ctx = c.getContext("2d")!;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const r = Math.min(w / 6.6, h / 2.3);
    thetas.forEach((th, i) => {
      const cx = w * (i + 0.5) / 3, cy = h / 2;
      ctx.strokeStyle = "rgba(159,179,196,.45)"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
      ctx.beginPath(); ctx.ellipse(cx, cy, r, r * 0.3, 0, 0, Math.PI * 2); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(cx, cy - r); ctx.lineTo(cx, cy + r); ctx.stroke();
      // state vector: polar angle 2θ from |0> (top), viewed with a slowly turning camera
      const pol = 2 * th, az = spin + i * 0.9, tilt = 0.3;
      const x = Math.sin(pol) * Math.cos(az), y = Math.sin(pol) * Math.sin(az), z = Math.cos(pol);
      const sx = cx + r * x, sy = cy - r * (z * Math.cos(tilt) - y * Math.sin(tilt));
      const col = Math.abs(Math.cos(pol)) > 0.85 ? "#7fd6b4" : "#3fb8af";
      ctx.strokeStyle = col; ctx.lineWidth = 2.5;
      ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(sx, sy); ctx.stroke();
      ctx.fillStyle = col; ctx.beginPath(); ctx.arc(sx, sy, 3.5, 0, Math.PI * 2); ctx.fill();
    });
  });

  return (
    <div className="qtile" style={settled ? { borderColor: fuelColor(d, d.fuels[top].key) } : undefined}>
      <div className="n"><b>{name.replace("MV ", "")}</b><span>{settled ? d.fuels[top].name : type === "mr" ? "tanker" : type}</span></div>
      <canvas ref={ref} />
      <div className="fb">{probs.map((p, k) => <div key={k} style={{ width: `${p * 100}%`, background: fuelColor(d, d.fuels[k].key) }} />)}</div>
    </div>
  );
}
