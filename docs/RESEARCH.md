# GreenFleet-Q — research notes and references

How each source is used: the IMO and EU documents give the rule formulas and emission factors
in the cost-and-carbon model (`backend/app/domain.py`, `fleet_model.py`); the research papers give
the quantum-inspired algorithm, the quantum kernel, the explanations and the benchmarks; the open
data sets are what will replace the simulated data in the next phase.

## Shipping rules and emissions
1. IMO Fourth GHG Study 2020 — shipping ≈ 2.9 % of global GHG. https://www.imo.org/en/ourwork/Environment/Pages/Fourth-IMO-Greenhouse-Gas-Study-2020.aspx
2. IMO CII and EEXI rating rules (MEPC 78) — A–E ratings, reference lines, reduction factors. https://www.imo.org/en/MediaCentre/HotTopics/Pages/EEXI-CII-FAQ.aspx
3. IMO Net-Zero Framework (MEPC 83, 2025) — GHG fuel-intensity targets and remedial-unit prices. https://www.imo.org/en/MediaCentre/PressBriefings/pages/IMO-approves-netzero-regulations.aspx
4. FuelEU Maritime — Regulation (EU) 2023/1805, GHG-intensity targets and penalty formula. https://eur-lex.europa.eu/eli/reg/2023/1805/oj
5. EU ETS extended to shipping. https://climate.ec.europa.eu/eu-action/transport/reducing-emissions-shipping-sector_en

## Quantum-inspired and AI methods
6. Han & Kim (2002), Quantum-inspired evolutionary algorithm for a class of combinatorial optimization, IEEE TEVC. https://doi.org/10.1109/TEVC.2002.804320
7. Havlíček et al. (2019), Supervised learning with quantum-enhanced feature spaces, Nature. https://doi.org/10.1038/s41586-019-0980-2
8. Shaydulin & Wild (2022), Importance of kernel bandwidth in quantum machine learning, Phys. Rev. A. https://doi.org/10.1103/PhysRevA.106.042407
9. Deb et al. (2002), NSGA-II, IEEE TEVC — classical benchmark. https://doi.org/10.1109/4235.996017
10. Lucas (2014), Ising formulations of many NP problems (QUBO), Frontiers in Physics. https://doi.org/10.3389/fphy.2014.00005
11. Psaraftis & Kontovas (2013), Speed models for energy-efficient maritime transportation, Transportation Research C. https://doi.org/10.1016/j.trc.2012.09.012
12. Lundberg & Lee (2017), A unified approach to interpreting model predictions (SHAP). https://arxiv.org/abs/1705.07874
13. Angelopoulos & Bates (2021), A gentle introduction to conformal prediction. https://arxiv.org/abs/2107.07511

## Open data and Indian policy
14. EU-MRV (THETIS) — annual fuel and CO₂ reports of ~12,000 ships. https://mrv.emsa.europa.eu/
15. NOAA MarineCadastre — AIS ship tracks. https://marinecadastre.gov/ais/
16. Copernicus ERA5 — wave and wind reanalysis. https://cds.climate.copernicus.eu/
17. Ministry of Ports, Shipping and Waterways — Maritime Amrit Kaal Vision 2047, Harit Sagar guidelines, Green Tug Transition Programme. https://shipmin.gov.in/
18. National Green Hydrogen Mission (MNRE). https://mnre.gov.in/national-green-hydrogen-mission/

## Honest status
- Prototype fuel predictor on 24,000 synthetic noon reports: 2.96 % mean error (classical RBF kernel 2.94 %, gradient boosting 4.02 %, random forest 5.77 %, physics only 19.3 %); 91 % of values inside the 90 % range.
- The optimised fleet plans shown in the demo video are an illustrative storyline; validating the optimiser on real AIS / EU-MRV data and against NSGA-II and exact MILP is the next phase.
