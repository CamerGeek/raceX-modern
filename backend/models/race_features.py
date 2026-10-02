"""Shared feature contract for the French flat-racing models.

Single source of truth for how model input features are built. Imported by
both the training scripts (train_catboost.py, train_deep_learning.py) and
the serving module (predict.py) so the transformation applied at prediction
time is exactly the one the models were trained on.

Verified data contract of plat.csv (166,401 rows / 16,280 races):
  * COTE, POIDS, GAIN, IC, FORME, S_COEFF, AGE are z-scored WITHIN each race
    (groupby ID_COURSE). Races where a column is constant were mapped to 0.
    => z-scoring those columns inside a single new race reproduces the
       training transform without needing any saved statistics.
  * N_WEIGHT is the RAW weight evolution in kg (approx. -19 .. +19).
  * NUMERO (the "N deg" horse-number column), CORDE, SEXE, HIPPOID are RAW.
  * The 0/1 indicator columns (OEILL.*, GRP.*, ...) are RAW flags.
  * DIST and NUM_STARTERS are global z-scores whose original statistics are
    lost; both are constant within a race anyway (no within-race ranking
    signal). They are DROPPED to avoid train/serve skew - the original
    notebook min-maxed them at prediction time with training-set statistics,
    silently corrupting those features.
"""

import os

import pandas as pd

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_PATH = os.path.join(_SCRIPT_DIR, "plat.csv")
DEFAULT_MODELS_DIR = os.path.join(_SCRIPT_DIR, "models")

HIPPODROME_MAPPING = {
    "AUTEUIL": 1, "COMPIEGNE": 2, "CLAIREFONTAINE": 3, "CHANTILLY": 4,
    "DEAUVILLE": 5, "PAU": 6, "SAINT CLOUD": 7, "LONGCHAMP": 8,
    "FONTAINEBLEAU": 9, "TOULOUSE": 10, "CAGNES SUR MER": 11,
    "LYON LA SOIE": 12, "VICHY": 13, "STRASBOURG": 14, "DIEPPE": 15,
    "BORDEAUX LE BOUSCAT": 16, "MARSEILLE BORELY": 17, "MAISONS LAFFITTE": 18,
    "LE LION D ANGERS": 19, "LA TESTE DE BUCH": 20, "NANTES": 21,
    "MARSEILLE VIVAUX": 22,
}

# z-scored within each race (both in plat.csv and, identically, at predict time)
PER_RACE_Z_FEATURES = ["COTE", "POIDS", "GAIN", "IC", "FORME", "S_COEFF", "AGE"]

# raw values, used exactly as found
RAW_FEATURES = ["NUMERO", "CORDE", "SEXE", "HIPPOID", "N_WEIGHT"]

# raw 0/1 flags (same selection as the original notebook's FEATURE_COLUMNS)
BINARY_FEATURES = [
    "OEILL.|0", "OEILL.|1", "OEILL.|2",
    "GRP|1", "GRP|2", "GRP|3",
    "Q+|0", "Q+|1",
    "LICE|0", "LICE|1", "LICE|2",
    "CLASSE|1", "CLASSE|2", "CLASSE|3", "CLASSE|4",
    "HANDICAP|0", "HANDICAP|1",
    "LISTED|0", "LISTED|1",
]

FEATURE_COLUMNS = PER_RACE_Z_FEATURES + RAW_FEATURES + BINARY_FEATURES

# rank multiclass target: min(RANG, RANK_CLIP); classes 1..RANK_CLIP
RANK_CLIP = 8


def find_num_col(columns):
    """Find the horse-number column across its encoding variants.

    plat.csv and the scraped CSVs store it as "N" + U+00B0 (the cp1252
    mojibake of "N deg"), sometimes as plain "N" or already as "NUMERO".
    """
    for c in columns:
        cs = str(c).strip()
        if cs == "NUMERO":
            return c
        if cs == "N" or (cs.startswith("N") and len(cs) == 2 and not cs[1].isascii()):
            return c
    return None


def canonicalize_columns(df):
    """Strip column names and rename the horse-number column to NUMERO."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    ncol = find_num_col(df.columns)
    if ncol is not None and ncol != "NUMERO":
        df = df.rename(columns={ncol: "NUMERO"})
    return df


def _zscore(s):
    std = s.std()
    if pd.isna(std) or std == 0:
        return pd.Series(0.0, index=s.index)
    return (s - s.mean()) / std


def zscore_within_race(df, group_col="ID_COURSE", features=None):
    """Z-score the per-race features inside each race (ddof=1, constant -> 0).

    This exactly reproduces the normalization already present in plat.csv,
    so calling it on a single new race yields values on the training scale.
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


def load_training_data(path=DEFAULT_DATA_PATH):
    """Load plat.csv with canonicalized columns and numeric features.

    plat.csv already contains the per-race z-scores, so no normalization is
    (re)applied here. Rows with missing COTE/IC are dropped, mirroring the
    original notebook (cell 5).
    """
    df = pd.read_csv(path, low_memory=False)
    df = canonicalize_columns(df)
    for col in FEATURE_COLUMNS:
        if col not in df.columns:
            df[col] = 0
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["RANG"] = pd.to_numeric(df["RANG"], errors="coerce")
    df["DARK_HORSE"] = pd.to_numeric(df["DARK_HORSE"], errors="coerce")
    df = df.dropna(subset=["COTE", "IC", "RANG", "DARK_HORSE"])
    df[FEATURE_COLUMNS] = df[FEATURE_COLUMNS].fillna(0)
    return df
