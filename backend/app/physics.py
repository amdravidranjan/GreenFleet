"""Vessel fuel physics.

`true_fuel_per_day` is the hidden "ground-truth" simulator used to create noon-report style
training data (it includes effects the predictor is NOT told about: part-load SFOC curve,
added wave/wind resistance, hull fouling growth, engine ageing, sensor noise and outliers).

`prior_fuel_per_day` is the textbook Admiralty-law estimate the predictor starts from; the
quantum-kernel model learns the multiplicative residual on top of it (grey-box modelling).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .domain import VESSEL_TYPES, ROUTES

FEATURES = ["speed_ratio", "draft_ratio", "hs", "wind", "wind_cos", "days_dd", "age", "load_est"]
FEATURE_LABELS = {
    "speed_ratio": "Speed", "draft_ratio": "Loading / draft", "hs": "Wave height",
    "wind": "Wind speed", "wind_cos": "Wind direction", "days_dd": "Hull fouling (days since dry-dock)",
    "age": "Engine age", "load_est": "Engine load",
}


def _displacement_factor(draft_ratio):
    return (0.3 + 0.7 * draft_ratio) ** (2 / 3)


def prior_fuel_per_day(mcr, design_speed, speed, draft_ratio, aux_sea_kw):
    p = mcr * 0.85 * (speed / design_speed) ** 3 * _displacement_factor(draft_ratio)
    return (p * 24 * 172 + aux_sea_kw * 24 * 220) / 1e6


def true_fuel_per_day(mcr, design_speed, speed, draft_ratio, hs, wind, wind_angle_deg, days_dd, age,
                      aux_sea_kw, rng=None, noise=True):
    head = 0.5 + 0.5 * np.cos(np.radians(wind_angle_deg))           # 1 = head seas, 0 = following
    v = speed / design_speed
    weather = 1 + (0.020 * hs ** 2 * (0.35 + 0.65 * head)) / np.maximum(v, 0.5) + 0.0005 * wind ** 2 * head
    fouling = 1 + 0.22 * (1 - np.exp(-days_dd / 480.0))
    p = mcr * 0.85 * v ** 3 * _displacement_factor(draft_ratio) * weather * fouling
    load = np.clip(p / mcr, 0.05, 1.15)
    sfoc = 166 * (1 + 0.35 * (load - 0.78) ** 2) + 30 * np.maximum(0.25 - load, 0) + 0.45 * age
    fuel = (p * 24 * sfoc + aux_sea_kw * 24 * 220 * (1 + 0.04 * hs)) / 1e6
    if noise:
        rng = rng or np.random.default_rng()
        fuel = fuel * np.exp(rng.normal(0, 0.035, np.shape(fuel)))
        outlier = rng.random(np.shape(fuel)) < 0.01
        fuel = np.where(outlier, fuel * rng.uniform(0.75, 1.3, np.shape(fuel)), fuel)
    return fuel


def feature_frame(mcr, design_speed, speed, draft_ratio, hs, wind, wind_angle_deg, days_dd, age):
    v = np.asarray(speed) / np.asarray(design_speed)
    return pd.DataFrame({
        "speed_ratio": v,
        "draft_ratio": draft_ratio,
        "hs": hs,
        "wind": wind,
        "wind_cos": np.cos(np.radians(wind_angle_deg)),
        "days_dd": days_dd,
        "age": age,
        "load_est": 0.85 * v ** 3 * _displacement_factor(np.asarray(draft_ratio)),
    })


def generate_noon_reports(n: int = 24000, seed: int = 11) -> pd.DataFrame:
    """Synthetic noon reports across all vessel types and route weather climates."""
    rng = np.random.default_rng(seed)
    t = rng.integers(0, len(VESSEL_TYPES), n)
    dwt = np.array([rng.uniform(*VESSEL_TYPES[i].dwt) for i in t])
    vd = np.array([VESSEL_TYPES[i].design_speed for i in t]) + rng.normal(0, 0.4, n)
    mcr = np.array([VESSEL_TYPES[i].mcr_per_dwt for i in t]) * dwt * rng.uniform(0.9, 1.1, n)
    aux = np.array([VESSEL_TYPES[i].aux_sea_kw for i in t])
    speed = vd * rng.uniform(0.5, 1.05, n)
    draft = rng.uniform(0.4, 1.0, n)
    route = rng.integers(0, len(ROUTES), n)
    monsoon = rng.random(n) < 0.33
    hs_mean = np.array([ROUTES[r].hs_mean for r in route]) * np.where(monsoon, 1.6, 1.0)
    hs = rng.gamma(4.0, hs_mean / 4.0)
    wind = np.clip(4.2 * hs ** 0.75 + rng.normal(0, 1.5, n), 0.5, 30)
    angle = rng.uniform(0, 180, n)
    days = rng.uniform(0, 900, n)
    age = rng.integers(1, 26, n).astype(float)
    fuel = true_fuel_per_day(mcr, vd, speed, draft, hs, wind, angle, days, age, aux, rng)
    df = feature_frame(mcr, vd, speed, draft, hs, wind, angle, days, age)
    df["vessel_type"] = [VESSEL_TYPES[i].key for i in t]
    df["dwt"], df["design_speed"], df["mcr"], df["aux_kw"] = dwt, vd, mcr, aux
    df["speed"], df["wind_angle"] = speed, angle
    df["prior"] = prior_fuel_per_day(mcr, vd, speed, draft, aux)
    df["fuel"] = fuel
    return df
