# GreenFleet-Q — features

Live demo: **https://greenfleet-q.vercel.app** (mirror: **https://amdravidranjan.me/GreenFleet/**)
Press **▶ Guided tour** for the narrated 4-minute walkthrough, or click any section in the top bar.
Best viewed on a laptop or desktop screen.

> The demo is a simulated 40-ship, 7-route fleet out of Chennai on synthetic data. See the
> README for which numbers come from the prototype engine and which are an illustrative storyline.

| Section | What you see | Why it matters |
|---|---|---|
| **Fleet today** | 40 ships sailing from Chennai to Colombo, Singapore, Port Klang, Jebel Ali, Haldia, Visakhapatnam and Rotterdam; yearly CO₂e, cost, fuel and CII ratings; ships rated D/E pulse red | Shows the cost and compliance problem of running a fleet the usual way |
| **Fuel predictor** | Forecast for one ship as the sea gets rough: speed, waves, wind, hull fouling; a 90 % range; each factor's share of the extra fuel; accuracy against classical models | Honest forecasts — physics first, then an 8-qubit quantum kernel learns what physics misses |
| **Quantum engine** | 40 tiles, each ship's fuel qubits drawn as Bloch spheres that start in superposition and collapse onto a choice | Makes the quantum-inspired search visible: 10 qubits per ship, 400 for the fleet |
| **Trade-offs** | The Pareto front of best plans: cheapest, greenest and balanced, compared with today | Managers choose knowingly instead of receiving one black-box answer |
| **Digital twin** | Split screen, today vs the GreenFleet-Q plan, ships coloured by fuel, live CO₂ counters and CII bars | The before/after in one glance |
| **Time machine** | 2025 → 2050: fuel mix re-planned for each year's carbon price and targets | Shows *when* green ammonia overtakes LNG, and the long-run cost of doing nothing |
| **Fuel genealogy** | Sankey diagram from fuel source → fuel → emissions from making vs burning it; greenwash detector | Exposes fuels that look green on the exhaust but are not over their life cycle (grey ammonia) |
| **Storm mode** | A cyclone in the Bay of Bengal, routes in its path, extra fuel predicted, fleet re-planned | Plans adapt in seconds instead of days |
| **Ask the fleet** | A plain-English question turned into constraints and answered with a plan and numbers | No optimisation expertise needed |

## Under the hood (prototype engine in `backend/`)

- **Fuel prediction:** grey-box model = Admiralty-law physics × exp(quantum-kernel correction);
  8-qubit ZZ feature map simulated exactly; Nyström kernel ridge regression; split-conformal
  90 % intervals; exact Shapley explanations.
- **Fleet model:** route, speed, fuel and shore-power decisions per ship; annual cost (fuel,
  retrofit capex, opex, EU ETS, FuelEU penalty, IMO Net-Zero Framework levy), well-to-wake
  GHG, energy; constraints for cargo demand, sailing frequency, CII rating and fuel availability.
- **Optimiser:** multi-objective quantum-inspired evolutionary algorithm (qubit rotation gates,
  H-ε gate, quantum NOT mutation, Pareto archive), benchmarked against NSGA-II and random search.
- **Quantum-ready:** the decision model can be written as a QUBO for quantum annealers or QAOA.
