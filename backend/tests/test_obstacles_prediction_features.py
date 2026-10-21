import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

MODELS_PATH = Path(__file__).resolve().parents[1] / "models"
if str(MODELS_PATH) not in sys.path:
    sys.path.insert(0, str(MODELS_PATH))

from obstacles_features import FEATURE_COLUMNS
from obstacles_features import extract_incident_features
from predict_obstacles import ObstaclesPredictor


@pytest.mark.parametrize(
    ("description", "expected_discipline", "expected_form"),
    [
        ("Prix des Haies", "h", 2),
        ("Prix de Steeple", "s", 4),
        ("Prix de Cross", "c", 1),
    ],
)
def test_prepare_race_exposes_form_for_race_discipline(
    description: str,
    expected_discipline: str,
    expected_form: int,
) -> None:
    predictor = ObstaclesPredictor.__new__(ObstaclesPredictor)
    predictor.feature_columns = FEATURE_COLUMNS
    race = pd.DataFrame([{
        "N°": 4,
        "CHEVAL": "Runner",
        "DESCRIPTIF": description,
        "MUSIQUE": "2h 4s 1c",
    }])

    prepared, _, _, _ = predictor.prepare_race(race)

    assert prepared.loc[0, "DISCIPLINE"] == expected_discipline
    assert prepared.loc[0, "FORM_DISCIPLINE"] == expected_form
    assert prepared.loc[0, "MUSIC_AVAILABLE"] == 1


def test_prepare_race_exposes_recent_obstacle_incidents() -> None:
    predictor = ObstaclesPredictor.__new__(ObstaclesPredictor)
    predictor.feature_columns = FEATURE_COLUMNS
    race = pd.DataFrame([{
        "N°": 4,
        "CHEVAL": "Runner",
        "DESCRIPTIF": "Prix des Haies",
        "MUSIQUE": "Th Ah 4h",
    }])

    prepared, _, _, _ = predictor.prepare_race(race)

    assert prepared.loc[0, "HAS_FALLEN"] == 1
    assert prepared.loc[0, "HAS_STOPPED"] == 0
    assert prepared.loc[0, "INCIDENT_COUNT"] == 1


def test_extract_incident_features_counts_falls_and_stops_across_music() -> None:
    music = pd.DataFrame({
        "HORSE_MUSIC": [
            "Ah Th 4h Ah",
            "2h 3s",
            "T A",
            "3hT 2hA 1s 4cT",
            "2h/T 1s-A",
            "(22j) 1s 4s Ah Ah (25) 6h Ts 4s 2s 6s 1h 2s (24) 5h",
        ],
    })

    incidents = extract_incident_features(music)

    assert incidents["STOP_COUNT"].tolist() == [2, 0, 1, 1, 1, 2]
    assert incidents["FALL_COUNT"].tolist() == [1, 0, 1, 2, 1, 1]


def test_prediction_rows_include_full_music_incident_counts() -> None:
    class Classifier:
        def predict_proba(self, features: pd.DataFrame) -> np.ndarray:
            return np.tile([0.5, 0.5], (len(features), 1))

    predictor = ObstaclesPredictor.__new__(ObstaclesPredictor)
    predictor.feature_columns = FEATURE_COLUMNS
    predictor.place = Classifier()
    predictor.dark = Classifier()
    predictor.rank = Classifier()
    predictor.rank_classes = [1, 2]
    predictor.deep = None
    race = pd.DataFrame([{
        "N°": 4,
        "CHEVAL": "Runner",
        "DESCRIPTIF": "Prix des Haies",
        "MUSIQUE": "3hT 2hA 1s 4cT",
    }])

    result = predictor.predict_race(race)

    assert result["table"].loc[0, "STOP_COUNT"] == 1
    assert result["table"].loc[0, "FALL_COUNT"] == 2
