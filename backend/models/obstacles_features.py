"""Shared feature contract for the French obstacle-race models (steeple / haies).

Single source of truth for how model input features are built, mirroring
trot_features.py. Imported by the training scripts (train_obstacles_catboost.py,
train_obstacles_deep_learning.py) and the serving module (predict_obstacles.py)
so the transform applied at prediction time is exactly the one the models were
trained on.

Training data: processed_data.csv (43,919 rows / 5,839 races, 2013-12 .. 2025-06,
14 hippodromes), produced from new_obstacles2025.ipynb. IMPORTANT: unlike the trot
DB, the CSV stores the notebook's GLOBALLY z-scored values for the z-block. The
contract re-applies the per-race z-score on load: per-race z-scoring is invariant
to any prior affine (global OR race-level) transform of the same quantity, so
re-scoring the stored global-z columns yields exactly the per-race z of the raw
scrape values - which is what prepare_race produces from a live race at serve
time. The notebook's own predict path (global z in training, ad-hoc race z on the
new race) was skewed; this contract fixes that.

Contract:
  * COTE, POIDS, GAIN, PAST_POIDS, AGE, IC, FS, FH, FC, FT, N_WEIGHT are
    z-scored WITHIN each race (groupby ID_COURSE, ddof=1, constant -> 0).
    - IC is the notebook's weight-minus-odds index; FS/FH/FC/FT are musique
      weighted per-discipline form scores (s/c/h/global); N_WEIGHT the weight
      evolution. All are musique/INDICS-derived at scrape time.
  * RAW numerics (no z): NUMERO (starting number), DISTANCE (m, race-level),
    STARTERS (field size, race-level), S_COEFF (success coefficient),
    INCIDENT_COUNT, LAST_RACE_INCIDENT, HAS_FALLEN, HAS_STOPPED (musique-derived
    fall/stop history).
  * CATEGORICALS (CatBoost native; one-hot for the deep model): SEXE, HIPPOID.
  * BINARY indicators (0/1, as in the notebook): OEILL.|0-2, GRP|1-3, DSCP|2-4,
    Q+|0-1, LICE|1-2, CLASSE|1-4, HANDICAP|0-1.
  * FORME is constant-zero in the training CSV and is dropped.
  * DARK_HORSE is PRECOMPUTED in the CSV (long-odds winner flag, notebook
    convention on the z-odds scale); it cannot be recomputed at serve time and
    is used as-is, like the flat pipeline does.
"""

import os
import re

import pandas as pd

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_PATH = os.path.join(_SCRIPT_DIR, "processed_data.csv")
DEFAULT_MODELS_DIR = os.path.join(_SCRIPT_DIR, "models")

# scrape column aliases -> canonical names (applied before anything else)
COLUMN_ALIASES = {
    "N°": "NUMERO",
    "N": "NUMERO",
    "DIST.": "DISTANCE",
    "DIST": "DISTANCE",
    "SA": "S/A",
    "HIPPO": "HIPPODROME",
    "TRACK": "HIPPODROME",
    "MUSIQUE": "HORSE_MUSIC",
    "MUSIC": "HORSE_MUSIC",
}

PER_RACE_Z_FEATURES = [
    "COTE", "POIDS", "GAIN", "PAST_POIDS", "AGE", "IC",
    "FS", "FH", "FC", "FT", "N_WEIGHT",
]
RAW_FEATURES = [
    "NUMERO", "DISTANCE", "STARTERS", "S_COEFF",
    "INCIDENT_COUNT", "LAST_RACE_INCIDENT", "HAS_FALLEN", "HAS_STOPPED",
]
CATEGORICAL_FEATURES = ["SEXE", "HIPPOID"]
BINARY_FEATURES = [
    "OEILL.|0", "OEILL.|1", "OEILL.|2",
    "GRP|1", "GRP|2", "GRP|3",
    "DSCP|2", "DSCP|3", "DSCP|4",
    "Q+|0", "Q+|1",
    "LICE|1", "LICE|2",
    "CLASSE|1", "CLASSE|2", "CLASSE|3", "CLASSE|4",
    "HANDICAP|0", "HANDICAP|1",
]
FEATURE_COLUMNS = (
    PER_RACE_Z_FEATURES + RAW_FEATURES + CATEGORICAL_FEATURES + BINARY_FEATURES
)

# fixed one-hot levels for the deep model (unknown level -> all-zero block)
CATEGORY_LEVELS = {
    "SEXE": ["0", "1", "2"],
    "HIPPOID": [
        "1", "10", "11", "13", "14", "15", "16", "19", "2", "20", "21", "3",
        "6", "9",
    ],
}

DEEP_ONEHOT_COLUMNS = [
    f"{col}={level}"
    for col, levels in CATEGORY_LEVELS.items()
    for level in levels
]
DEEP_FEATURE_COLUMNS = PER_RACE_Z_FEATURES + RAW_FEATURES + DEEP_ONEHOT_COLUMNS

# rank multiclass target: min(RANG, RANK_CLIP); RANG max is 18 but >10 is 2.7%
RANK_CLIP = 10
PLACE_RANK = 3

# hippodrome name -> HIPPOID code (from the reference notebook; the training
# CSV carries codes 1-21 subset, live races can be at any of these tracks)
HIPPODROME_TO_ID = {
    "AUTEUIL": "1", "COMPIEGNE": "2", "CLAIREFONTAINE": "3",
    "CHANTILLY": "4", "DEAUVILLE": "5", "PAU": "6",
    "SAINT CLOUD": "7", "LONGCHAMP": "8", "FONTAINEBLEAU": "9",
    "TOULOUSE": "10", "CAGNES SUR MER": "11", "LYON LA SOIE": "12",
    "VICHY": "13", "STRASBOURG": "14", "DIEPPE": "15",
    "BORDEAUX LE BOUSCAT": "16", "MARSEILLE BORELY": "17",
    "MAISONS LAFFITTE": "18", "LE LION D ANGERS": "19",
    "LA TESTE DE BUCH": "20", "NANTES": "21",
}


def clean_sex(s):
    """H/M/F -> 0/1/2 (training codes); numeric codes pass through."""
    if s == "H":
        return "0"
    if s == "M":
        return "1"
    if s == "F":
        return "2"
    return str(s)


def canonicalize_columns(df):
    """Strip column names and apply the alias map (NUMERO, DISTANCE, ...)."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    rename = {c: COLUMN_ALIASES[c] for c in df.columns if c in COLUMN_ALIASES}
    df = df.rename(columns=rename)
    return df.loc[:, ~df.columns.duplicated()]


def _coerce_numerics(df):
    """Coerce the numeric feature blocks; missing columns become NaN."""
    out = df.copy()
    for col in PER_RACE_Z_FEATURES + RAW_FEATURES:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
        else:
            out[col] = float("nan")
    return out


def _derive_categories(df):
    """Build SEXE / HIPPOID categoricals and fill the binary indicators."""
    out = df.copy()

    # SEXE: accept letter codes (H/M/F), S/A first char, or numeric 0/1/2
    sexe = out["SEXE"] if "SEXE" in out.columns else None
    if "S/A" in out.columns:
        sa = out["S/A"].astype(str).str.strip()
        from_sa = sa.str[0].map(clean_sex)
        if sexe is None:
            sexe = from_sa
        else:
            raw = sexe.astype(str).str.strip()
            numeric = pd.to_numeric(sexe, errors="coerce")
            sexe = raw.map(clean_sex)
            sexe = sexe.where(numeric.isna(), numeric.astype("Int64").astype(str))
            missing = raw.str.upper().isin(("", "NAN", "NONE", "0")) & from_sa.notna()
            sexe = sexe.where(~missing, from_sa)
    if sexe is None:
        sexe = pd.Series("0", index=out.index)
    out["SEXE"] = sexe.fillna("0").astype(str).str.strip()

    # HIPPOID: numeric code as string; fall back to the hippodrome name map
    if "HIPPOID" in out.columns:
        h = pd.to_numeric(out["HIPPOID"], errors="coerce")
        hid = h.astype("Int64").astype(str)
        bad = hid.isin(["<NA>", "nan", "0"])
        if "HIPPODROME" in out.columns:
            from_name = (out["HIPPODROME"].astype(str).str.strip().str.upper()
                         .map(HIPPODROME_TO_ID))
            hid = hid.where(~bad, from_name)
        out["HIPPOID"] = hid.fillna("0")
    elif "HIPPODROME" in out.columns:
        out["HIPPOID"] = (out["HIPPODROME"].astype(str).str.strip().str.upper()
                          .map(HIPPODROME_TO_ID).fillna("0"))
    else:
        out["HIPPOID"] = "0"
    out["HIPPOID"] = out["HIPPOID"].astype(str).str.strip()

    for col in BINARY_FEATURES:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0)
        else:
            out[col] = 0
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


# --------------------------------------------------------------------- #
# musique-derived features (ported from new_obstacles2025.ipynb so a live  #
# scrape carrying HORSE_MUSIC can rebuild the training columns)           #
# --------------------------------------------------------------------- #

def compute_d_perf(horse_music):
    """Weighted per-discipline musique scores {'h','s','c','global'}.

    Tokens like "5h 10s Dc": digit = finish (D/A/T/NP/0 -> penalty 10),
    last letter = discipline (h=haies, s=steeple, c=cross). Most recent
    performance weighs most.
    """
    default = {"h": 0, "s": 0, "c": 0, "global": 0}
    if not isinstance(horse_music, str) or not horse_music.strip():
        return default
    try:
        cleaned = re.sub(r"[\[\(].*?[\]\)]", "", horse_music).strip()
        tokens = []
        for token in cleaned.split():
            if len(token) >= 2:
                tokens.append((token[:-1], token[-1].lower()))
        penalties = {"D": 10, "A": 10, "T": 10, "NP": 10, "0": 10}
        by_disc = {"h": [], "s": [], "c": []}
        for score_part, disc in tokens:
            if disc not in by_disc:
                continue
            if score_part in penalties:
                score = penalties[score_part]
            elif score_part.isdigit():
                score = int(score_part)
            else:
                continue
            by_disc[disc].append(score)

        def weighted_avg(scores):
            if not scores:
                return None
            weights = range(len(scores), 0, -1)
            return round(sum(s * w for s, w in zip(scores, weights))
                         / sum(weights), 2)

        out = {d: weighted_avg(sc) or 0 for d, sc in by_disc.items()}
        all_scores, all_weights = [], []
        for scores in by_disc.values():
            if scores:
                all_scores.extend(scores)
                all_weights.extend(range(len(scores), 0, -1))
        out["global"] = (round(sum(s * w for s, w in zip(all_scores, all_weights))
                               / sum(all_weights), 2) if all_scores else 0)
        return out
    except Exception:
        return default


def success_coefficient(horse_music, discipline):
    """Notebook success coefficient for one discipline letter (0-10-ish)."""
    try:
        max_score = 10
        cleaned = re.sub(r"[\(\[].*?[\)\]]", "", horse_music).strip()
        tokens = [t for t in cleaned.split() if len(t) >= 2]
        filtered = []
        for token in tokens:
            rank_str, disc = token[:-1], token[-1].lower()
            if disc == str(discipline).lower():
                if rank_str.upper() in ("D", "A", "T", "NP") or rank_str == "0":
                    score = max_score
                elif rank_str.isdigit():
                    score = int(rank_str)
                else:
                    continue
                filtered.append(score)
        last_ranks = filtered[:5]
        n = len(last_ranks)
        if n == 0:
            return 0.0
        weights = [5, 4, 3, 2, 1][:n]
        return round(sum(w * (11 - p) for w, p in zip(weights, last_ranks))
                     / sum(weights), 2)
    except Exception:
        return 0.0


def extract_incident_features(df):
    """HAS_FALLEN / HAS_STOPPED / INCIDENT_COUNT / LAST_RACE_INCIDENT from
    HORSE_MUSIC (first token = current race, second = previous race)."""
    out = df.copy()
    music = out["HORSE_MUSIC"].fillna("").astype(str).str.strip()

    def first(x):
        return x.split()[0].upper() if len(x) > 0 else ""

    out["HAS_FALLEN"] = music.map(lambda x: int("T" in first(x)))
    out["HAS_STOPPED"] = music.map(lambda x: int("A" in first(x)))
    out["INCIDENT_COUNT"] = music.map(
        lambda x: first(x).count("T") + first(x).count("A") if len(x) > 0 else 0
    )

    def last_race_incident(x):
        parts = x.split()
        return int(len(parts) > 1 and ("T" in parts[0].upper() or "A" in parts[1].upper()))

    out["LAST_RACE_INCIDENT"] = music.map(last_race_incident)
    return out


def load_training_data(path=DEFAULT_DATA_PATH, sample=None, seed=42):
    """Load processed_data.csv, prepare features and add the target columns.

    Rows without COTE/IC/RANG are dropped (mirrors the flat loader). DARK_HORSE
    is precomputed in the CSV and used as-is.
    """
    df = pd.read_csv(path, low_memory=False)
    df = df.drop(columns=[c for c in df.columns if str(c).startswith("Unnamed")])
    df = canonicalize_columns(df)
    rang = pd.to_numeric(df["RANG"], errors="coerce")
    df["PLACE"] = (rang <= PLACE_RANK).astype(float)
    df["RANG"] = rang
    df["DARK_HORSE"] = pd.to_numeric(df["DARK_HORSE"], errors="coerce")
    df = df.dropna(subset=["RANG", "COTE", "IC", "DARK_HORSE"])
    if sample:
        ids = df["ID_COURSE"].drop_duplicates().sample(sample, random_state=seed)
        df = df[df["ID_COURSE"].isin(ids)]
    df = prepare_frame(df)
    return df


if __name__ == "__main__":
    import numpy as np

    data = load_training_data()
    print(f"rows {len(data)} / races {data['ID_COURSE'].nunique()}")
    print(f"place rate {data['PLACE'].mean():.4f} | dark-horse rate "
          f"{data['DARK_HORSE'].mean():.4f} | dark rate on RANG<=6 "
          f"{data.loc[data['RANG'] <= 6, 'DARK_HORSE'].mean():.4f}")
    deep = build_deep_matrix(data)
    missing = [c for c in DEEP_FEATURE_COLUMNS if c not in deep.columns]
    print(f"deep matrix {deep[DEEP_FEATURE_COLUMNS].shape}, missing columns: {missing}")

    race_id = int(data["ID_COURSE"].iloc[0])
    raw_race = pd.read_csv(DEFAULT_DATA_PATH, low_memory=False)
    raw_race = raw_race[raw_race["ID_COURSE"] == race_id].drop(
        columns=[c for c in raw_race.columns if str(c).startswith("Unnamed")]
    )
    lone = prepare_frame(raw_race)
    ref = data[data["ID_COURSE"] == race_id]
    same = all(
        np.allclose(ref[c].values, lone.loc[ref.index, c].values)
        for c in PER_RACE_Z_FEATURES
    )
    print(f"single-race z-score invariance (race {race_id}, "
          f"{len(raw_race)} raw rows): {same}")
