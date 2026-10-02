#!/usr/bin/env python
"""Reusable race prediction with the saved CatBoost / Keras models.

Module use:
    from predict import RacePredictor
    predictor = RacePredictor()                      # loads models/ next to this file
    result = predictor.predict_race("prix_28_9_2026.csv")
    print(result["bet_list"])                        # e.g. [5, 2, 9, 1, 7, 4]
    result["table"]                                  # per-horse probabilities & votes

CLI:
    C:/Users/HP/anaconda3/python.exe predict.py RACE.csv [--out preds.csv] [--top 6]

Input: a turfomania-style scraped race CSV (N°, CHEVAL, Poids, COTE, Gain,
CORDE, S/A, track, descriptif, INDICS, horse_music, ...) or an
already-processed race table; missing columns are derived where possible
and defaulted to 0 otherwise.

Feature preparation replicates the training contract of plat.csv exactly:
per-race z-scores for COTE/POIDS/GAIN/IC/FORME/S_COEFF/AGE, raw N_WEIGHT
(kg), raw NUMERO/CORDE/SEXE/HIPPOID and raw 0/1 flags. This also fixes the
notebook's prediction-path bugs: min-maxed DIST/NUM_STARTERS/N_WEIGHT with
training-set statistics, odds truncated at the decimal point, and gains
lost to French number formatting ("37 904 EUR" -> 0).
"""

import argparse
import json
import os
import re
import sys
import unicodedata

import numpy as np
import pandas as pd

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from catboost import CatBoostClassifier

from race_features import (
    BINARY_FEATURES,
    DEFAULT_MODELS_DIR,
    HIPPODROME_MAPPING,
    PER_RACE_Z_FEATURES,
    canonicalize_columns,
    zscore_within_race,
)

try:
    from model_functions import clean_sex, success_coefficient
except Exception:

    def clean_sex(s):
        return {"H": "0", "M": "1", "F": "2"}.get(s, s)

    def success_coefficient(horse_music, discipline):
        try:
            max_score = 10
            cleaned = re.sub(r"[\(\[].*?[\)\]]", "", horse_music).strip()
            tokens = [t for t in cleaned.split() if len(t) >= 2]
            filtered = []
            for token in tokens:
                rank_str, disc = token[:-1], token[-1].lower()
                if disc == discipline.lower():
                    if rank_str.upper() in ("D", "A", "T", "NP") or rank_str == "0":
                        score = max_score
                    elif rank_str.isdigit():
                        score = int(rank_str)
                    else:
                        continue
                    filtered.append(score)
            last_ranks = filtered[:5]
            if not last_ranks:
                return 0.0
            weights = [5, 4, 3, 2, 1][: len(last_ranks)]
            weighted = [w * (11 - p) for w, p in zip(weights, last_ranks)]
            return round(sum(weighted) / sum(weights), 2)
        except Exception:
            return 0.0


# --- ports of the notebook's INDICS parsing (cell 27) ---
_COTATIONS_RE = re.compile(
    r"Evolution\s+cotations\s*:\s*(.*?)(?:\s*=>\s*([+-]?\d+(?:[.,]\d+)?))?"
    r"(?=\s*(?:Derni\xe8re\s+sortie|$))",
    re.IGNORECASE | re.DOTALL,
)
_FORME_RE = re.compile(r"Indice\s+de\s+forme\s+(\d+)", re.IGNORECASE)


def _extract_cotations(text):
    if not isinstance(text, str):
        return 0.0
    m = _COTATIONS_RE.search(text)
    if not m:
        return 0.0
    if m.group(2):
        try:
            return float(m.group(2).replace(",", "."))
        except ValueError:
            return 0.0
    return 0.0


def _extract_forme(text):
    if not isinstance(text, str):
        return 0
    m = _FORME_RE.search(text)
    return int(m.group(1)) if m else 0


def _clean_cote_value(v):
    """'3,6' -> 3.6 ; '-' / '' -> NaN (filled with the race median later)."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return np.nan
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", ".")
    if s in ("", "-", "--", "nan", "NaN", "None"):
        return np.nan
    return pd.to_numeric(s, errors="coerce")


def _clean_decimal_value(v):
    """'58,0' -> 58.0 (French decimal comma)."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return np.nan
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", ".")
    return pd.to_numeric(s, errors="coerce")


def _clean_gain_value(v):
    """'37 904 EUR' -> 37904.0 (keep digits only, as in training data creation)."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return np.nan
    if isinstance(v, (int, float)):
        return float(v)
    digits = "".join(ch for ch in str(v) if ch.isdigit())
    return float(digits) if digits else np.nan


def _norm_track(name):
    s = str(name).strip().upper()
    s = re.sub(r"[-_]+", " ", s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.split())


def _fill_per_race_median(s, groups):
    if s.notna().any():
        s = s.fillna(s.groupby(groups).transform("median"))
        if s.isna().any():
            s = s.fillna(s.median())
    return s.fillna(0.0)


class RacePredictor:
    """Loads the saved models once and predicts any number of races."""

    def __init__(self, models_dir=DEFAULT_MODELS_DIR, use_deep=True):
        self.models_dir = models_dir
        meta_path = os.path.join(models_dir, "catboost_meta.json")
        if not os.path.exists(meta_path):
            raise FileNotFoundError(
                f"{meta_path} not found - run train_catboost.py first"
            )
        with open(meta_path, encoding="utf-8") as f:
            self.meta = json.load(f)
        self.feature_columns = self.meta["feature_columns"]

        self.place = CatBoostClassifier()
        self.place.load_model(os.path.join(models_dir, self.meta["models"]["place_bet"]["file"]))
        self.dark = CatBoostClassifier()
        self.dark.load_model(os.path.join(models_dir, self.meta["models"]["dark_horse"]["file"]))
        self.rank = CatBoostClassifier()
        self.rank.load_model(os.path.join(models_dir, self.meta["models"]["rank"]["file"]))
        self.rank_classes = [int(c) for c in self.meta["models"]["rank"]["classes"]]

        self.deep = None
        self.deep_scaler = None
        deep_meta_path = os.path.join(models_dir, "deep_meta.json")
        if use_deep and os.path.exists(deep_meta_path):
            try:
                with open(deep_meta_path, encoding="utf-8") as f:
                    dmeta = json.load(f)
                if set(dmeta["feature_columns"]) != set(self.feature_columns):
                    print("warning: deep model feature set differs from catboost; "
                          "skipping deep model", file=sys.stderr)
                else:
                    from tensorflow import keras

                    import joblib

                    self.deep = keras.models.load_model(
                        os.path.join(models_dir, dmeta["model_file"]))
                    self.deep_scaler = joblib.load(
                        os.path.join(models_dir, dmeta["scaler_file"]))
            except Exception as e:
                print(f"warning: could not load deep model ({e}); "
                      f"continuing without it", file=sys.stderr)
                self.deep = None
                self.deep_scaler = None

    # ------------------------------------------------------------------ #
    # feature preparation                                                #
    # ------------------------------------------------------------------ #
    def prepare_race(self, data, source="turfomania"):
        """Turn a scraped/processed race CSV (or DataFrame) into model input.

        source: "turfomania" (default) or "zone-turf". zone-turf output has a
        FORME column on a different scale (bayesian musique score, ~3-10)
        than plat.csv's indice de forme, so it is dropped -> neutral z-score;
        its MUSIQUE column is mapped to HORSE_MUSIC for S_COEFF fallback.

        Returns (prepared_df, X, race_info): X holds exactly the training
        feature columns on the training scale; prepared_df keeps everything
        (raw display values in the *_RAW columns, z-scores in place).
        """
        if isinstance(data, pd.DataFrame):
            df = data.copy()
        else:
            df = pd.read_csv(data)
        df.columns = [str(c).strip().upper() for c in df.columns]
        if source == "zone-turf":
            df = df.drop(columns=["FORME", "IF"], errors="ignore")
            df = df.rename(columns={"MUSIQUE": "HORSE_MUSIC"})
        df = canonicalize_columns(df)
        df = df.replace({True: 1, False: 0})

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

        # COTE (odds): French decimal comma, '-' placeholder -> race median
        cote = (df["COTE"].map(_clean_cote_value) if "COTE" in df.columns
                else pd.Series(np.nan, index=df.index))
        df["COTE"] = _fill_per_race_median(cote, df[group])

        # POIDS: '58,0' -> 58.0
        poids = (df["POIDS"].map(_clean_decimal_value) if "POIDS" in df.columns
                 else pd.Series(np.nan, index=df.index))
        df["POIDS"] = _fill_per_race_median(poids, df[group])

        # GAIN: '37 904 EUR' -> 37904
        gain = (df["GAIN"].map(_clean_gain_value) if "GAIN" in df.columns
                else pd.Series(0.0, index=df.index))
        df["GAIN"] = gain.fillna(0.0)

        # AGE / SEXE from S/A ('F3' -> female, 3 years)
        sa = df["S/A"].astype(str).str.strip() if "S/A" in df.columns else None
        age = (pd.to_numeric(df["AGE"], errors="coerce") if "AGE" in df.columns
               else pd.Series(np.nan, index=df.index))
        if age.isna().all() and sa is not None:
            age = pd.to_numeric(sa.str[1:], errors="coerce")
        df["AGE"] = age.fillna(0.0)

        if "SEXE" in df.columns:
            sexe = df["SEXE"].map(clean_sex)
        elif sa is not None:
            sexe = sa.str[0].map(clean_sex)
        else:
            sexe = pd.Series("0", index=df.index)
        df["SEXE"] = pd.to_numeric(sexe, errors="coerce").fillna(0)

        # FORME from INDICS ('Indice de forme 8/10 ...')
        forme = (pd.to_numeric(df["FORME"], errors="coerce") if "FORME" in df.columns
                 else pd.Series(np.nan, index=df.index))
        if forme.isna().all() and "INDICS" in df.columns:
            forme = df["INDICS"].map(_extract_forme).astype(float)
        df["FORME"] = forme.fillna(0.0)

        # N_WEIGHT: raw weight evolution in kg (training contract, NOT min-maxed)
        if "N_WEIGHT" in df.columns:
            n_weight = pd.to_numeric(df["N_WEIGHT"], errors="coerce")
        elif "WEIGHT_EVOLUTION" in df.columns:
            n_weight = pd.to_numeric(df["WEIGHT_EVOLUTION"], errors="coerce")
        elif "INDICS" in df.columns:
            n_weight = df["INDICS"].map(_extract_cotations).astype(float)
        else:
            n_weight = pd.Series(0.0, index=df.index)
        df["N_WEIGHT"] = n_weight.fillna(0.0)

        # HIPPOID from the track name
        hippo = (pd.to_numeric(df["HIPPOID"], errors="coerce") if "HIPPOID" in df.columns
                 else pd.Series(np.nan, index=df.index))
        if hippo.isna().all() and "TRACK" in df.columns:
            tracks = df["TRACK"].map(_norm_track)
            hippo = tracks.map(lambda t: HIPPODROME_MAPPING.get(t))
            unknown = sorted({t for t in tracks.dropna() if t not in HIPPODROME_MAPPING})
            if unknown:
                print(f"warning: unmapped track(s) {unknown} -> HIPPOID 0", file=sys.stderr)
        df["HIPPOID"] = hippo.fillna(0)

        # IC = raw POIDS - raw COTE (as in training data creation)
        df["IC"] = (pd.to_numeric(df["POIDS"], errors="coerce")
                    - pd.to_numeric(df["COTE"], errors="coerce")).fillna(0.0)

        # S_COEFF from HORSE_MUSIC
        s_coeff = (pd.to_numeric(df["S_COEFF"], errors="coerce") if "S_COEFF" in df.columns
                   else pd.Series(np.nan, index=df.index))
        if s_coeff.isna().all() and "HORSE_MUSIC" in df.columns:
            s_coeff = df["HORSE_MUSIC"].map(
                lambda m: success_coefficient(m if isinstance(m, str) else "", "p"))
        df["S_COEFF"] = pd.to_numeric(s_coeff, errors="coerce").fillna(0.0)

        # CORDE / NUMERO
        corde = (pd.to_numeric(df["CORDE"], errors="coerce") if "CORDE" in df.columns
                 else pd.Series(0, index=df.index))
        df["CORDE"] = corde.fillna(0)
        df["NUMERO"] = pd.to_numeric(df["NUMERO"], errors="coerce").fillna(0).astype(int)

        # Q+ flags from the race description (as in the notebook)
        if ("Q+|1" not in df.columns or "Q+|0" not in df.columns) and "DESCRIPTIF" in df.columns:
            has_q = df["DESCRIPTIF"].astype(str).str.contains(r"Q\+", regex=True)
            if "Q+|1" not in df.columns:
                df["Q+|1"] = has_q.astype(int)
            if "Q+|0" not in df.columns:
                df["Q+|0"] = (~has_q).astype(int)

        # remaining binary flags: ensure presence, numeric
        for col in BINARY_FEATURES:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
            else:
                df[col] = 0

        # keep raw values for display / bet-list ordering before z-scoring
        for col in ("COTE", "POIDS", "S_COEFF"):
            df[col + "_RAW"] = df[col]

        # per-race z-scores - identical to the training normalization
        for col in PER_RACE_Z_FEATURES:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
        df = zscore_within_race(df, group_col=group)

        for col in self.feature_columns:
            if col not in df.columns:
                df[col] = 0
        X = df[self.feature_columns].astype(float)
        return df, X, race_info

    # ------------------------------------------------------------------ #
    # prediction                                                         #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_pronos(prepared):
        for col in ("PRONOS", "PRONO"):
            if col in prepared.columns:
                nums = set()
                for v in prepared[col].dropna().astype(str):
                    nums.update(int(x) for x in re.findall(r"\d+", v))
                return {n for n in nums if n > 0}
        return set()

    def predict_race(self, data, max_length=6, source="turfomania"):
        """Predict one race (CSV path or DataFrame).

        source: "turfomania" (default) or "zone-turf" (see prepare_race).

        Returns a dict with:
          table     per-horse probabilities, votes and bet tier
          bet_list  the final list of horse numbers to bet (tiered voting)
          race_info track / date / description when available
          pronos    parsed pronostics when a PRONOS column is present
        """
        prepared, X, race_info = self.prepare_race(data, source=source)

        out = pd.DataFrame(index=prepared.index)
        for col in ("NUMERO", "CHEVAL", "JOCKEY", "ENTRAINEUR", "CORDE",
                    "COTE_RAW", "POIDS_RAW", "S_COEFF_RAW"):
            if col in prepared.columns:
                out[col] = prepared[col]
        out = out.rename(columns={"COTE_RAW": "COTE", "POIDS_RAW": "POIDS",
                                  "S_COEFF_RAW": "S_COEFF"})

        out["place_prob"] = self.place.predict_proba(X)[:, 1]
        out["dark_prob"] = self.dark.predict_proba(X)[:, 1]
        rp = self.rank.predict_proba(X)
        classes = self.rank_classes
        out["p_win"] = rp[:, classes.index(1)]
        out["rank_pred"] = [classes[i] for i in rp.argmax(axis=1)]
        if self.deep is not None:
            Xs = self.deep_scaler.transform(X.values.astype(np.float32))
            out["place_prob_deep"] = np.asarray(self.deep.predict(Xs, verbose=0)).ravel()
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
        pronos = self._parse_pronos(prepared)
        if pronos:
            sources.append(set(out.index[out["NUMERO"].isin(pronos)]))
        out["votes"] = np.sum([out.index.isin(s).astype(int) for s in sources], axis=0)

        bet_list, tier_of = self._build_bet_list(out, max_length)
        out["bet_tier"] = [tier_of.get(n) for n in out["NUMERO"]]
        out = (out.assign(_s=pd.Series(out["bet_tier"], index=out.index).fillna(9))
                  .sort_values(["_s", "place_prob_avg"], ascending=[True, False])
                  .drop(columns=["_s"]))

        return {"table": out, "bet_list": bet_list, "race_info": race_info,
                "pronos": sorted(pronos)}

    def _build_bet_list(self, out, max_length=6):
        """Tiered voting, deterministic port of the notebook's create_optimized_list.

        Tier 1: picked by >= 3 sources (top-3 of each model, top-4 dark horses,
                pronostics)          Tier 2: top-2 by success coefficient
        Tier 3: top dark-horse candidate
        Tier 4: remaining horses with 2 votes
        Tier 5: fill by average place probability
        """
        votes_by_num = dict(zip(out["NUMERO"], out["votes"]))
        prob_by_num = dict(zip(out["NUMERO"], out["place_prob_avg"]))
        success_order = (out.sort_values(["S_COEFF", "place_prob_avg"],
                                         ascending=False)["NUMERO"].tolist()
                         if "S_COEFF" in out.columns else
                         out.sort_values("place_prob_avg",
                                         ascending=False)["NUMERO"].tolist())

        t1 = sorted([n for n, v in votes_by_num.items() if v >= 3],
                    key=lambda n: -prob_by_num.get(n, 0.0))
        t4 = sorted([n for n, v in votes_by_num.items() if v == 2],
                    key=lambda n: -prob_by_num.get(n, 0.0))
        t5 = out.sort_values("place_prob_avg", ascending=False)["NUMERO"].tolist()

        tiers = [t1, success_order[:2]]
        if len(out):
            tiers.append([int(out.loc[out["dark_prob"].idxmax(), "NUMERO"])])
        tiers.append(t4)
        tiers.append(t5)

        final, tier_of = [], {}
        for tnum, tier in enumerate(tiers, start=1):
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
    ap.add_argument("race_csv", help="scraped/processed race CSV")
    ap.add_argument("--models-dir", default=DEFAULT_MODELS_DIR)
    ap.add_argument("--out", default=None, help="write the full prediction table to this CSV")
    ap.add_argument("--top", type=int, default=6, help="bet list length (default 6)")
    ap.add_argument("--no-deep", action="store_true", help="skip the Keras model")
    ap.add_argument("--source", default="turfomania", choices=["turfomania", "zone-turf"],
                    help="data source of the race CSV (default turfomania)")
    args = ap.parse_args()

    predictor = RacePredictor(args.models_dir, use_deep=not args.no_deep)
    result = predictor.predict_race(args.race_csv, max_length=args.top,
                                    source=args.source)
    out = result["table"]

    header = " | ".join(f"{k}: {v}" for k, v in result["race_info"].items())
    print(header if header else os.path.basename(args.race_csv))
    if result["pronos"]:
        print(f"pronostics: {result['pronos']}")
    deep_state = "on" if predictor.deep is not None else "off"
    print(f"models: catboost (place/dark/rank) + deep {deep_state} | horses: {len(out)}\n")

    show = [c for c in ("NUMERO", "CHEVAL", "COTE", "S_COEFF", "place_prob",
                        "place_prob_deep", "place_prob_avg", "dark_prob",
                        "p_win", "rank_pred", "votes", "bet_tier")
            if c in out.columns]
    disp = out[show].copy()
    for c in ("COTE", "S_COEFF"):
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
