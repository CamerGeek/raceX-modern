from functools import lru_cache
import logging
from pathlib import Path
import sys
from typing import Any

import pandas as pd

from app.services.serialization import dataframe_records


logger = logging.getLogger(__name__)
MODELS_DIR = Path(__file__).resolve().parents[2] / "models"


@lru_cache(maxsize=1)
def _get_predictor() -> Any:
    models_path = str(MODELS_DIR)
    if models_path not in sys.path:
        sys.path.insert(0, models_path)

    from predict import RacePredictor

    return RacePredictor(models_dir=models_path)


@lru_cache(maxsize=1)
def _get_trot_predictor() -> Any:
    models_path = str(MODELS_DIR)
    if models_path not in sys.path:
        sys.path.insert(0, models_path)

    from predict_trot import TrotPredictor

    return TrotPredictor(models_dir=models_path)


def predict_race(frame: pd.DataFrame, race_type: str, source: str) -> dict[str, Any]:
    if race_type == "trot":
        return _trot_predictions(frame)
    if race_type != "flat":
        return {
            "status": "unsupported",
            "model_version": None,
            "bet_list": [],
            "rows": [],
            "message": "The available prediction models support flat and trot races only.",
        }

    try:
        predictor = _get_predictor()
        result = predictor.predict_race(frame, source=source)
        return {
            "status": "ready",
            "model_version": predictor.meta.get("created"),
            "bet_list": result["bet_list"],
            "rows": dataframe_records(result["table"]),
            "message": None,
        }
    except Exception:
        logger.exception("Model prediction failed")
        return {
            "status": "unavailable",
            "model_version": None,
            "bet_list": [],
            "rows": [],
            "message": "Model predictions are unavailable for this race.",
        }


def _trot_predictions(frame: pd.DataFrame) -> dict[str, Any]:
    try:
        predictor = _get_trot_predictor()
        result = predictor.predict_race(frame)
        return {
            "status": "ready",
            "model_version": predictor.meta.get("created"),
            "bet_list": result["bet_list"],
            "rows": dataframe_records(result["table"]),
            "message": None,
        }
    except Exception:
        logger.exception("Trot model prediction failed")
        return {
            "status": "unavailable",
            "model_version": None,
            "bet_list": [],
            "rows": [],
            "message": "Model predictions are unavailable for this race.",
        }