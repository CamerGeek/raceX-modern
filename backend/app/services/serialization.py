from typing import Any
import math

import pandas as pd


def dataframe_records(frame: pd.DataFrame, limit: int | None = None) -> list[dict[str, Any]]:
    output = frame.head(limit) if limit else frame
    records = output.replace({pd.NA: None}).where(pd.notna(output), None).to_dict(orient="records")
    return [{str(key): _json_value(value) for key, value in record.items()} for record in records]


def _json_value(value: Any) -> Any:
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if value is pd.NaT or value is pd.NA:
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value
