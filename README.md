# GreenFleet-Q

**Quantum-inspired fuel consumption prediction and green fleet optimisation**
Team **Cup Of Tea** (Team ID 141591) · Smart India Hackathon 2026

GreenFleet-Q predicts how much fuel every ship will burn and then plans the whole fleet — route,
speed, fuel (VLSFO, LNG, bio-LNG, methanol, e-methanol, grey/green ammonia, hydrogen) and shore
power — to cut fuel, cost and lifecycle (well-to-wake) emissions while meeting cargo demand,
schedules and the CII / EU ETS / FuelEU / IMO Net-Zero rules.

🌐 **Live demo:** https://greenfleet-q.vercel.app — mirror: https://amdravidranjan.me/GreenFleet/ (press **▶ Guided tour**)
📄 **Features:** [docs/FEATURES.md](docs/FEATURES.md) · **Research notes:** [docs/RESEARCH.md](docs/RESEARCH.md)

▶ **Demo video:** [`demo/GreenFleet-Q_demo.mp4`](demo/GreenFleet-Q_demo.mp4) (subtitles: [`demo/GreenFleet-Q_demo.srt`](demo/GreenFleet-Q_demo.srt))

> **About the numbers.** The demo is a *simulated* scenario: a 40-ship, 7-route fleet out of
> Chennai on synthetic data. Fleet, routes, business-as-usual costs and the fuel-predictor results
> come from the prototype engine in `backend/`; the optimised plans, trade-off menu, qubit replay
> and storm re-plan shown in the video are an illustrative storyline
> (`backend/scripts/simulate_demo.py`), not validated optimiser output.

## What is in the repo

| Path | What it is |
|---|---|
| `backend/app/domain.py` | Fuels (well-to-tank / tank-to-wake factors), vessel types, Chennai routes, year-by-year policy scenario (EU ETS, FuelEU, IMO NZF, CII) |
| `backend/app/physics.py` | Ship fuel physics and the synthetic noon-report generator |
| `backend/app/quantum_kernel.py` | 8-qubit ZZ feature-map quantum kernel, simulated exactly as a state vector, with Nyström kernel ridge regression |
| `backend/app/predictor.py` | Grey-box predictor (physics × quantum-kernel correction), conformal 90 % intervals, exact Shapley explanations, benchmark vs classical models |
| `backend/app/fleet_model.py` | 10-qubit-per-ship encoding, repair, vectorised cost / emissions / CII / penalty evaluation |
| `backend/app/qiea.py` | Multi-objective quantum-inspired evolutionary algorithm (qubit rotation gates, H-ε gate, NOT-gate mutation) |
| `backend/app/baselines.py`, `backend/scripts/benchmark.py` | NSGA-II and random-search baselines, hypervolume + Wilcoxon benchmark |
| `backend/scripts/export_demo.py`, `simulate_demo.py` | Build `frontend/public/demo-data.json` for the demo |
| `frontend/` | React + deck.gl + MapLibre demo: digital twin, qubit wall, trade-off menu, time machine, fuel genealogy, storm mode, assistant |
| `demo/` | Video pipeline: narration (edge-tts), recorder (Chrome screencast + console-logged action times), ffmpeg assembly |

## Run the demo

```bash
cd frontend
npm install
npm run dev            # open http://localhost:5173 and click through the sections
```

## Rebuild the video

```bash
cd frontend && npm run dev              # keep running
cd demo
npm install                              # playwright-core (drives your installed Chrome)
pip install edge-tts imageio-ffmpeg
python tts.py                            # narration clips, word timings, frontend/public/timeline.json
node record.mjs <tmpdir>                 # plays http://localhost:5173/?demo=1 and captures it
python build_video.py <tmpdir>           # -> demo/GreenFleet-Q_demo.mp4 + .srt
```

Every on-screen action is triggered by the narration word that describes it (marks in
`narration.json`), and the page logs each action to the Chrome console as
`[DEMO] {"ev": ..., "at": <ms>}`. The recorder captures those logs alongside screencast frames that
carry the browser's own timestamps, and `build_video.py` places the narration and subtitles at the
logged times.

## Engine (optional)

```bash
cd backend
pip install -r requirements.txt
python -m scripts.export_demo       # trains the predictor, runs the optimiser, writes demo data
python -m scripts.simulate_demo     # adds the illustrative storyline used by the video
python -m scripts.benchmark --seeds 10   # MO-QIEA vs NSGA-II vs random search
```
