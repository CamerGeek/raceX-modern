"""Temp plumbing check: SEXE / ALLOC / CLASS normalization on the serve path.

Runs prepare_race only (no model loading) on the two saved live trot races.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "models"))

import pandas as pd

from app.services.supabase_client import SupabaseClientWrapper
from predict_trot import TrotPredictor
from trot_features import FEATURE_COLUMNS

client = SupabaseClientWrapper()
predictor = TrotPredictor.__new__(TrotPredictor)
predictor.feature_columns = FEATURE_COLUMNS

RACES = {
    "turfomania": "5e8ea050-675c-4886-9745-bea86c5bf8cd",
    "zone-turf": "99d78245-8886-4ba5-b294-d4c4ecd7e867",
}

for label, race_id in RACES.items():
    race = client.select_one("races", filters=[("id", "eq", race_id)])
    if not race:
        print(f"{label}: race {race_id} NOT FOUND")
        continue
    rows = client.list(
        "trot_race_runners",
        filters=[("race_id", "eq", race_id)],
        limit=1000,
        order_by=("runner_number", "asc"),
    )
    frame = pd.DataFrame(
        [r.get("raw_data") if isinstance(r.get("raw_data"), dict) else r for r in rows]
    )
    frame = frame.drop(columns=["POIDS", "IC", "HANDICAP_DISTANCE"], errors="ignore")
    prepared, X, X_deep, info = predictor.prepare_race(frame)
    print(f"== {label} ({race.get('race_key')}, {race.get('source')}) rows={len(frame)} ==")
    print("  SEXE    :", prepared["SEXE"].tolist())
    print("  ALLOC   :", prepared["ALLOC"].tolist())
    print("  DIST    :", prepared["DIST"].tolist())
    for col in ("DISCIPLINE", "COURSE", "DSCP", "AUTO", "DEPART", "Q_PLUS", "GROUPE"):
        if col in prepared.columns:
            print(f"  {col:8s}:", prepared[col].unique().tolist())
    print("  X shape:", X.shape, "| deep:", X_deep.shape,
          "| NaNs:", int(X.isna().sum().sum()))
