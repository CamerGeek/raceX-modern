from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ScrapeRequest(BaseModel):
    url: str = Field(min_length=1)
    race_type: str = Field(pattern="^(flat|trot)$")
    source: str = "zone-turf"


class AnalysisRequest(ScrapeRequest):
    race_id: str | None = None
    include_handicap: bool = True
    max_horses: int = Field(default=8, ge=1, le=30)


class TurfomaniaQuinteAnalysisRequest(BaseModel):
    meeting_id: str = Field(min_length=1)
    include_handicap: bool = True
    max_horses: int = Field(default=8, ge=1, le=30)


class BettingRequest(BaseModel):
    race_id: str = Field(min_length=1)
    race_type: str = Field(pattern="^(flat|trot)$")
    simulations: int = Field(default=5000, ge=100, le=50000)
    combination_size: int = Field(default=5, ge=1, le=20)
    max_combinations: int = Field(default=50, ge=1, le=500)
    mandatory: list[str] = []
    excluded: list[str] = []


class RaceResponse(BaseModel):
    race_type: str
    source: str
    row_count: int
    columns: list[str]
    rows: list[dict[str, Any]]


class ModelPredictionResponse(BaseModel):
    status: Literal["ready", "unsupported", "unavailable"]
    model_version: str | None = None
    bet_list: list[int] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    message: str | None = None


class AnalysisResponse(RaceResponse):
    model_config = ConfigDict(protected_namespaces=())

    model_version: str
    prognosis: list[dict[str, Any]]
    prognosis_outside_top_composite: list[dict[str, Any]] | None = None
    signals: list[dict[str, str]] = []
    sections: list[dict[str, Any]] = []
    overview: dict[str, Any] = {}
    race_details: str = ""
    handicap: dict[str, Any] | None = None
    model_predictions: ModelPredictionResponse | None = None


class TurfomaniaQuinteAnalysisResponse(AnalysisResponse):
    race_id: str
