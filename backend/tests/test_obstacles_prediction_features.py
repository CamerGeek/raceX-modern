import sys
from pathlib import Path

import pandas as pd
import pytest

MODELS_PATH = Path(__file__).resolve().parents[1] / "models"
if str(MODELS_PATH) not in sys.path:
    sys.path.insert(0, str(MODELS_PATH))

from obstacles_features import FEATURE_COLUMNS
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
