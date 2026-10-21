#!/usr/bin/env python
"""Reusable obstacle-race prediction with the saved CatBoost / Keras models.

Module use:
    from predict_obstacles import ObstaclesPredictor
    predictor = ObstaclesPredictor()                 # loads models/ next to this file
    result = predictor.predict_race("race_obstacles.csv")
    print(result["bet_list"])
    result["table"]                                  # per-horse probabilities

CLI:
    C:/Users/HP/anaconda3/python.exe predict_obstacles.py RACE.csv [--out preds.csv] [--top 6]

Input: a scraped obstacle race (CSV or DataFrame) with turfomania columns
(N°, CHEVAL, COTE, POIDS, S/A, DESCRIPTIF, TRACK/HIPPODROME, HORSE_MUSIC,
PAST_POIDS, DISTANCE, ...). Missing columns are derived where possible
(HIPPODROME name -> HIPPOID, HORSE_MUSIC -> incident + form features, S/A ->
SEXE/AGE) and defaulted to 0 - a race without musique carries no incident
signal, which is a documented degradation, not an error.

Feature preparation replicates the training contract of processed_data.csv
exactly via obstacles_features.prepare_frame: per-race z-scores for
COTE/POIDS/GAIN/PAST_POIDS/AGE/IC/FS/FH/FC/FT/N_WEIGHT, raw NUMERO/DISTANCE/
STARTERS/S_COEFF/incident block, native SEXE/HIPPOID categoricals, binary
indicators.
"""

import argparse
import json
import os
import re
import sys

import numpy as np
import pandas as pd

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from catboost import CatBoostClassifier

from obstacles_features import (
    DEFAULT_MODELS_DIR,
    DEEP_FEATURE_COLUMNS,
    FEATURE_COLUMNS,
    canonicalize_columns,
    prepare_frame,
    build_deep_matrix,
    compute_d_perf,
    success_coefficient,
    extract_incident_features,
)


def _clean_number(v):
    """'5,5' / '5.5' / 5.5 -> 5.5 ; ranges like '5.5-6' -> 5.5 ; junk -> NaN."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return np.nan
    if isinstance(v, (int, float)):
        return float(v)
    m = re.match(r"^\s*(\d+(?:[.,]\d+)?)", str(v))
    return float(m.group(1).replace(",", ".")) if m else np.nan


def _digits_only(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return np.nan
    if isinstance(v, (int, float)):
        return float(v)
    digits = "".join(ch for ch in str(v) if ch.isdigit())
    return float(digits) if digits else np.nan


def _extract_weight_evolution(text):
    """'Evolution cotations : 54 => +2' style snippets -> the evolution number."""
    if not isinstance(text, str):
        return np.nan
    m = re.search(
        r"Evolution\s+cotations\s*:\s*(.*?)(?:\s*=>\s*([+-]?\d+(?:[.,]\d+)?))?"
        r"(?=\s*(?:Dernière sortie|$))",
        text, re.IGNORECASE | re.DOTALL,
    )
    if not m or not m.group(2):
        return 0.0
    return float(m.group(2).replace(",", "."))


def _discipline_letter(descriptif):
    d = str(descriptif).lower()
    if "steeple" in d:
        return "s"
    if "cross" in d:
        return "c"
    if "haie" in d or "hedge" in d or "hurdle" in d:
        return "h"
    return ""


class ObstaclesPredictor:
    """Loads the saved obstacle models once and predicts any number of races."""

    def __init__(self, models_dir=DEFAULT_MODELS_DIR, use_deep=True):
        self.models_dir = models_dir
        meta_path = os.path.join(models_dir, "obstacles_catboost_meta.json")
        if not os.path.exists(meta_path):
            raise FileNotFoundError(
                f"{meta_path} not found - run train_obstacles_catboost.py first"
            )
        with open(meta_path, encoding="utf-8") as f:
            self.meta = json.load(f)
        self.feature_columns = self.meta["feature_columns"]
        self.cat_features = self.meta["categorical_features"]

        self.place = CatBoostClassifier()
        self.place.load_model(os.path.join(models_dir, self.meta["models"]["place_bet"]["file"]))
        self.dark = CatBoostClassifier()
        self.dark.load_model(os.path.join(models_dir, self.meta["models"]["dark_horse"]["file"]))
        self.rank = CatBoostClassifier()
        self.rank.load_model(os.path.join(models_dir, self.meta["models"]["rank"]["file"]))
        self.rank_classes = [int(c) for c in self.meta["models"]["rank"]["classes"]]

        self.deep = None
        self.deep_scaler = None
        deep_meta_path = os.path.join(models_dir, "obstacles_deep_meta.json")
        if use_deep and os.path.exists(deep_meta_path):
            try:
                with open(deep_meta_path, encoding="utf-8") as f:
                    dmeta = json.load(f)
                if set(dmeta["feature_columns"]) != set(DEEP_FEATURE_COLUMNS):
                    print("warning: deep model feature set differs from the "
                          "obstacles contract; skipping deep model", file=sys.stderr)
                else:
                    from tensorflow import keras

                    import joblib
                    self.deep_scaler = joblib.load(
                        os.path.join(models_dir, dmeta["scaler_file"]))
                    self.deep = keras.models.load_model(
                        os.path.join(models_dir, dmeta["model_file"]))
            except Exception as e:
                print(f"warning: could not load deep model ({e}); "
                      "continuing without it", file=sys.stderr)
                self.deep = None
                self.deep_scaler = None

    # ------------------------------------------------------------------ #
    # feature preparation                                                #
    # ------------------------------------------------------------------ #
    def prepare_race(self, data):
        """Turn a scraped obstacle race (CSV path or DataFrame) into model input.

        Returns (prepared_df, X, X_deep, race_info): X holds exactly the
        CatBoost training columns; X_deep the one-hot matrix for the Keras
        model. prepared_df keeps raw display values in the *_RAW columns.
        """
        if isinstance(data, pd.DataFrame):
            df = data.copy()
        else:
            df = pd.read_csv(data)
        df.columns = [str(c).strip().upper() for c in df.columns]
        df = canonicalize_columns(df)

        race_info = {}
        for key, col in (("track", "HIPPODROME"), ("date", "DATE"),
                         ("description", "DESCRIPTIF"), ("distance", "DISTANCE")):
            if col in df.columns:
                vals = [str(v) for v in df[col].dropna().unique()[:3]]
                if vals:
                    race_info[key] = " | ".join(vals)

        group = "ID_COURSE" if "ID_COURSE" in df.columns else "_RACE"
        if group == "_RACE" or df[group].isna().all():
            group = "_RACE"
        if group == "_RACE":
            df["_RACE"] = 0

        df["COTE"] = (df["COTE"].map(_clean_number) if "COTE" in df.columns
                      else pd.Series(np.nan, index=df.index))
        if "COTE" in df.columns:
            df["COTE_RAW"] = df["COTE"]
        if "POIDS" in df.columns:
            df["POIDS"] = pd.to_numeric(
                df["POIDS"].astype(str).str.replace(",", ".", regex=False),
                errors="coerce")
        df["NUMERO"] = (pd.to_numeric(df["NUMERO"], errors="coerce")
                        if "NUMERO" in df.columns
                        else pd.Series(np.nan, index=df.index))
        df["DISTANCE"] = (df["DISTANCE"].map(_digits_only) if "DISTANCE" in df.columns
                          else pd.Series(np.nan, index=df.index))

        starters = (pd.to_numeric(df["STARTERS"], errors="coerce")
                    if "STARTERS" in df.columns
                    else pd.Series(np.nan, index=df.index))
        if starters.isna().all():
            starters = df.groupby(group)["NUMERO"].transform("count")
        df["STARTERS"] = starters

        age = (pd.to_numeric(df["AGE"], errors="coerce") if "AGE" in df.columns
               else pd.Series(np.nan, index=df.index))
        if age.isna().all() and "S/A" in df.columns:
            age = pd.to_numeric(df["S/A"].astype(str).str.strip().str[1:],
                                errors="coerce")
        df["AGE"] = age

        if "PAST_POIDS" in df.columns:
            df["PAST_POIDS"] = pd.to_numeric(
                df["PAST_POIDS"].astype(str).str.replace(",", ".", regex=False),
                errors="coerce")

        # musique-derived blocks: form scores, success coefficient, incidents
        if "HORSE_MUSIC" in df.columns:
            perf = df["HORSE_MUSIC"].map(
                lambda m: compute_d_perf(m) if isinstance(m, str) and m.strip()
                else compute_d_perf(""))
            df["FH"] = perf.map(lambda x: x.get("h", 0))
            df["FS"] = perf.map(lambda x: x.get("s", 0))
            df["FC"] = perf.map(lambda x: x.get("c", 0))
            df["FT"] = perf.map(lambda x: x.get("global", 0))
            letter = df["DESCRIPTIF"].map(_discipline_letter) \
                if "DESCRIPTIF" in df.columns else pd.Series("", index=df.index)
            df["DISCIPLINE"] = letter
            form_column = letter.map({"h": "FH", "s": "FS", "c": "FC"})
            df["FORM_DISCIPLINE"] = [
                scores.get({"FH": "h", "FS": "s", "FC": "c"}.get(column), 0) or np.nan
                for scores, column in zip(perf, form_column)
            ]
            df["S_COEFF"] = [
                success_coefficient(m, l) if isinstance(m, str) and m.strip() else 0.0
                for m, l in zip(df["HORSE_MUSIC"], letter)
            ]
            df["MUSIC_AVAILABLE"] = df["HORSE_MUSIC"].astype(str).str.strip().ne("").astype(int)
            df = extract_incident_features(df)

        if "IC" not in df.columns:
            df["IC"] = df.get("POIDS", 0) - df.get("COTE", 0)

        if "N_WEIGHT" not in df.columns and "INDICS" in df.columns:
            df["N_WEIGHT"] = df["INDICS"].map(_extract_weight_evolution)

        df = df.replace({True: 1, False: 0})

        prepared = prepare_frame(df)

        X = prepared[[c for c in self.feature_columns]].copy()
        for col in self.feature_columns:
            if col not in X.columns:
                X[col] = 0
        X = X[self.feature_columns]
        X_deep = build_deep_matrix(prepared)[DEEP_FEATURE_COLUMNS].astype(np.float32)
        return prepared, X, X_deep, race_info

    # ------------------------------------------------------------------ #
    # prediction                                                         #
    # ------------------------------------------------------------------ #
    def predict_race(self, data, max_length=6):
        """Predict one obstacle race (CSV path or DataFrame).

        Returns a dict with:
          table     per-horse probabilities, votes and bet tier
          bet_list  the final list of horse numbers to bet
          race_info track / date / description when available
        """
        prepared, X, X_deep, race_info = self.prepare_race(data)

        out = pd.DataFrame(index=prepared.index)
        for col in (
            "NUMERO", "CHEVAL", "JOCKEY", "COTE_RAW", "DISTANCE",
            "DISCIPLINE", "FORM_DISCIPLINE", "S_COEFF", "MUSIC_AVAILABLE",
            "INCIDENT_COUNT", "HAS_FALLEN", "HAS_STOPPED",
            "FALL_COUNT", "STOP_COUNT",
        ):
            if col in prepared.columns:
                out[col] = prepared[col]
        out = out.rename(columns={"COTE_RAW": "COTE"})

        out["place_prob"] = self.place.predict_proba(X)[:, 1]
        out["dark_prob"] = self.dark.predict_proba(X)[:, 1]
        rp = self.rank.predict_proba(X)
        classes = self.rank_classes
        out["p_win"] = rp[:, classes.index(1)]
        out["rank_pred"] = [classes[i] for i in rp.argmax(axis=1)]
        if self.deep is not None:
            Xs = self.deep_scaler.transform(X_deep.values.astype(np.float32))
            out["place_prob_deep"] = np.asarray(
                self.deep.predict(Xs, verbose=0)).ravel()
        else:
            out["place_prob_deep"] = np.nan
        out["place_prob_avg"] = out[["place_prob", "place_prob_deep"]].mean(axis=1)

        # votes: how many sources put the horse in their top picks
        sources = [
            set(out["place_prob"].nlargest(3).index),
            set(out["p_win"].nlargest(3).index),
            set(out["dark_prob"].nlargest(min(4, len(out))).index),
        ]
        if out["place_prob_deep"].notna().any():
            sources.append(set(out["place_prob_deep"].nlargest(3).index))
        out["votes"] = np.sum([out.index.isin(s).astype(int) for s in sources], axis=0)

        bet_list, tier_of = self._build_bet_list(out, max_length)
        out["bet_tier"] = [tier_of.get(n) for n in out["NUMERO"]]
        out = (out.assign(_s=pd.Series(out["bet_tier"], index=out.index).fillna(9))
                  .sort_values(["_s", "place_prob_avg"], ascending=[True, False])
                  .drop(columns=["_s"]))

        return {"table": out, "bet_list": bet_list, "race_info": race_info}

    @staticmethod
    def _build_bet_list(out, max_length=6):
        """Tiered voting like the flat/trot predictors.

        Tier 1: picked by >= 3 sources (top-3 of each model, top-4 dark)
        Tier 2: picked by 2 sources
        Tier 3: fill by average place probability
        """
        votes_by_num = dict(zip(out["NUMERO"], out["votes"]))
        prob_by_num = dict(zip(out["NUMERO"], out["place_prob_avg"]))

        t1 = sorted([n for n, v in votes_by_num.items() if v >= 3],
                    key=lambda n: -prob_by_num.get(n, 0.0))
        t2 = sorted([n for n, v in votes_by_num.items() if v == 2],
                    key=lambda n: -prob_by_num.get(n, 0.0))
        t3 = out.sort_values("place_prob_avg", ascending=False)["NUMERO"].tolist()

        final, tier_of = [], {}
        for tnum, tier in enumerate([t1, t2, t3], start=1):
            for n in tier:
                if n not in tier_of:
                    tier_of[n] = tnum
                    final.append(int(n))
                if len(final) >= max_length:
                    break
            if len(final) >= max_length:
                break
        return final[:max_length], tier_of


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("race_csv", help="scraped obstacle race CSV")
    ap.add_argument("--models-dir", default=DEFAULT_MODELS_DIR)
    ap.add_argument("--out", default=None, help="write the full prediction table to this CSV")
    ap.add_argument("--top", type=int, default=6, help="bet list length (default 6)")
    ap.add_argument("--no-deep", action="store_true", help="skip the Keras model")
    args = ap.parse_args()

    predictor = ObstaclesPredictor(args.models_dir, use_deep=not args.no_deep)
    result = predictor.predict_race(args.race_csv, max_length=args.top)
    out = result["table"]

    header = " | ".join(f"{k}: {v}" for k, v in result["race_info"].items())
    print(header if header else os.path.basename(args.race_csv))
    deep_state = "on" if predictor.deep is not None else "off"
    print(f"models: catboost (place/dark/rank) + deep {deep_state} | horses: {len(out)}\n")

    show = [c for c in ("NUMERO", "CHEVAL", "JOCKEY", "COTE", "DISTANCE",
                        "place_prob", "place_prob_deep", "place_prob_avg",
                        "dark_prob", "p_win", "rank_pred", "votes", "bet_tier")
            if c in out.columns]
    disp = out[show].copy()
    for c in ("COTE",):
        if c in disp.columns:
            disp[c] = pd.to_numeric(disp[c], errors="coerce").round(2)
    for c in ("place_prob", "place_prob_deep", "place_prob_avg", "dark_prob", "p_win"):
        if c in disp.columns:
            disp[c] = pd.to_numeric(disp[c], errors="coerce").round(4)
    print(disp.to_string(index=False))
    print(f"\nBET LIST (top {args.top}): {result['bet_list']}")
    print("note: probabilities are class-balanced ranking scores, "
          "not calibrated probabilities")
    if args.out:
        out.to_csv(args.out, index=False, encoding="utf-8-sig")
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
