"""Shared singletons: trained predictor (cached on disk), fleet, fuel-table cache."""
from __future__ import annotations

import pickle
from pathlib import Path

from .domain import build_fleet, Scenario
from .fleet_model import FleetModel
from .predictor import Predictor

CACHE = Path(__file__).resolve().parent.parent / "cache"
CACHE.mkdir(exist_ok=True)
_PRED_FILE = CACHE / "predictor.pkl"

_predictor: Predictor | None = None
FLEET = build_fleet()
FUEL_TABLES: dict = {}


def predictor() -> Predictor:
    global _predictor
    if _predictor is None:
        if _PRED_FILE.exists():
            _predictor = pickle.loads(_PRED_FILE.read_bytes())
        else:
            _predictor = Predictor().train()
            _PRED_FILE.write_bytes(pickle.dumps(_predictor))
    return _predictor


def fleet_model(sc: Scenario) -> FleetModel:
    return FleetModel(FLEET, predictor(), sc, FUEL_TABLES)
