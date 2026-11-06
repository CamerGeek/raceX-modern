import pandas as pd
import pytest
from fastapi import HTTPException

from app.api import races
from app.schemas.races import CustomCombinationRequest
from app.services import betting_service


def descending_field(size: int = 16) -> pd.DataFrame:
    scores = [round(1.0 - 0.05 * index, 2) for index in range(size)]
    if size >= 10:
        scores[9] = scores[8]
    return pd.DataFrame([
        {"N°": number, "Composite": score}
        for number, score in enumerate(scores, 1)
    ])


def predictions_with_top(*numbers: int) -> dict:
    scores = {number: 0.99 - 0.03 * rank for rank, number in enumerate(numbers)}
    rows = [
        {"NUMERO": number, "place_prob_deep": score}
        for number, score in scores.items()
    ]
    rows += [
        {"NUMERO": number, "place_prob_deep": 0.10}
        for number in range(1, 17)
        if number not in scores
    ]
    return {"status": "ready", "rows": rows}


def test_model_shortlist_orders_by_deep_score_and_limits_eight() -> None:
    predictions = {
        "status": "ready",
        "rows": [
            {"NUMERO": number, "place_prob_deep": score}
            for number, score in [(1, 0.2), (2, 0.9), (3, 0.5), (4, 0.7), (5, 0.1),
                                  (6, 0.8), (7, 0.3), (8, 0.6), (9, 0.4), (10, 0.85)]
        ],
    }

    assert betting_service.model_shortlist_numbers(predictions) == ["2", "10", "6", "4", "8", "3", "9", "7"]


def test_model_shortlist_is_empty_when_predictions_are_unavailable() -> None:
    assert betting_service.model_shortlist_numbers({"status": "unavailable", "rows": []}) == []
    assert betting_service.model_shortlist_numbers(None) == []


def test_plot_twist_matches_frontend_criteria() -> None:
    assert betting_service.plot_twist_numbers(descending_field()) == ["9", "10"]


def test_plot_twist_requires_more_than_eight_scored_horses() -> None:
    assert betting_service.plot_twist_numbers(descending_field(8)) == []


def test_plan_uses_model_shortlist_as_mandatory_base(monkeypatch) -> None:
    monkeypatch.setattr(
        betting_service,
        "analyze_race",
        lambda *_args, **_kwargs: (descending_field(), pd.DataFrame(), None),
    )
    monkeypatch.setattr(
        betting_service,
        "predict_model_race",
        lambda *_args, **_kwargs: predictions_with_top(6, 3, 14),
    )

    plan = betting_service.generate_combination_plan(pd.DataFrame(), "flat")

    assert plan["base"] == ["6", "3", "14"]
    assert plan["substitutes"] == ["9", "10"]
    assert plan["combinations"]
    assert all(set(plan["base"]) <= set(combination) for combination in plan["combinations"])


@pytest.mark.parametrize("race_type", ["flat", "trot"])
def test_plan_keeps_every_shortlist_horse_in_the_combinations(monkeypatch, race_type: str) -> None:
    monkeypatch.setattr(
        betting_service,
        "analyze_race",
        lambda *_args, **_kwargs: (descending_field(), pd.DataFrame(), None),
    )
    shortlist = [6, 3, 14, 4, 8, 5, 12, 1]
    monkeypatch.setattr(
        betting_service,
        "predict_model_race",
        lambda *_args, **_kwargs: predictions_with_top(*shortlist),
    )

    plan = betting_service.generate_combination_plan(pd.DataFrame(), race_type)

    assert plan["base"] == ["6", "3", "14"]
    assert plan["substitutes"] == ["9", "10"]
    assert len(plan["combinations"]) == 10
    assert all(len(combination) == 5 for combination in plan["combinations"])
    assert all(set(plan["base"]) <= set(combination) for combination in plan["combinations"])
    assert all(set(combination) <= {str(number) for number in shortlist} for combination in plan["combinations"])
    covered = {number for combination in plan["combinations"] for number in combination}
    assert covered == {str(number) for number in shortlist}


def test_plan_tops_up_associates_when_the_shortlist_cannot_fill_the_ticket(monkeypatch) -> None:
    monkeypatch.setattr(
        betting_service,
        "analyze_race",
        lambda *_args, **_kwargs: (descending_field(), pd.DataFrame(), None),
    )
    monkeypatch.setattr(
        betting_service,
        "predict_model_race",
        lambda *_args, **_kwargs: {
            "status": "ready",
            "rows": [
                {"NUMERO": number, "place_prob_deep": score}
                for number, score in [(6, 0.99), (3, 0.96), (14, 0.93), (4, 0.90)]
            ],
        },
    )

    plan = betting_service.generate_combination_plan(pd.DataFrame(), "flat", combination_size=6)

    assert plan["base"] == ["6", "3", "14"]
    assert len(plan["combinations"]) == 1
    assert set(plan["combinations"][0]) == {"6", "3", "14", "4", "9", "10"}


def test_plot_twist_horses_substitute_for_unavailable_shortlist_horses(monkeypatch) -> None:
    frame = pd.DataFrame({
        "N°": list(range(1, 17)),
        "NON_PARTANT": [number == 3 for number in range(1, 17)],
    })
    monkeypatch.setattr(
        betting_service,
        "analyze_race",
        lambda *_args, **_kwargs: (descending_field(), pd.DataFrame(), None),
    )
    monkeypatch.setattr(
        betting_service,
        "predict_model_race",
        lambda *_args, **_kwargs: predictions_with_top(6, 3, 14),
    )

    plan = betting_service.generate_combination_plan(frame, "flat")

    assert plan["base"] == ["6", "14", "9"]
    assert plan["substitutes"] == ["10"]
    assert all("3" not in combination for combination in plan["combinations"])


def test_plan_falls_back_to_composite_when_model_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        betting_service,
        "analyze_race",
        lambda *_args, **_kwargs: (descending_field(), pd.DataFrame(), None),
    )
    monkeypatch.setattr(
        betting_service,
        "predict_model_race",
        lambda *_args, **_kwargs: {"status": "unavailable", "rows": []},
    )

    plan = betting_service.generate_combination_plan(pd.DataFrame(), "flat")

    assert plan["base"] == ["1", "2", "3"]


def test_explicit_mandatory_overrides_the_derived_base(monkeypatch) -> None:
    monkeypatch.setattr(
        betting_service,
        "analyze_race",
        lambda *_args, **_kwargs: (descending_field(), pd.DataFrame(), None),
    )

    def fail(*_args, **_kwargs):
        raise AssertionError("model predictions should not be requested for an explicit base")

    monkeypatch.setattr(betting_service, "predict_model_race", fail)

    plan = betting_service.generate_combination_plan(pd.DataFrame(), "flat", mandatory=["7"])

    assert plan["base"] == ["7"]
    assert plan["substitutes"] == ["9", "10"]
    assert all("7" in combination for combination in plan["combinations"])


def test_plan_skips_excluded_horses(monkeypatch) -> None:
    monkeypatch.setattr(
        betting_service,
        "analyze_race",
        lambda *_args, **_kwargs: (descending_field(), pd.DataFrame(), None),
    )
    monkeypatch.setattr(
        betting_service,
        "predict_model_race",
        lambda *_args, **_kwargs: predictions_with_top(6, 3, 14),
    )

    plan = betting_service.generate_combination_plan(pd.DataFrame(), "flat", excluded=["6"])

    assert "6" not in plan["base"]
    assert all("6" not in combination for combination in plan["combinations"])


def custom_field(monkeypatch) -> None:
    monkeypatch.setattr(
        betting_service,
        "analyze_race",
        lambda *_args, **_kwargs: (descending_field(), pd.DataFrame(), None),
    )


def test_custom_combinations_keep_the_subscriber_base(monkeypatch) -> None:
    custom_field(monkeypatch)

    plan = betting_service.generate_custom_combinations(
        pd.DataFrame(), "flat", base=["2", "5"], associates=["1", "3", "4", "6"]
    )

    assert plan["base"] == ["2", "5"]
    assert len(plan["combinations"]) == 4
    assert all(combination[:2] == ["2", "5"] for combination in plan["combinations"])
    assert all(len(combination) == 5 for combination in plan["combinations"])


def test_custom_combinations_default_associates_to_all_other_starters(monkeypatch) -> None:
    custom_field(monkeypatch)

    plan = betting_service.generate_custom_combinations(pd.DataFrame(), "flat", base=["2", "5"])

    assert plan["associates"] == [str(number) for number in range(1, 17) if number not in {2, 5}]
    assert len(plan["combinations"]) == 50


def test_custom_combinations_reject_unknown_starters(monkeypatch) -> None:
    custom_field(monkeypatch)

    try:
        betting_service.generate_custom_combinations(pd.DataFrame(), "flat", base=["99"])
    except ValueError as error:
        assert "99" in str(error)
    else:
        raise AssertionError("expected a ValueError for an unknown base horse")


def test_custom_combinations_require_enough_associates(monkeypatch) -> None:
    custom_field(monkeypatch)

    try:
        betting_service.generate_custom_combinations(
            pd.DataFrame(), "flat", base=["2", "5"], associates=["1"]
        )
    except ValueError as error:
        assert "3" in str(error)
    else:
        raise AssertionError("expected a ValueError for too few associates")


def test_custom_combinations_reject_non_partants(monkeypatch) -> None:
    custom_field(monkeypatch)
    frame = pd.DataFrame({
        "N°": [1, 2],
        "NON_PARTANT": [False, True],
    })

    try:
        betting_service.generate_custom_combinations(frame, "flat", base=["2"])
    except ValueError as error:
        assert "2" in str(error)
    else:
        raise AssertionError("expected a ValueError for a non-partant base horse")


def test_subscriber_combinations_return_the_cached_plan(monkeypatch) -> None:
    monkeypatch.setattr(races, "SupabaseClientWrapper", lambda: object())
    monkeypatch.setattr(
        races,
        "_saved_frame",
        lambda *_args: (
            pd.DataFrame(),
            {"race_type": "flat", "source": "turfomania", "summary": {"q_plus": True}},
        ),
    )
    monkeypatch.setattr(races, "_cached_result", lambda *_args, **_kwargs: {"cached": True})
    monkeypatch.setattr(
        races,
        "generate_combination_plan",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("cached plan should be reused")),
    )

    assert races.subscriber_combinations("race-id", {}) == {"cached": True}


def test_subscriber_combinations_reject_non_quinte_races(monkeypatch) -> None:
    monkeypatch.setattr(races, "SupabaseClientWrapper", lambda: object())
    monkeypatch.setattr(
        races,
        "_saved_frame",
        lambda *_args: (pd.DataFrame(), {"race_type": "flat", "source": "turfomania", "summary": {}}),
    )

    with pytest.raises(HTTPException) as error:
        races.subscriber_combinations("race-id", {})

    assert error.value.status_code == 404


def test_subscriber_custom_combinations_use_the_reducing_system(monkeypatch) -> None:
    captured: dict = {}
    monkeypatch.setattr(races, "SupabaseClientWrapper", lambda: object())
    monkeypatch.setattr(
        races,
        "_saved_frame",
        lambda *_args: (
            pd.DataFrame(),
            {"race_type": "flat", "source": "turfomania", "summary": {"q_plus": True}},
        ),
    )

    def custom(frame, race_type, base, associates, combination_size, max_combinations):
        captured.update(
            frame=frame,
            race_type=race_type,
            base=base,
            associates=associates,
            combination_size=combination_size,
            max_combinations=max_combinations,
        )
        return {"combinations": [["2", "5", "1", "3", "4"]], "base": base, "associates": associates}

    monkeypatch.setattr(races, "generate_custom_combinations", custom)

    response = races.subscriber_custom_combinations(
        "race-id",
        CustomCombinationRequest(base=["2", "5"], associates=["1", "3", "4"]),
        {},
    )

    assert captured["combination_size"] == 5
    assert captured["max_combinations"] == 50
    assert response["combinations"] == [["2", "5", "1", "3", "4"]]
    assert response["base"] == ["2", "5"]
