#!/usr/bin/env python
"""Reusable trotting-race prediction with the saved CatBoost / Keras models.

Module use:
    from predict_trot import TrotPredictor
    predictor = TrotPredictor()                      # loads models/ next to this file
    result = predictor.predict_race("race_trot.csv")
    print(result["bet_list"])
    result["table"]                                  # per-horse probabilities

CLI:
    C:/Users/HP/anaconda3/python.exe predict_trot.py RACE.csv [--out preds.csv] [--top 6]

Input: a scraped trot race (CSV or DataFrame) with turfomania / zone-turf /
backend columns (N deg, CHEVAL, COTE, MUSIQUE, REC. / Record, DEF. / Def,
DIST. / DISTANCE, GAIN, AGE, S/A or SEXE, CLASS or DESCRIPTIF, TRACK /
HIPPODROME...). Missing columns are derived where possible and defaulted.
REC given as a chrono string ("1'12\"1") is converted to seconds, matching
the training data.

Feature preparation replicates the training contract of the TROT table
exactly via trot_features.prepare_frame: per-race z-scores for
COTE/REC/FORME/GAIN/AGE, raw NUMERO/DIST/ALLOC, and native categoricals.
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

from predict import _clean_cote_value, _clean_decimal_value, _clean_gain_value
from trot_features import (
    DEFAULT_MODELS_DIR,
    FEATURE_COLUMNS,
    canonicalize_columns,
    prepare_frame,
    build_deep_matrix,
    DEEP_FEATURE_COLUMNS,
)


def _chrono_to_seconds(v):
    """'1\'12"1' -> 72.1 ; 73.5 -> 73.5 ; junk -> NaN."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return np.nan
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    m = re.match(r"^(\d+)'(\d+)\"(\d)$", s)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2)) + int(m.group(3)) / 10.0
    digits = re.sub(r"[^\d.,]", "", s).replace(",", ".")
    return pd.to_numeric(digits, errors="coerce")


def _clean_def(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "0"
    s = str(v).strip().upper().replace("-", " ").strip()
    if s in ("", "0", "NAN", "NONE"):
        return "0"
    return " ".join(s.split())


def _digits_only(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return np.nan
    if isinstance(v, (int, float)):
        return float(v)
    digits = "".join(ch for ch in str(v) if ch.isdigit())
    return float(digits) if digits else np.nan


class TrotPredictor:
    """Loads the saved trot models once and predicts any number of races."""

    def __init__(self, models_dir=DEFAULT_MODELS_DIR, use_deep=True):
        self.models_dir = models_dir
        meta_path = os.path.join(models_dir, "trot_catboost_meta.json")
        if not os.path.exists(meta_path):
            raise FileNotFoundError(
                f"{meta_path} not found - run train_trot_catboost.py first"
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
        deep_meta_path = os.path.join(models_dir, "trot_deep_meta.json")
        if use_deep and os.path.exists(deep_meta_path):
            try:
                with open(deep_meta_path, encoding="utf-8") as f:
                    dmeta = json.load(f)
                if set(dmeta["feature_columns"]) != set(DEEP_FEATURE_COLUMNS):
                    print("warning: deep model feature set differs from the "
                          "trot contract; skipping deep model", file=sys.stderr)
                else:
                    from tensorflow import keras

                    self.deep = keras.models.load_model(
                        os.path.join(models_dir, dmeta["model_file"]))
            except Exception as e:
                print(f"warning: could not load deep model ({e}); "
                      "continuing without it", file=sys.stderr)
                self.deep = None

    # ------------------------------------------------------------------ #
    # feature preparation                                                #
    # ------------------------------------------------------------------ #
    def prepare_race(self, data):
        """Turn a scraped trot race (CSV path or DataFrame) into model input.

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
        for key, col in (("track", "TRACK"), ("date", "DATE"),
                         ("description", "DESCRIPTIF")):
            if col in df.columns:
                vals = [str(v) for v in df[col].dropna().unique()[:3]]
                if vals:
                    race_info[key] = " | ".join(vals)

        group = "ID_COURSE" if "ID_COURSE" in df.columns else "_RACE"
        if group == "_RACE" or df[group].isna().all():
            group = "_RACE"
        if group == "_RACE":
            df["_RACE"] = 0

        df["COTE"] = (df["COTE"].map(_clean_cote_value) if "COTE" in df.columns
                      else pd.Series(np.nan, index=df.index))
        df["GAIN"] = (df["GAIN"].map(_clean_gain_value) if "GAIN" in df.columns
                      else pd.Series(0.0, index=df.index))
        df["REC"] = (df["REC"].map(_chrono_to_seconds) if "REC" in df.columns
                     else pd.Series(np.nan, index=df.index))
        df["DIST"] = (df["DIST"].map(_digits_only) if "DIST" in df.columns
                      else pd.Series(np.nan, index=df.index))
        if "ALLOC" in df.columns:
            alloc = df["ALLOC"].map(_digits_only)
        else:
            alloc = pd.Series(np.nan, index=df.index)
        if alloc.isna().all():
            # zone-turf has no allocation column; the prize purse in
            # RACE_CONDITIONS ("46 000€") is the same figure as ALLOC.
            prize = pd.Series("", index=df.index)
            for col in ("RACE_CONDITIONS", "DESCRIPTIF"):
                if col in df.columns:
                    prize = df[col].astype(str)
                    break
            alloc = prize.str.extract(r"([\d][\d\s\u00a0]*)\s*€", expand=False)
            alloc = alloc.map(_digits_only)
        df["ALLOC"] = alloc
        df["NUMERO"] = (pd.to_numeric(df["NUMERO"], errors="coerce") if "NUMERO" in df.columns
                        else pd.Series(np.nan, index=df.index))

        age = (pd.to_numeric(df["AGE"], errors="coerce") if "AGE" in df.columns
               else pd.Series(np.nan, index=df.index))
        sa = df["S/A"].astype(str).str.strip() if "S/A" in df.columns else None
        if age.isna().all() and sa is not None:
            age = pd.to_numeric(sa.str[1:], errors="coerce")
        df["AGE"] = age

        from predict import clean_sex  # H/M/F -> 0/1/2 (codes used in training)

        sa_sexe = sa.str[0].map(clean_sex) if sa is not None else None
        if "SEXE" in df.columns:
            raw = df["SEXE"]
            sexe = raw.astype(str).str.strip().map(clean_sex)
            numeric = pd.to_numeric(raw, errors="coerce")
            sexe = sexe.where(numeric.isna(), numeric.astype("Int64").astype(str))
            # zone-turf leaves SEXE blank for hongres; S/A ("H5"/"M5") has it
            missing = (raw.isna() | raw.astype(str).str.strip().str.upper()
                       .isin(("", "NAN", "NONE")))
            if sa_sexe is not None:
                sexe = sexe.where(~missing, sa_sexe)
        elif sa_sexe is not None:
            sexe = sa_sexe
        else:
            sexe = pd.Series("0", index=df.index)
        df["SEXE"] = sexe.fillna("0")

        # CLASS / DISCIPLINE: live scrapes have no CLASS column; rebuild it
        # from RACE_CONDITIONS ("Attelé ... Course D" / "Monté ..."), falling
        # back to DESCRIPTIF, so the derive step sees discipline and course.
        if "CLASS" not in df.columns:
            text = None
            for col in ("RACE_CONDITIONS", "DESCRIPTIF"):
                if col in df.columns:
                    text = df[col].astype(str)
                    break
            if text is None:
                text = pd.Series("", index=df.index)
            cls = pd.Series("", index=df.index)
            cls[text.str.contains("Mont", case=False)] = "Monté"
            cls[text.str.contains("Attel", case=False)] = "Attelé"
            course = text.str.extract(
                r"(Course\s+(?:Europ\w*|[A-Ga-g]))", expand=False
            ).fillna("")
            df["CLASS"] = (cls + " " + course).str.strip()

        df["DEF"] = (df["DEF"].map(_clean_def) if "DEF" in df.columns
                     else pd.Series("0", index=df.index))

        df = df.replace({True: 1, False: 0})

        # keep raw display values before z-scoring
        for col in ("COTE", "REC", "GAIN", "FORME"):
            if col in df.columns:
                df[col + "_RAW"] = df[col]

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
        """Predict one trot race (CSV path or DataFrame).

        Returns a dict with:
          table     per-horse probabilities, votes and bet tier
          bet_list  the final list of horse numbers to bet
          race_info track / date / description when available
        """
        prepared, X, X_deep, race_info = self.prepare_race(data)

        out = pd.DataFrame(index=prepared.index)
        for col in ("NUMERO", "CHEVAL", "DRIVER", "ENTRAINEUR", "COTE_RAW",
                    "REC_RAW", "GAIN_RAW", "FORME_RAW"):
            if col in prepared.columns:
                out[col] = prepared[col]
        out = out.rename(columns={"COTE_RAW": "COTE", "REC_RAW": "REC",
                                  "GAIN_RAW": "GAIN", "FORME_RAW": "FORME"})

        out["place_prob"] = self.place.predict_proba(X)[:, 1]
        out["dark_prob"] = self.dark.predict_proba(X)[:, 1]
        rp = self.rank.predict_proba(X)
        classes = self.rank_classes
        out["p_win"] = rp[:, classes.index(1)]
        out["rank_pred"] = [classes[i] for i in rp.argmax(axis=1)]
        if self.deep is not None:
            out["place_prob_deep"] = np.asarray(
                self.deep.predict(X_deep.values, verbose=0)).ravel()
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
        """Tiered voting like the flat predictor, without the flat-only tiers.

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
    ap.add_argument("race_csv", help="scraped trot race CSV")
    ap.add_argument("--models-dir", default=DEFAULT_MODELS_DIR)
    ap.add_argument("--out", default=None, help="write the full prediction table to this CSV")
    ap.add_argument("--top", type=int, default=6, help="bet list length (default 6)")
    ap.add_argument("--no-deep", action="store_true", help="skip the Keras model")
    args = ap.parse_args()

    predictor = TrotPredictor(args.models_dir, use_deep=not args.no_deep)
    result = predictor.predict_race(args.race_csv, max_length=args.top)
    out = result["table"]

    header = " | ".join(f"{k}: {v}" for k, v in result["race_info"].items())
    print(header if header else os.path.basename(args.race_csv))
    deep_state = "on" if predictor.deep is not None else "off"
    print(f"models: catboost (place/dark/rank) + deep {deep_state} | horses: {len(out)}\n")

    show = [c for c in ("NUMERO", "CHEVAL", "DRIVER", "COTE", "REC", "GAIN", "FORME",
                        "place_prob", "place_prob_deep", "place_prob_avg",
                        "dark_prob", "p_win", "rank_pred", "votes", "bet_tier")
            if c in out.columns]
    disp = out[show].copy()
    for c in ("COTE", "REC", "GAIN", "FORME"):
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
