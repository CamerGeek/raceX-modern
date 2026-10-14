import pandas as pd
import pytest
from fastapi import HTTPException

from app.api import races
from app.schemas.races import AnalysisRequest, AnalysisResponse, BettingRequest
from app.services import model_prediction_service, scraping_service


def test_predict_race_returns_model_scores(monkeypatch) -> None:
    class Predictor:
        meta = {"created": "2026-09-29"}

        def predict_race(self, frame, source):
            assert source == "turfomania"
            assert len(frame) == 1
            return {
                "bet_list": [4],
                "table": pd.DataFrame([{"NUMERO": 4, "place_prob": 0.75}]),
            }

    monkeypatch.setattr(model_prediction_service, "_get_predictor", lambda: Predictor())

    result = model_prediction_service.predict_race(pd.DataFrame([{"N°": "4"}]), "flat", "turfomania")

    assert result == {
        "status": "ready",
        "model_version": "2026-09-29",
        "bet_list": [4],
        "rows": [{"NUMERO": 4, "place_prob": 0.75}],
        "message": None,
    }


def test_predict_race_returns_trot_model_scores(monkeypatch) -> None:
    class TrotPredictor:
        meta = {"created": "2026-10-05"}

        def predict_race(self, frame):
            assert len(frame) == 1
            return {
                "bet_list": [7],
                "table": pd.DataFrame([{"NUMERO": 7, "place_prob": 0.66, "place_prob_deep": float("nan")}]),
            }

    monkeypatch.setattr(
        model_prediction_service,
        "_get_predictor",
        lambda: (_ for _ in ()).throw(AssertionError("flat predictor should not load")),
    )
    monkeypatch.setattr(model_prediction_service, "_get_trot_predictor", lambda: TrotPredictor())

    result = model_prediction_service.predict_race(pd.DataFrame([{"N°": "7"}]), "trot", "turfomania")

    assert result == {
        "status": "ready",
        "model_version": "2026-10-05",
        "bet_list": [7],
        "rows": [{"NUMERO": 7, "place_prob": 0.66, "place_prob_deep": None}],
        "message": None,
    }


def test_predict_race_skips_unsupported_race_type(monkeypatch) -> None:
    monkeypatch.setattr(
        model_prediction_service,
        "_get_predictor",
        lambda: (_ for _ in ()).throw(AssertionError("predictor should not load")),
    )
    monkeypatch.setattr(
        model_prediction_service,
        "_get_trot_predictor",
        lambda: (_ for _ in ()).throw(AssertionError("trot predictor should not load")),
    )

    result = model_prediction_service.predict_race(pd.DataFrame(), "unknown", "turfomania")

    assert result["status"] == "unsupported"
    assert result["bet_list"] == []


def test_analyze_includes_model_predictions(monkeypatch) -> None:
    frame = pd.DataFrame([{"N°": "4", "CHEVAL": "Runner"}])
    prediction = {
        "status": "ready",
        "model_version": "2026-09-29",
        "bet_list": [4],
        "rows": [{"NUMERO": 4, "place_prob": 0.75}],
        "message": None,
    }
    monkeypatch.setattr(races, "scrape_race", lambda *_: frame)
    monkeypatch.setattr(races, "analyze_race", lambda source, *_args, **_kwargs: (source, pd.DataFrame(), None))
    monkeypatch.setattr(races, "_prognosis_rows", lambda *_: [])
    monkeypatch.setattr(races, "_legacy_sections", lambda *_: [])
    monkeypatch.setattr(races, "_flat_overview", lambda *_: {})
    monkeypatch.setattr(races, "predict_model_race", lambda *_: prediction)

    result = races.analyze(AnalysisRequest(url="https://example.test/race", race_type="flat", source="turfomania"))

    assert result.model_predictions is not None
    assert result.model_predictions.status == "ready"
    assert result.model_predictions.bet_list == [4]


@pytest.mark.parametrize("force_refresh", [False, True])
def test_saved_race_analysis_uses_cache_unless_admin_forces_refresh(monkeypatch, force_refresh: bool) -> None:
    cache_response = AnalysisResponse(
        race_type="flat",
        source="zone-turf",
        row_count=1,
        columns=["N°", "CHEVAL"],
        rows=[{"N°": "4", "CHEVAL": "Runner"}],
        model_version="cached-model",
        prognosis=[],
    )
    run = {
        "created_at": "2026-10-03T10:00:00+00:00",
        "summary": {
            "racex_cache": {
                "version": races.RACE_ANALYSIS_CACHE_VERSION,
                "kind": "race-analysis",
                "options": {
                    "race_type": "flat",
                    "source": "zone-turf",
                    "include_handicap": True,
                    "max_horses": 8,
                },
                "result": cache_response.model_dump(mode="json"),
            }
        },
    }

    class Client:
        inserted: list[dict] = []

        def select_one(self, table, *, filters, **kwargs):
            if table == "races":
                return {"id": "race-id", "race_type": "flat", "source": "zone-turf"}
            if table == "flat_race_runners":
                return {"updated_at": "2026-10-03T10:00:00+00:00"}
            raise AssertionError(f"unexpected select table: {table}")

        def list(self, table, *, filters, **kwargs):
            if table == "flat_race_runners":
                return [{"raw_data": {"N°": "4", "CHEVAL": "Runner"}}]
            if table == "analysis_runs":
                return [run]
            raise AssertionError(f"unexpected list table: {table}")

        def insert(self, table, payload):
            assert table == "analysis_runs"
            self.inserted.append(payload)
            return payload

    client = Client()
    monkeypatch.setattr(races, "SupabaseClientWrapper", lambda: client)
    compute_calls = 0

    def compute(*_args, **_kwargs):
        nonlocal compute_calls
        compute_calls += 1
        return cache_response.model_copy(update={"model_version": "refreshed-model"})

    monkeypatch.setattr(races, "_analysis_response", compute)
    request = AnalysisRequest(
        url="https://example.test/race",
        race_type="flat",
        source="zone-turf",
        race_id="race-id",
        force_refresh=force_refresh,
    )

    response = races.analyze(request)

    assert compute_calls == int(force_refresh)
    assert len(client.inserted) == int(force_refresh)
    assert response.model_version == ("refreshed-model" if force_refresh else "cached-model")


@pytest.mark.parametrize(("analysis_kind", "force_refresh"), [
    ("simulation", False),
    ("simulation", True),
    ("combinations", False),
    ("combinations", True),
])
def test_betting_analyses_use_cache_unless_admin_forces_refresh(
    monkeypatch,
    analysis_kind: str,
    force_refresh: bool,
) -> None:
    options = (
        {"race_type": "flat", "simulations": 5000}
        if analysis_kind == "simulation"
        else {
            "race_type": "flat",
            "combination_size": 5,
            "max_combinations": 50,
            "mandatory": [],
            "excluded": [],
        }
    )
    cached_result = (
        {"race_id": "race-id", "race_type": "flat", "simulations": 5000, "rows": []}
        if analysis_kind == "simulation"
        else {"race_id": "race-id", "race_type": "flat", "combination_size": 5, "combinations": []}
    )
    analysis_run = {
        "created_at": "2026-10-03T10:00:00+00:00",
        "summary": {
            "racex_cache": {
                "version": races.BETTING_CACHE_VERSION,
                "kind": analysis_kind,
                "options": options,
                "result": cached_result,
            }
        },
    }

    class Client:
        inserted: list[dict] = []

        def select_one(self, table, *, filters, **kwargs):
            if table == "races":
                return {"id": "race-id", "race_type": "flat", "source": "zone-turf"}
            if table == "flat_race_runners":
                return {"updated_at": "2026-10-03T10:00:00+00:00"}
            raise AssertionError(f"unexpected select table: {table}")

        def list(self, table, *, filters, **kwargs):
            if table == "flat_race_runners":
                return [{"raw_data": {"N°": "4", "CHEVAL": "Runner"}}]
            if table == "analysis_runs":
                return [analysis_run]
            raise AssertionError(f"unexpected list table: {table}")

        def insert(self, table, payload):
            assert table == "analysis_runs"
            self.inserted.append(payload)
            return payload

    client = Client()
    monkeypatch.setattr(races, "SupabaseClientWrapper", lambda: client)
    compute_calls = 0

    def compute(*_args, **_kwargs):
        nonlocal compute_calls
        compute_calls += 1
        return [{"fresh": True}]

    monkeypatch.setattr(races, "simulate_race", compute)
    monkeypatch.setattr(races, "generate_combinations", compute)
    request = BettingRequest(race_id="race-id", race_type="flat", force_refresh=force_refresh)
    if analysis_kind == "simulation":
        response = races.simulate(request)
    else:
        response = races.combinations(request)

    assert compute_calls == int(force_refresh)
    assert len(client.inserted) == int(force_refresh)
    assert response == (cached_result if not force_refresh else {
        **cached_result,
        "rows" if analysis_kind == "simulation" else "combinations": [{"fresh": True}],
    })


def test_detect_type_rejects_meeting_level_turfomania_url() -> None:
    with pytest.raises(HTTPException) as error:
        races.detect_type("turfomania://meetings/meeting-1")

    assert error.value.status_code == 422


def test_detect_type_uses_selected_turfomania_race(monkeypatch) -> None:
    monkeypatch.setattr(
        races,
        "detect_turfomania_race_type",
        lambda url: "obstacles",
    )

    result = races.detect_type(
        "https://www.turfomania.fr/pronostics/partants-race.html?idcourse=123"
    )

    assert result == {"race_type": "obstacles"}


def test_detect_turfomania_race_type_reads_race_conditions(monkeypatch) -> None:
    import turfomania_race

    html = """
      <div class="table-head-bloc-title">
        <div class="h2">Prix des Haies (Auteuil)</div>
        <div class="date">Mercredi 14 Octobre 2026 - 14h00</div>
        <div class="detail">Haies - 3600 mètres</div>
      </div>
      <table><tr><td><a href="/cheval/demo">Demo</a></td></tr></table>
    """
    monkeypatch.setattr(turfomania_race, "fetch_race_html", lambda _: html)

    assert scraping_service.detect_turfomania_race_type(
        "https://www.turfomania.fr/pronostics/partants-race.html?idcourse=123"
    ) == "obstacles"


def test_saved_turfomania_obstacle_race_repairs_legacy_flat_type() -> None:
    class Client:
        updates: list[dict] = []

        def select_one(self, *_args, **_kwargs):
            return {"id": "race-1", "source": "turfomania", "race_type": "flat"}

        def list(self, table, **_kwargs):
            assert table == "flat_race_runners"
            return [{
                "raw_data": {
                    "N°": "4",
                    "POIDS": 67,
                    "RACE_CONDITIONS": "Haies - 3600 mètres",
                }
            }]

        def update(self, table, *, id_value, payload):
            self.updates.append(payload)
            return {"id": id_value, **payload}

    client = Client()
    frame, race = races._saved_frame(client, "race-1")

    assert not frame.empty
    assert race["race_type"] == "obstacles"
    assert client.updates == [{"race_type": "obstacles"}]