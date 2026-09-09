from app.services.meeting_persistence import _normalize_integer_columns


def test_normalize_grouped_meter_distance() -> None:
    payload = _normalize_integer_columns({"DIST.": "3\u00a0100m", "DIST": "2 700m"})

    assert payload["DIST."] == 3100
    assert payload["DIST"] == 2700