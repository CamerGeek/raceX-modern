"""Shared feature contract for the French trotting models.

Single source of truth for how model input features are built. Imported by
the training scripts (train_trot_catboost.py, train_trot_deep_learning.py)
and the serving module (predict.py) so the transformation applied at
prediction time is exactly the one the models were trained on.

Training data: TROT_RACING.db, table TROT (244,124 rows / 29,229 races,
2012-04 .. 2025-05, 45 hippodromes, disciplines Attelé + Monté). Unlike
plat.csv the table stores RAW values, so load_training_data applies the
per-race z-score itself - the identical transform serve time applies to a
single new race, which is why no statistics need to be saved.

Contract:
  * COTE, REC, FORME, GAIN, AGE are z-scored WITHIN each race (groupby
    ID_COURSE, ddof=1, constant -> 0).
    - REC is the kilometric record in SECONDS. REC <= 0 or REC > 100 is
      treated as missing (the DB stores 0 for "no record"; 13 rows hold
      garbage > 100).
    - FORME is the musique-derived score (bayesian_performance_score, 0-12
      scale). When the input frame lacks FORME it is derived from MUSIQUE.
    - Missing COTE stays NaN through the z-score and becomes 0 (field mean).
  * NUMERO (starting post), DIST (meters) and ALLOC are RAW numerics.
    DIST and ALLOC are race-level, i.e. constant within a race, so their
    absolute levels carry no within-race ranking signal but are kept raw.
  * CATEGORICALS (CatBoost native; one-hot for the deep model):
    SEXE, DEF, DSCP, AUTO, DEPART, Q_PLUS, GROUPE, COURSE, DISCIPLINE,
    HIPPODROME.
    - DISCIPLINE and COURSE are derived from CLASS
      ("Attelé. - Course F" -> "att" + "F"); the test uses ASCII prefixes
      so the encoding mojibake in TROT ("AttelÃ©") does not matter.
    - DEF is uppercased ("Pa Dp" -> "PA DP") to merge case variants.
    - Unknown category levels at serve time one-hot to all-zero blocks.
"""

import os
import re
import sqlite3

import pandas as pd

try:
    from model_functions import bayesian_performance_score
except Exception:

    def bayesian_performance_score(music_str, global_avg=5.0, k=3):
        try:
            cleaned = re.sub(r"[\(\[].*?[\)\]]", "", music_str)
            tokens = cleaned.strip().split()

            performances = []
            for token in tokens:
                if token == "NP":
                    continue
                if len(token) != 2:
                    continue
                outcome = token[0]
                if outcome == "D":
                    performances.append(6)
                elif outcome.isdigit():
                    performances.append(10 if outcome == "0" else int(outcome))

            n = len(performances)
            if n == 0:
                return global_avg

            return round((global_avg * k + sum(performances)) / (k + n), 2)
        except Exception:
            return global_avg

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TROT_DB_PATH = os.path.join(_SCRIPT_DIR, "TROT_RACING.db")
DEFAULT_MODELS_DIR = os.path.join(_SCRIPT_DIR, "models")

# DB/scrape column aliases -> canonical names (applied before anything else)
COLUMN_ALIASES = {
    "N°": "NUMERO",
    "N": "NUMERO",
    "REC.": "REC",
    "RECORD": "REC",
    "DIST.": "DIST",
    "DISTANCE": "DIST",
    "DEF.": "DEF",
    "ALLOCATION": "ALLOC",
    "SA": "S/A",
    "Q+": "Q_PLUS",
    "Q+ ": "Q_PLUS",
}

PER_RACE_Z_FEATURES = ["COTE", "REC", "FORME", "GAIN", "AGE"]
RAW_FEATURES = ["NUMERO", "DIST", "ALLOC"]
CATEGORICAL_FEATURES = [
    "SEXE", "DEF", "DSCP", "AUTO", "DEPART", "Q_PLUS",
    "GROUPE", "COURSE", "DISCIPLINE", "HIPPODROME",
]
FEATURE_COLUMNS = PER_RACE_Z_FEATURES + RAW_FEATURES + CATEGORICAL_FEATURES

# fixed one-hot levels for the deep model (unknown level -> all-zero block)
CATEGORY_LEVELS = {
    "SEXE": ["0", "1", "2"],
    "DEF": ["0", "D4", "DP", "DA", "PA DP", "PA", "P4", "PP"],
    "DSCP": ["0", "1"],
    "AUTO": ["0", "1"],
    "DEPART": ["0", "1"],
    "Q_PLUS": ["0", "1"],
    "GROUPE": ["NONE", "GRP 1", "GRP 2", "GRP 3"],
    "COURSE": ["NONE", "A", "B", "C", "D", "E", "F", "G", "EUROP"],
    "DISCIPLINE": ["att", "mont", "other"],
    "HIPPODROME": [
        "AMIENS", "AMIENS GRAND", "ARGENTAN", "BEAUMONT DE LOMAGNE",
        "BEAUMONT DE LOMAGNE GRAND", "CABOURG", "CABOURG GRAND", "CAEN",
        "CHARTRES", "CHARTRES GRAND", "CHOLET", "CHOLET GRAND",
        "ENGHIEN SOISY", "ENGHIEN SOISY LA COURSE DES BLEUS", "GRAIGNES",
        "GRAIGNES GRAND", "HYERES", "HYERES GRAND", "LA CAPELLE",
        "LA CAPELLE GRAND", "LAVAL", "LAVAL GRAND", "LE CROISE LAROCHE",
        "LE CROISE LAROCHE 1ER", "LE CROISE LAROCHE 2EME",
        "LE CROISE LAROCHE GRAND", "LE MANS", "LE MANS GRAND",
        "MARSEILLE BORELY", "MARSEILLE BORELY GRAND", "NANTES",
        "NANTES GRAND", "PARIS VINCENNES", "PARIS VINCENNES GRAND",
        "PARIS VINCENNES PX DES PART OFF DU GD",
        "PARIS VINCENNES PX LE SOUVENIR FRANCAIS", "REIMS", "REIMS GD",
        "REIMS GRAND", "SALON DE PROVENCE", "SALON DE PROVENCE GRAND",
        "STRASBOURG", "STRASBOURG GRAND", "VICHY", "VIRE",
    ],
}

DEEP_ONEHOT_COLUMNS = [
    f"{col}={level}"
    for col, levels in CATEGORY_LEVELS.items()
    for level in levels
]
DEEP_FEATURE_COLUMNS = PER_RACE_Z_FEATURES + RAW_FEATURES + DEEP_ONEHOT_COLUMNS

# rank multiclass target: min(RANG, RANK_CLIP); RANG max is 12 in TROT
RANK_CLIP = 12
PLACE_RANK = 3
DARK_HORSE_MIN_ODDS = 20.0


def canonicalize_columns(df):
    """Strip column names and apply the alias map (NUMERO, REC, DIST, ...).

    Live scrapes can carry both the native and the aliased spelling of the
    same column (e.g. DIST and DIST. in the turfomania partants table), so
    duplicate names are dropped keeping the first occurrence.
    """
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    rename = {c: COLUMN_ALIASES[c] for c in df.columns if c in COLUMN_ALIASES}
    df = df.rename(columns=rename)
    return df.loc[:, ~df.columns.duplicated()]


def _coerce_numerics(df):
    """Coerce the numeric features and mask invalid values BEFORE z-scoring.

    REC <= 0 or > 100 becomes NaN so it cannot pollute the field mean/std,
    and a missing FORME is derived from MUSIQUE with the shared
    bayesian_performance_score (same scorer the flat pipeline uses).
    """
    out = df.copy()
    for col in PER_RACE_Z_FEATURES + RAW_FEATURES:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
        else:
            out[col] = float("nan")

    rec = out["REC"]
    out.loc[rec <= 0, "REC"] = float("nan")
    out.loc[rec > 100, "REC"] = float("nan")

    if out["FORME"].isna().any() and "MUSIQUE" in out.columns:
        mask = out["FORME"].isna()
        out.loc[mask, "FORME"] = out.loc[mask, "MUSIQUE"].map(
            lambda m: bayesian_performance_score(m) if isinstance(m, str) and m.strip() else float("nan")
        )
    return out


def _derive_categories(df):
    """Build the categorical columns (DISCIPLINE/COURSE from CLASS, etc.)."""
    out = df.copy()
    cls = out.get("CLASS")
    if cls is None:
        cls = pd.Series("", index=out.index)
    cls = cls.astype(str)

    discipline = pd.Series("other", index=out.index)
    discipline[cls.str.contains("Attel", case=False)] = "att"
    discipline[cls.str.contains("Mont", case=False)] = "mont"
    out["DISCIPLINE"] = discipline

    course = cls.str.extract(r"Course\s+([A-Ga-g])", expand=False)
    course = course.str.upper()
    course[cls.str.contains("Europ", case=False)] = "EUROP"
    out["COURSE"] = course.fillna("NONE")

    if "GROUPE" in out.columns:
        out["GROUPE"] = out["GROUPE"].fillna("NONE").astype(str).str.strip()
        out.loc[out["GROUPE"] == "", "GROUPE"] = "NONE"
    else:
        out["GROUPE"] = "NONE"

    for col in ("SEXE", "DSCP", "AUTO", "DEPART", "Q_PLUS"):
        if col in out.columns:
            out[col] = out[col].astype(str).str.strip()
        else:
            out[col] = "0"
    if "DEF" in out.columns:
        out["DEF"] = out["DEF"].fillna("0").astype(str).str.strip().str.upper()
        out.loc[out["DEF"] == "", "DEF"] = "0"
    else:
        out["DEF"] = "0"
    if "HIPPODROME" in out.columns:
        out["HIPPODROME"] = out["HIPPODROME"].astype(str).str.strip().str.upper()
    else:
        out["HIPPODROME"] = "UNKNOWN"
    return out


def _zscore(s):
    std = s.std()
    if pd.isna(std) or std == 0:
        return pd.Series(0.0, index=s.index)
    return (s - s.mean()) / std


def zscore_within_race(df, group_col="ID_COURSE", features=None):
    """Z-score the per-race features inside each race (ddof=1, constant -> 0).

    Works on a full training frame or on a single new race: the transform
    only ever looks at the rows it is given.
    """
    features = PER_RACE_Z_FEATURES if features is None else features
    out = df.copy()
    if group_col in out.columns:
        grouper = out.groupby(group_col)
    else:
        grouper = out.groupby(pd.Series(0, index=out.index))
    for col in features:
        if col in out.columns:
            out[col] = grouper[col].transform(_zscore)
    return out


def prepare_frame(df):
    """Canonicalize -> coerce -> per-race z-score -> categories -> fill NaN 0.

    The one entry point shared by training and serving.
    """
    out = _coerce_numerics(canonicalize_columns(df))
    out = zscore_within_race(out)
    out = _derive_categories(out)
    out[PER_RACE_Z_FEATURES + RAW_FEATURES] = out[
        PER_RACE_Z_FEATURES + RAW_FEATURES
    ].fillna(0.0)
    return out


def build_deep_matrix(df):
    """One-hot the categoricals on the fixed level lists -> numeric matrix."""
    out = df.copy()
    for col, levels in CATEGORY_LEVELS.items():
        values = out[col].astype(str) if col in out.columns else pd.Series("", index=out.index)
        for level in levels:
            out[f"{col}={level}"] = (values == level).astype(float)
    return out


def load_training_data(db_path=TROT_DB_PATH):
    """Load the TROT table, prepare features and add the target columns.

    DARK_HORSE is defined on RAW odds (COTE >= DARK_HORSE_MIN_ODDS), so it
    is computed before prepare_frame z-scores the odds column.
    """
    con = sqlite3.connect(db_path)
    df = pd.read_sql("SELECT * FROM TROT", con)
    con.close()
    rang = pd.to_numeric(df["RANG"], errors="coerce")
    cote_raw = pd.to_numeric(df["COTE"], errors="coerce")
    df = prepare_frame(df)
    df["RANG"] = rang
    df["PLACE"] = (rang <= PLACE_RANK).astype(float)
    df["DARK_HORSE"] = (
        (rang == 1) & (cote_raw >= DARK_HORSE_MIN_ODDS)
    ).astype(float)
    df = df.dropna(subset=["RANG", "COTE"])
    return df


if __name__ == "__main__":
    import numpy as np

    data = load_training_data()
    print(f"rows {len(data)} / races {data['ID_COURSE'].nunique()}")
    print(f"place rate {data['PLACE'].mean():.4f} | dark-horse rate {data['DARK_HORSE'].mean():.4f} | "
          f"dark rate on RANG<=6 {data.loc[data['RANG'] <= 6, 'DARK_HORSE'].mean():.4f}")
    deep = build_deep_matrix(data)
    missing = [c for c in DEEP_FEATURE_COLUMNS if c not in deep.columns]
    print(f"deep matrix {deep[DEEP_FEATURE_COLUMNS].shape}, missing columns: {missing}")

    race_id = int(data["ID_COURSE"].iloc[0])
    con = sqlite3.connect(TROT_DB_PATH)
    raw_race = pd.read_sql("SELECT * FROM TROT WHERE ID_COURSE = ?", con, params=(race_id,))
    con.close()
    lone = prepare_frame(raw_race)
    ref = data[data["ID_COURSE"] == race_id]
    same = all(
        np.allclose(ref[c].values, lone.loc[ref.index, c].values)
        for c in PER_RACE_Z_FEATURES
    )
    print(f"single-race z-score invariance (race {race_id}, {len(raw_race)} raw rows): {same}")
