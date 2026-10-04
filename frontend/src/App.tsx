/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useMemo, useRef, useState } from "react";
import { flushSync } from "react-dom";
import FleetMap from "./FleetMap";
import { BlochTile } from "./Bloch";
import { Sankey } from "./Sankey";
import { type Demo, type Plan, CII_COLORS, act, cue, resetCues, clock, clockNow, clamp, ease, lerp, fmt, fuelColor, fuelName } from "./data";

type SceneId = "intro" | "fleet" | "predict" | "quantum" | "pareto" | "twin" | "time" | "genealogy" | "storm" | "ask" | "outro";
const SCENES: { id: SceneId; label: string; dur: number; marks?: Record<string, number> }[] = [
  { id: "intro", label: "Intro", dur: 16 }, { id: "fleet", label: "Fleet today", dur: 22 },
  { id: "predict", label: "Fuel predictor", dur: 30 }, { id: "quantum", label: "Quantum engine", dur: 26 },
  { id: "pareto", label: "Trade-offs", dur: 18 }, { id: "twin", label: "Digital twin", dur: 24 },
  { id: "time", label: "Time machine", dur: 22 }, { id: "genealogy", label: "Fuel genealogy", dur: 24 },
  { id: "storm", label: "Storm mode", dur: 22 }, { id: "ask", label: "Ask the fleet", dur: 22 }, { id: "outro", label: "Summary", dur: 14 },
];
const SIM_HOURS_PER_SEC = 10;
const pct = (a: number, b: number) => Math.round((a / b - 1) * 100);

export default function App() {
  const [d, setD] = useState<Demo | null>(null);
  const [timeline, setTimeline] = useState(SCENES);
  const [scene, setScene] = useState(0);
  const [sceneStart, setSceneStart] = useState(clockNow());
  const [now, setNow] = useState(clockNow());
  const appStart = useRef(clockNow());
  const demo = useMemo(() => new URLSearchParams(location.search).has("demo"), []);
  const running = useRef(false);
  const demoStart = useRef(0);

  useEffect(() => {
    fetch("/demo-data.json").then((r) => r.json()).then(setD);
    fetch("/timeline.json").then((r) => (r.ok ? r.json() : null)).then((t) => {
      if (t?.scenes) setTimeline(SCENES.map((s) => { const x = t.scenes.find((y: any) => y.id === s.id); return { ...s, dur: x?.dur ?? s.dur, marks: x?.marks ?? {} }; }));
    }).catch(() => undefined);
  }, []);

  useEffect(() => {
    let raf = 0;
    const tick = () => { if (clock.virtual === null) setNow(clockNow()); raf = requestAnimationFrame(tick); };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  // demo director: waits for window.__startDemo(), then plays scenes back-to-back on the wall clock
  useEffect(() => {
    if (!d) return;
    (window as any).__demoReady = true;
    // render mode: the recorder sets the clock for every frame and re-renders synchronously
    (window as any).__setClock = (ms: number) => { clock.virtual = ms; flushSync(() => setNow(ms)); };
    (window as any).__startDemo = () => {
      resetCues();
      running.current = true;
      demoStart.current = clockNow();
      appStart.current = clockNow();
      setScene(0); setSceneStart(clockNow());
      act("demo:start"); act("scene:intro");
    };
    if (!demo) act("app:ready");
  }, [d, demo]);

  useEffect(() => {
    if (!running.current) return;
    let acc = 0;
    const el = (now - demoStart.current) / 1000;
    for (let i = 0; i < timeline.length; i++) {
      if (el < acc + timeline[i].dur) {
        if (i !== scene) { setScene(i); setSceneStart(demoStart.current + acc * 1000); act("scene:" + timeline[i].id); }
        return;
      }
      acc += timeline[i].dur;
    }
    running.current = false;
    act("demo:end");
  }, [now, timeline, scene]);

  if (!d) return <div className="app" />;
  const cur = timeline[scene];
  const t = (now - sceneStart) / 1000;
  const hours = ((now - appStart.current) / 1000) * SIM_HOURS_PER_SEC;
  const Y = d.years[String(d.meta.main_year)];
  const go = (i: number) => { running.current = false; setScene(i); setSceneStart(clockNow()); };
  const mk = (name: string, frac: number) => cur.marks?.[name] ?? cur.dur * frac;
  const p = { d, t, dur: cur.dur, hours, mk };

  return (
    <div className={"app" + (demo ? " demo" : "")}>
      <Stage id={cur.id} {...p} />
      <header className="bar">
        <div className="brand">GreenFleet<b>-Q</b></div>
        <nav className="nav" aria-label="Demo sections">
          {timeline.map((s, i) => (
            <button key={s.id} className={i === scene ? "on" : ""} onClick={() => go(i)}>{s.label}</button>
          ))}
        </nav>
        <div className="year">Rules of <strong>{cur.id === "time" ? Math.round(timeYear(t, mk)) : d.meta.main_year}</strong></div>
      </header>
      {cur.id === "intro" && <Intro {...p} />}
      {cur.id === "fleet" && <FleetToday {...p} plan={Y.bau} />}
      {cur.id === "predict" && <Predictor {...p} />}
      {cur.id === "quantum" && <Quantum {...p} />}
      {cur.id === "pareto" && <Pareto {...p} />}
      {cur.id === "twin" && <TwinOverlay {...p} />}
      {cur.id === "time" && <TimeMachine {...p} />}
      {cur.id === "genealogy" && <Genealogy {...p} />}
      {cur.id === "storm" && <Storm {...p} />}
      {cur.id === "ask" && <Ask {...p} />}
      {cur.id === "outro" && <Outro {...p} />}
    </div>
  );
}

type MK = (name: string, frac: number) => number;
type P = { d: Demo; t: number; dur: number; hours: number; mk: MK };
const timeYear = (t: number, mk: MK) => { const a = mk("time:start", 0.12), b = mk("time:2050", 0.84); return lerp(2025, 2050, ease(clamp((t - a) / (b - a)))); };

// ------------------------------------------------------------------ background stage per scene
function Stage({ id, d, t, hours, mk }: P & { id: SceneId }) {
  const Y = d.years[String(d.meta.main_year)];
  if (id === "twin") {
    return (
      <div className="split">
        <div><FleetMap d={d} plan={Y.bau} hours={hours} mode="bau" view={{ longitude: 86, latitude: 10.5, zoom: 3.3 }} /></div>
        <div><FleetMap d={d} plan={Y.opt} hours={hours} mode="opt" view={{ longitude: 86, latitude: 10.5, zoom: 3.3 }} /></div>
      </div>
    );
  }
  let plan: Plan = Y.opt, mode: "bau" | "opt" = "opt", dim = false, flagBad = 0, storm: any;
  if (id === "intro" || id === "fleet") { plan = Y.bau; mode = "bau"; }
  if (id === "fleet") flagBad = t > mk("fleet:flag-de", 0.45) ? 0.5 + 0.5 * Math.sin(t * 4) : 0;
  if (id === "predict" || id === "quantum" || id === "pareto" || id === "genealogy" || id === "outro") dim = true;
  if (id === "time") {
    const yr = timeYear(t, mk);
    const near = d.meta.years.reduce((a: number, b: number) => (Math.abs(b - yr) < Math.abs(a - yr) ? b : a));
    plan = d.years[String(near)].opt; dim = true;
  }
  if (id === "storm") {
    const a = clamp((t - mk("storm:detected", 0.1) + 0.6) / 2);
    plan = t > mk("storm:new-plan", 0.62) ? d.storm.replan : d.storm.keep;
    storm = { center: d.storm.center, radius: 3.2, spin: -t * 1.6, routes: t > mk("storm:forecast", 0.27) ? Object.keys(d.storm.routes) : [], alpha: a };
  }
  return (
    <div className={"stage" + (dim ? " dim" : "")}>
      <FleetMap d={d} plan={plan} hours={hours} mode={mode} flagBad={flagBad} storm={storm} />
    </div>
  );
}

// ------------------------------------------------------------------ scenes
function Intro({ t }: P) {
  cue("intro:title", t, 0.3);
  return (
    <div className="card" style={{ opacity: clamp(t / 0.8) }}>
      <h1 className="big">GreenFleet<span>-Q</span></h1>
      <p className="tag">A quantum-inspired co-pilot that predicts every ship’s fuel and plans the whole fleet for less fuel, less cost and less carbon.</p>
      <div className="meta" style={{ opacity: clamp((t - 2) / 1) }}>
        <div><strong>Cup Of Tea</strong>Team ID 141591</div>
        <div><strong>Smart India Hackathon 2026</strong>Quantum-inspired fuel prediction & green fleet optimisation</div>
        <div><strong>Simulated demo</strong>40 ships · 7 routes from Chennai</div>
      </div>
    </div>
  );
}

function FleetToday({ d, t, mk, plan }: P & { plan: Plan }) {
  const kT = mk("fleet:kpis", 0.2);
  cue("fleet:kpis", t, kT);
  const bad = cue("fleet:flag-de", t, mk("fleet:flag-de", 0.45));
  const o = plan.objectives;
  const de = (plan.cii_counts.D || 0) + (plan.cii_counts.E || 0);
  const tot = Object.values(plan.cii_counts).reduce((a, b) => a + b, 0);
  const k = ease(clamp((t - kT) / 2));
  return (
    <section className="panel right" style={{ opacity: clamp((t - 0.5) / 0.8) }}>
      <h2>The fleet today</h2>
      <p className="sub">Fixed speeds, fossil fuels — how most fleets still operate. Rules of {d.meta.main_year}.</p>
      <div className="kpis">
        <div className="kpi bad"><div className="v">{fmt(o.wtw_kt * k)}</div><div className="l">thousand tonnes CO₂e a year</div></div>
        <div className="kpi bad"><div className="v">${fmt(o.cost_musd * k)}M</div><div className="l">running cost a year</div></div>
        <div className="kpi"><div className="v">{fmt(o.energy_kt * k)}</div><div className="l">thousand tonnes of fuel a year</div></div>
        <div className={"kpi " + (bad ? "alert" : "")}><div className="v">{bad ? de : "–"}</div><div className="l">ships rated D or E (failing)</div></div>
      </div>
      <div className="ciirow" aria-label="CII ratings">
        {"ABCDE".split("").map((c) => (plan.cii_counts[c] ? <div key={c} style={{ flexGrow: plan.cii_counts[c] / tot, background: CII_COLORS[c] }}>{c} {plan.cii_counts[c]}</div> : null))}
      </div>
      <div className="legend"><span><i style={{ background: "#ffb547" }} />VLSFO ship</span><span><i style={{ background: "#7aa7d9" }} />LNG ship</span><span><i style={{ border: "2px solid #ff5d5d" }} />rated D/E</span></div>
    </section>
  );
}

function Predictor({ d, t, mk }: P) {
  const ex = d.predictor.explain;
  const m = d.predictor.metrics;
  const c0 = mk("predict:conditions", 0.1), b0 = mk("predict:band", 0.38), e0 = mk("predict:explain", 0.45), m0 = mk("predict:models", 0.72);
  const ramp = ease(clamp((t - c0) / Math.max(2, (b0 - c0) * 0.8)));
  cue("predict:conditions", t, c0);
  const showBand = cue("predict:band", t, b0);
  const nC = Math.floor(clamp((t - e0) / Math.max(1.5, (m0 - e0) * 0.8)) * (ex.contributions.length + 0.99));
  if (nC > 0) act("predict:explain");
  const showModels = cue("predict:models", t, m0);
  const conds: [string, string, string][] = [
    ["Speed", "13.3 kn", `${(13.3 + 0.5 * ramp).toFixed(1)} kn`], ["Wave height", "0.5 m", `${(0.5 + 2.9 * ramp).toFixed(1)} m`],
    ["Wind", "4 m/s · beam", `${(4 + 9 * ramp).toFixed(0)} m/s · head`], ["Hull since cleaning", "0 days", `${Math.round(610 * ramp)} days`],
  ];
  const pred = lerp(ex.base, ex.prediction, ramp);
  const maxAbs = Math.max(...ex.contributions.map((c: any) => Math.abs(c.delta_t)));
  const best = m[0];
  const order = [...m].sort((a: any, b: any) => a.mape - b.mape);
  return (
    <>
      <section className="panel left" style={{ width: 900 }}>
        <h2>Step 1 · Predict fuel, honestly</h2>
        <p className="sub">Physics first, then an 8-qubit quantum kernel learns what physics misses. Forecast for {ex.vessel}.</p>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 26 }}>
          <div>
            {conds.map(([k, , v]) => (
              <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "9px 0", borderBottom: "1px solid var(--line)", fontSize: 19 }}>
                <span style={{ color: "var(--mist)" }}>{k}</span><b>{v}</b>
              </div>
            ))}
            <div style={{ marginTop: 20 }} className="kpi"><div className="v" style={{ fontSize: 72 }}>{pred.toFixed(1)} t</div>
              <div className="l">fuel per day{showBand ? ` · 90% range ${ex.lo.toFixed(1)}–${ex.hi.toFixed(1)} t` : ""}</div></div>
          </div>
          <div>
            <div style={{ fontSize: 16, color: "var(--mist)", marginBottom: 8 }}>Why? Each factor’s share (Shapley values)</div>
            {ex.contributions.slice(0, 6).map((c: any, i: number) => (
              <div key={c.feature} style={{ display: "grid", gridTemplateColumns: "150px 1fr 70px", alignItems: "center", gap: 8, margin: "7px 0", opacity: i < nC ? 1 : 0.15, transition: "opacity .4s" }}>
                <span style={{ fontSize: 16 }}>{c.feature}</span>
                <div style={{ height: 16, position: "relative" }}><div style={{ position: "absolute", left: c.delta_t < 0 ? `${50 - 50 * Math.abs(c.delta_t) / maxAbs}%` : "50%", width: `${50 * Math.abs(c.delta_t) / maxAbs}%`, height: "100%", background: c.delta_t > 0 ? "var(--amber)" : "var(--glass)", borderRadius: 2 }} /></div>
                <b style={{ fontSize: 16, textAlign: "right" }}>{c.delta_t > 0 ? "+" : ""}{c.delta_pct.toFixed(0)}%</b>
              </div>
            ))}
          </div>
        </div>
      </section>
      <section className="panel right" style={{ width: 520, opacity: showModels ? 1 : 0, transition: "opacity .6s" }}>
        <h2>Accuracy</h2>
        <p className="sub">Average error on 7,200 unseen noon reports (simulated)</p>
        {order.map((r: any) => (
          <div key={r.model} style={{ margin: "8px 0" }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 15 }}><span>{r.model}</span><b>{r.mape.toFixed(1)}%</b></div>
            <div style={{ height: 8, background: "var(--hull)", borderRadius: 2 }}><div style={{ height: 8, width: `${Math.min(100, r.mape * 5)}%`, background: r === best ? "var(--chart)" : "var(--mist)", borderRadius: 2 }} /></div>
          </div>
        ))}
        <div className="sub" style={{ marginTop: 12 }}>{best.coverage90.toFixed(0)}% of real values fall inside the 90% range.</div>
      </section>
    </>
  );
}

function Quantum({ d, t, mk }: P) {
  const Y = d.years[String(d.meta.main_year)];
  const snaps = Y.snapshots;
  const s0 = mk("quantum:search", 0.12), s1 = mk("quantum:collapsed", 0.82);
  const prog = clamp((t - s0) / (s1 - s0));
  cue("quantum:superposition", t, 0.3);
  cue("quantum:search", t, s0);
  cue("quantum:collapsed", t, s1);
  const fi = prog * (snaps.length - 1);
  const a = Math.floor(fi), b = Math.min(a + 1, snaps.length - 1), u = fi - a;
  const theta = (i: number, q: number) => lerp(snaps[a].theta[i][q], snaps[b].theta[i][q], u);
  const h = Y.history;
  const hi = Math.round(prog * (h.length - 1));
  const ent = h.slice(0, hi + 1).map((x: any) => x.entropy);
  const path = ent.map((e: number, i: number) => `${(i / (h.length - 1)) * 1000},${60 - e * 56}`).join(" ");
  return (
    <>
      <div className="qwall">
        {d.fleet.map((v: any, i: number) => (
          <BlochTile key={v.id} d={d} name={v.name} type={v.type} thetas={[6, 7, 8].map((q) => theta(i, q))} spin={t * 0.6 + i} />
        ))}
      </div>
      <div className="qstats">
        <div style={{ fontFamily: "var(--display)", fontSize: 30, fontWeight: 600, lineHeight: 1.05, width: 250 }}>Step 2 · Decide<br /><span style={{ color: "var(--chart)" }}>with 400 qubits</span></div>
        <div className="kpi"><div className="v">{h[hi].gen + 1}</div><div className="l">generation</div></div>
        <div className="kpi"><div className="v">{fmt(h[hi].evals)}</div><div className="l">fleet plans evaluated</div></div>
        <div className="kpi good"><div className="v">400</div><div className="l">qubits (10 per ship)</div></div>
        <div style={{ flex: 1 }}>
          <div className="l" style={{ color: "var(--mist)", fontSize: 15 }}>Uncertainty left in the qubits (entropy) — falls as they collapse onto choices</div>
          <svg viewBox="0 0 1000 64" preserveAspectRatio="none"><polyline points={path} fill="none" stroke="#3fb8af" strokeWidth="3" /></svg>
        </div>
      </div>
    </>
  );
}

function Pareto({ d, t, mk }: P) {
  const Y = d.years[String(d.meta.main_year)];
  const bau = Y.bau.objectives;
  const pts = Y.front.filter((p: any) => !p.pick);
  const shown = Math.floor(clamp((t - 0.4) / Math.max(1.5, mk("pareto:cheapest", 0.32) - 0.6)) * pts.length);
  if (shown > 0) act("pareto:front");
  const picks: ["cheapest" | "greenest" | "balanced", number][] = [["cheapest", 0.32], ["greenest", 0.52], ["balanced", 0.72]];
  let pick: string | null = null;
  for (const [k, at] of picks) if (cue("pareto:" + k, t, mk("pareto:" + k, at))) pick = k;
  const xs = [...Y.front.map((p: any) => p.cost), bau.cost_musd];
  const ys = [...Y.front.map((p: any) => p.co2), bau.wtw_kt];
  const [x0, x1, y0, y1] = [Math.min(...xs) * 0.95, Math.max(...xs) * 1.04, 0, Math.max(...ys) * 1.06];
  const W = 980, H = 640;
  const X = (v: number) => 70 + (v - x0) / (x1 - x0) * (W - 100);
  const Yp = (v: number) => H - 50 - (v - y0) / (y1 - y0) * (H - 80);
  const plan: Plan | null = pick ? Y.extremes[pick] : null;
  const label: Record<string, string> = { cheapest: "Cheapest plan", greenest: "Greenest plan", balanced: "Balanced plan" };
  return (
    <>
      <section className="panel left" style={{ width: 1060 }}>
        <h2>A menu of best trade-offs</h2>
        <p className="sub">Every dot is a plan nobody can beat on both cost and carbon at once (the Pareto front).</p>
        <svg width={W} height={H} role="img" aria-label="Cost versus emissions trade-off">
          <line x1={70} y1={H - 50} x2={W - 20} y2={H - 50} stroke="#9fb3c4" strokeOpacity=".4" />
          <line x1={70} y1={20} x2={70} y2={H - 50} stroke="#9fb3c4" strokeOpacity=".4" />
          <text x={W / 2} y={H - 12} fill="#9fb3c4" fontSize="16" textAnchor="middle">Running cost, $ million a year →</text>
          <text x={20} y={H / 2} fill="#9fb3c4" fontSize="16" textAnchor="middle" transform={`rotate(-90 20 ${H / 2})`}>CO₂e, thousand tonnes a year →</text>
          <circle cx={X(bau.cost_musd)} cy={Yp(bau.wtw_kt)} r={13} fill="#ffb547" />
          <text x={X(bau.cost_musd) + 18} y={Yp(bau.wtw_kt) + 6} fill="#ffb547" fontSize="19" fontWeight="600">Today</text>
          {pts.slice(0, shown).map((p: any, i: number) => <circle key={i} cx={X(p.cost)} cy={Yp(p.co2)} r={6} fill="#3fb8af" fillOpacity=".8" />)}
          {Y.front.filter((p: any) => p.pick).map((p: any) => (
            <g key={p.pick} opacity={pick === p.pick ? 1 : (pick ? 0.45 : 0)}>
              <circle cx={X(p.cost)} cy={Yp(p.co2)} r={pick === p.pick ? 15 : 9} fill="none" stroke="#7fd6b4" strokeWidth="3" />
              <text x={X(p.cost) + 20} y={Yp(p.co2) - 14} fill="#7fd6b4" fontSize="19" fontWeight="600">{label[p.pick]}</text>
            </g>
          ))}
        </svg>
      </section>
      {plan && (
        <section className="panel right" style={{ width: 560 }}>
          <h2>{label[pick!]}</h2>
          <p className="sub">Compared with today’s operation</p>
          <div className="kpis">
            <div className="kpi good"><div className="v">{pct(plan.objectives.wtw_kt, bau.wtw_kt)}%</div><div className="l">CO₂e ({fmt(plan.objectives.wtw_kt)} kt a year)</div></div>
            <div className={"kpi " + (plan.objectives.cost_musd > bau.cost_musd ? "bad" : "good")}><div className="v">{pct(plan.objectives.cost_musd, bau.cost_musd) > 0 ? "+" : ""}{pct(plan.objectives.cost_musd, bau.cost_musd)}%</div><div className="l">cost (${fmt(plan.objectives.cost_musd)}M a year)</div></div>
          </div>
          <MixBar d={d} plan={plan} />
        </section>
      )}
    </>
  );
}

function MixBar({ d, plan }: { d: Demo; plan: Plan }) {
  const mix = Object.entries(plan.fuel_mix).filter(([, v]) => v > 0.005).sort((a, b) => b[1] - a[1]);
  return (
    <>
      <div style={{ display: "flex", height: 26, borderRadius: 3, overflow: "hidden", marginTop: 20 }}>
        {mix.map(([k, v]) => <div key={k} style={{ width: `${v * 100}%`, background: fuelColor(d, k) }} />)}
      </div>
      <div className="legend">{mix.map(([k, v]) => <span key={k}><i style={{ background: fuelColor(d, k) }} />{fuelName(d, k)} {Math.round(v * 100)}%</span>)}</div>
    </>
  );
}

function TwinOverlay({ d, t, mk }: P) {
  const Y = d.years[String(d.meta.main_year)];
  cue("twin:split", t, 0.2);
  const cT = mk("twin:counters", 0.25);
  const counters = cue("twin:counters", t, cT);
  const cii = cue("twin:cii", t, mk("twin:cii", 0.6));
  const simH = Math.max(0, (t - cT)) * SIM_HOURS_PER_SEC * 40;
  const perH = (kt: number) => kt * 1000 / 8760;
  const tag = (plan: Plan, label: string, side: "l" | "r", col: string) => (
    <>
      <div className="tag-label" style={{ [side === "l" ? "left" : "right"]: 28, color: col } as any}>{label}</div>
      {counters && (
        <div className="counter" style={{ [side === "l" ? "left" : "right"]: 28 } as any}>
          <div className="v" style={{ color: col }}>{fmt(perH(plan.objectives.wtw_kt) * simH)} t</div>
          <div className="l">CO₂e emitted since you pressed play · {fmt(plan.objectives.wtw_kt)} kt a year</div>
          {cii && <div className="ciirow" style={{ height: 26, marginTop: 10 }}>{"ABCDE".split("").map((c) => plan.cii_counts[c] ? <div key={c} style={{ flexGrow: plan.cii_counts[c], background: CII_COLORS[c] }}>{c} {plan.cii_counts[c]}</div> : null)}</div>}
        </div>
      )}
    </>
  );
  return (
    <>
      <div style={{ position: "absolute", inset: "0 50% 0 0" }}>{tag(Y.bau, "Today", "l", "#ffb547")}</div>
      <div style={{ position: "absolute", inset: "0 0 0 50%" }}>{tag(Y.opt, "With GreenFleet-Q", "r", "#7fd6b4")}</div>
    </>
  );
}

function TimeMachine({ d, t, mk }: P) {
  const yr = timeYear(t, mk);
  cue("time:start", t, mk("time:start", 0.12));
  const years: number[] = d.meta.years;
  const keys = ["vlsfo", "lng", "biolng", "meoh", "emeoh", "nh3", "gnh3", "h2"];
  const mixAt = (y: number) => {
    const i = Math.min(years.length - 2, Math.max(0, years.findIndex((v) => v > y) - 1));
    const a = d.years[String(years[i])].opt.fuel_mix, b = d.years[String(years[i + 1])].opt.fuel_mix;
    const u = clamp((y - years[i]) / (years[i + 1] - years[i]));
    return Object.fromEntries(keys.map((k) => [k, lerp(a[k] || 0, b[k] || 0, u)]));
  };
  let cross = 0;
  for (let y = 2025; y <= 2050; y += 0.25) { const m = mixAt(y); if (m.gnh3 > m.lng) { cross = y; break; } }
  const crossed = yr >= cross;
  if (crossed) act("time:ammonia-overtakes-lng");
  if (yr > 2049.5) act("time:2050");
  const W = 1000, H = 420;
  const N = 60;
  const stacks = Array.from({ length: N + 1 }, (_, i) => { const y = 2025 + 25 * i / N; return { y, m: mixAt(y) }; });
  const areas = keys.map((k, ki) => {
    const top = stacks.map((s) => { const below = keys.slice(0, ki + 1).reduce((acc, kk) => acc + s.m[kk], 0); return [((s.y - 2025) / 25) * W, H - below * H]; });
    const bot = stacks.map((s) => { const below = keys.slice(0, ki).reduce((acc, kk) => acc + s.m[kk], 0); return [((s.y - 2025) / 25) * W, H - below * H]; }).reverse();
    return { k, d: "M" + [...top, ...bot].map((p) => p.join(",")).join("L") + "Z" };
  });
  const interp = (f: (y: number) => number) => { const i = Math.min(years.length - 2, Math.max(0, years.findIndex((v) => v > yr) - 1)); const u = clamp((yr - years[i]) / (years[i + 1] - years[i])); return lerp(f(years[i]), f(years[i + 1]), u); };
  const co2b = interp((y) => d.years[String(y)].bau.objectives.wtw_kt), co2o = interp((y) => d.years[String(y)].opt.objectives.wtw_kt);
  const cb = interp((y) => d.years[String(y)].bau.objectives.cost_musd), co = interp((y) => d.years[String(y)].opt.objectives.cost_musd);
  return (
    <section className="panel left" style={{ width: 1140 }}>
      <h2>Carbon-price time machine · {Math.round(yr)}</h2>
      <p className="sub">The fleet is re-planned for each year’s carbon price, fuel prices and green targets. Share of ships by fuel:</p>
      <svg width={W} height={H + 34} role="img" aria-label="Fuel mix by year">
        {areas.map((a) => <path key={a.k} d={a.d} fill={fuelColor(d, a.k)} fillOpacity=".88" />)}
        <line x1={((yr - 2025) / 25) * W} x2={((yr - 2025) / 25) * W} y1={0} y2={H} stroke="#e8eef2" strokeWidth="3" />
        {years.map((y) => <text key={y} x={((y - 2025) / 25) * W} y={H + 26} fill="#9fb3c4" fontSize="16" textAnchor={y === 2025 ? "start" : y === 2050 ? "end" : "middle"}>{y}</text>)}
        {crossed && <text x={((cross - 2025) / 25) * W + 10} y={40} fill="#e8eef2" fontSize="20" fontWeight="600">Green ammonia overtakes LNG ({Math.round(cross)})</text>}
      </svg>
      <div className="kpis" style={{ gridTemplateColumns: "repeat(4,1fr)", marginTop: 16 }}>
        <div className="kpi bad"><div className="v">{fmt(co2b)}</div><div className="l">kt CO₂e, old way</div></div>
        <div className="kpi good"><div className="v">{fmt(co2o)}</div><div className="l">kt CO₂e, GreenFleet-Q</div></div>
        <div className="kpi bad"><div className="v">${fmt(cb)}M</div><div className="l">cost, old way</div></div>
        <div className="kpi good"><div className="v">${fmt(co)}M</div><div className="l">cost, GreenFleet-Q</div></div>
      </div>
    </section>
  );
}

function Genealogy({ d, t, mk }: P) {
  cue("genealogy:sankey", t, 0.4);
  const gT = mk("genealogy:greenwash", 0.45);
  const hl = cue("genealogy:greenwash", t, gT);
  const nh3 = d.fuels.find((f: any) => f.key === "nh3"), vl = d.fuels.find((f: any) => f.key === "vlsfo");
  const bars: [string, number, string][] = [["Grey ammonia — what today’s CII rating counts (exhaust CO₂)", 0, "#7fd6b4"], ["Grey ammonia — full life cycle", nh3.wtw, "#ff5d5d"], ["Ship diesel (VLSFO) — full life cycle", vl.wtw, "#ffb547"]];
  const g = ease(clamp((t - gT - 0.5) / 2));
  return (
    <>
      <section className="panel left" style={{ width: 1180 }}>
        <h2>Fuel genealogy · from source to exhaust</h2>
        <p className="sub">Grams of CO₂e per unit of energy (gCO₂e/MJ), split into making the fuel and burning it.</p>
        <Sankey d={d} width={1120} height={640} highlight={hl ? "nh3" : null} reveal={clamp(t / 2.5)} />
      </section>
      <section className="panel right" style={{ width: 600, top: 300, opacity: hl ? 1 : 0, transition: "opacity .6s" }}>
        <h2>Greenwash detector</h2>
        <p className="sub">Grey ammonia scores an “A” today because its exhaust has no carbon. Its life cycle tells another story.</p>
        {bars.map(([l, v, c]) => (
          <div key={l} style={{ margin: "14px 0" }}>
            <div style={{ fontSize: 16, color: "var(--mist)" }}>{l}</div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{ height: 22, width: `${(v / 130) * 420 * g}px`, background: c, borderRadius: 2 }} />
              <b style={{ fontFamily: "var(--display)", fontSize: 30 }}>{Math.round(v * g)} g</b>
            </div>
          </div>
        ))}
        <p className="sub" style={{ marginTop: 10 }}>GreenFleet-Q optimises the full life cycle (well-to-wake), so this loophole cannot fool it.</p>
      </section>
    </>
  );
}

function Storm({ d, t, mk }: P) {
  const S = d.storm;
  const steps = [["storm:detected", 0.1], ["storm:forecast", 0.27], ["storm:replanning", 0.44], ["storm:new-plan", 0.62]] as const;
  const on = steps.map(([n, at]) => cue(n, t, mk(n, at)));
  const prog = clamp((t - mk("storm:replanning", 0.44)) / Math.max(1, mk("storm:new-plan", 0.62) - mk("storm:replanning", 0.44)));
  const k = S.keep.objectives, r = S.replan.objectives;
  return (
    <section className="panel right" style={{ width: 600 }}>
      <h2>Storm mode</h2>
      <p className="sub">A cyclone forms in the Bay of Bengal. What happens to the plan?</p>
      <ul className="steps">
        <li className={on[0] ? "on alert" : "alert"}><span className="dot" /><span>Cyclone detected — waves up to 6 m on {Object.keys(S.routes).length} routes</span></li>
        <li className={on[1] ? "on alert" : "alert"}><span className="dot" /><span>Predictor: {S.ships_affected} ships in its path would burn <b>+{S.extra_fuel_pct}% fuel</b> on the old plan</span></li>
        <li className={on[2] ? "on" : ""}><span className="dot" /><span>Re-planning all 400 qubits… {on[2] ? `${(prog * S.seconds).toFixed(1)} s` : ""}<div className="progress"><div style={{ width: `${prog * 100}%` }} /></div></span></li>
        <li className={on[3] ? "on" : ""}><span className="dot" /><span>New plan: ships slow down in heavy seas, cargo and schedules still met</span></li>
      </ul>
      {on[3] && (
        <div className="kpis" style={{ marginTop: 20 }}>
          <div className="kpi bad"><div className="v">{fmt(k.wtw_kt)}</div><div className="l">kt CO₂e a year, keeping the old plan</div></div>
          <div className="kpi good"><div className="v">{fmt(r.wtw_kt)}</div><div className="l">kt CO₂e a year, re-planned in {S.seconds} s</div></div>
        </div>
      )}
    </section>
  );
}

function Ask({ d, t, dur, mk }: P) {
  const Y = d.years[String(d.meta.main_year)];
  const o = Y.opt.objectives, b = Y.bau.objectives;
  const active = Y.opt.vessels.filter((v: any) => v.route).length;
  const ab = (Y.opt.cii_counts.A || 0) + (Y.opt.cii_counts.B || 0);
  const q = "We need every ship rated B or better by 2030, and hydrogen gets 30% cheaper. What should we change?";
  const h2 = Y.opt.vessels.filter((v: any) => v.fuel === "h2").length;
  const nh3 = Y.opt.vessels.filter((v: any) => v.fuel === "gnh3").length;
  const ans = `Plan ready in ${Y.seconds} s.\n• ${h2} ships run on green hydrogen on the short Colombo, Visakhapatnam and Haldia runs\n• ${nh3} ships switch to green ammonia, bunkered at Singapore and Rotterdam\n• Average speed eases to about 81% of design speed\n\nResult: ${ab} of ${active} trading ships rated A or B · CO₂e ${fmt(o.wtw_kt)} kt a year (${pct(o.wtw_kt, b.wtw_kt)}%) · cost $${fmt(o.cost_musd)}M a year (${pct(o.cost_musd, b.cost_musd)}%) compared with today.`;
  const qT = mk("ask:typing", 0.06), chipsT = mk("ask:constraints", 0.32), aT = mk("ask:answer", 0.45);
  cue("ask:typing", t, qT);
  const showChips = cue("ask:constraints", t, chipsT);
  const showA = cue("ask:answer", t, aT);
  const qn = Math.floor(clamp((t - qT) / Math.max(1.5, (chipsT - qT) * 0.85)) * q.length);
  const an = Math.floor(clamp((t - aT) / Math.max(2, dur - aT - 1.2)) * ans.length);
  return (
    <section className="panel right" style={{ width: 720 }}>
      <h2>Ask the fleet</h2>
      <p className="sub">Plain English in, an optimised plan out.</p>
      <div className="chat">
        {qn > 0 && <div className="msg user">{q.slice(0, qn)}</div>}
        {showChips && <div className="chips"><span className="chip">Year 2030</span><span className="chip">Every ship CII ≥ B</span><span className="chip">Hydrogen price −30%</span><span className="chip">Keep all cargo & schedules</span></div>}
        {showA && <div className="msg bot">{ans.slice(0, an)}</div>}
      </div>
    </section>
  );
}

function Outro({ d, t, mk }: P) {
  const Y = d.years[String(d.meta.main_year)];
  const o = Y.opt.objectives, b = Y.bau.objectives;
  const words = ["Predict.", "Optimise.", "Simulate.", "Act."];
  const n = [1, 2, 3, 4].filter((i) => cue("outro:w" + i, t, mk("outro:w" + i, 0.1 * i))).length;
  const stats = cue("outro:stats", t, mk("outro:stats", 0.5));
  return (
    <div className="card">
      <div className="words">{words.map((w, i) => <span key={w} className={i < n ? "on" : ""}>{w}</span>)}</div>
      <div className="stat" style={{ opacity: stats ? 1 : 0, transition: "opacity .6s" }}>
        <div>{pct(o.wtw_kt, b.wtw_kt)}%<small>CO₂e, simulated 2030 fleet</small></div>
        <div>{pct(o.cost_musd, b.cost_musd)}%<small>running cost</small></div>
        <div>0<small>ships rated D or E</small></div>
        <div>{d.storm.seconds} s<small>to re-plan around a storm</small></div>
      </div>
      <div className="meta" style={{ opacity: stats ? 1 : 0, transition: "opacity .6s" }}>
        <div><strong>GreenFleet-Q</strong>quantum-inspired today, quantum-ready tomorrow</div>
        <div><strong>Team Cup Of Tea</strong>Smart India Hackathon 2026</div>
      </div>
    </div>
  );
}
