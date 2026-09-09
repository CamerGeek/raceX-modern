from app.services.meeting_persistence import _normalize_integer_columns, _normalize_trot_row


def test_normalize_grouped_meter_distance() -> None:
    payload = _normalize_integer_columns({"DIST.": "3\u00a0100m", "DIST": "2 700m"})

    assert payload["DIST."] == 3100
    assert payload["DIST"] == 2700


def test_normalize_trot_music_from_performance_column() -> None:
    row = _normalize_trot_row({"MUSIQUE": None, "SEXE": None, "SEX": "H", "DERNIÈRES PERF.": "1a 2a 3a"})

    assert row["SEXE"] == "H"
    assert row["MUSIQUE"] == "1a 2a 3a"


def test_normalize_trot_record_time() -> None:
    row = _normalize_trot_row({"REC.": '1\'12"1'})

    assert row["REC."] == 72