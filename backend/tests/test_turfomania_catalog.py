from datetime import date

from bs4 import BeautifulSoup
from turfomania_reunions import parse_race_details
from turfomania_reunions import parse_reunion

from app.services.turfomania_catalog import persist_turfomania_reunions

CARD_TEXT = (
    "R1 C1 Grand Prix Anjou-maine Attelé - Groupe III - 2850m - 100000 € "
    "15 partants Q+ GRP 3 13h55 Parier avec"
)

RACE_HREF = "https://www.turfomania.fr/pronostics/partants-mercredi-30-septembre-2026-laval-grand-prix-anjou-maine.html?idcourse=684060"

REUNIONS = [
    {
        "reunion": "Réunion 1",
        "track": "Laval",
        "header_right": "mercredi 30 septembre 2026",
        "races": [
            {"code": "R1 C1", "name": "Grand Prix Anjou-maine", "href": RACE_HREF, "text": CARD_TEXT},
        ],
    }
]


def test_parse_race_details() -> None:
    details = parse_race_details(CARD_TEXT)

    assert details["distance_m"] == 2850
    assert details["prize_eur"] == 100000
    assert details["starters"] == 15
    assert details["start_time"] == "13h55"
    assert details["q_plus"] is True
    assert details["discipline"] == "attelé"
    assert details["race_type"] == "trot"


def test_parse_race_details_flat_without_q_plus() -> None:
    details = parse_race_details("R2 C3 Prix de la Plaine Plat - 1600m - 25000 € 12 partants 14h10")

    assert details["distance_m"] == 1600
    assert details["q_plus"] is False
    assert details["discipline"] == "plat"
    assert details["race_type"] == "flat"


def test_parse_reunion_excludes_non_partants_links() -> None:
    reunion = BeautifulSoup(
        '''<div class="reunion-container"><div class="header-row"><span class="badge-text">R1</span><span class="title">Auteuil</span></div>
        <a class="card-course" href="/quinte/"><span class="badge-text">R1</span><span class="hippodrome">Quinté</span></a>
        <a class="card-course" href="/pronostics/partants-test.html?idcourse=42"><span class="badge-text">R1</span><span class="hippodrome">Prix Test</span></a></div>''',
        "html.parser",
    ).select_one(".reunion-container")

    parsed = parse_reunion(reunion)

    assert [race["href"] for race in parsed["races"]] == [
        "https://www.turfomania.fr/pronostics/partants-test.html?idcourse=42"
    ]


class _CatalogClient:
    def __init__(self, *, existing_meeting: dict | None = None, existing_races: dict[str, dict] | None = None) -> None:
        self.existing_meeting = existing_meeting
        self.existing_races = existing_races or {}
        self.meeting_filters: list[list[tuple[str, str, object]]] = []
        self.race_filters: list[list[tuple[str, str, object]]] = []
        self.inserts: list[tuple[str, dict]] = []
        self.updates: list[tuple[str, str, dict]] = []

    def select_one(self, table: str, *, filters: list[tuple[str, str, object]] | None = None, **_: object) -> dict | None:
        if table == "meetings":
            self.meeting_filters.append(filters or [])
            return self.existing_meeting
        if table == "races":
            self.race_filters.append(filters or [])
            race_key = {column: value for column, _, value in filters or []}.get("race_key")
            return self.existing_races.get(race_key)
        return None

    def insert(self, table: str, payload: dict) -> dict:
        self.inserts.append((table, payload))
        return {"id": "meeting-1" if table == "meetings" else "race-1", **payload}

    def update(self, table: str, *, id_value: str, payload: dict) -> dict:
        self.updates.append((table, id_value, payload))
        return {"id": id_value, **payload}


def test_persist_creates_meeting_and_pending_race() -> None:
    client = _CatalogClient()

    result = persist_turfomania_reunions(REUNIONS, meeting_date=date(2026, 9, 30), client=client)

    assert result["meeting_count"] == 1
    assert result["races_created"] == 1
    assert result["races_updated"] == 0
    assert client.meeting_filters == [[("source", "eq", "turfomania"), ("meeting_date", "eq", "2026-09-30"), ("name", "eq", "Laval")]]

    inserts = {table: payload for table, payload in client.inserts}
    meeting_payload = inserts.get("meetings")
    assert meeting_payload is not None
    assert meeting_payload["url"] is None
    assert meeting_payload["metadata"] == {"reunion": "Réunion 1", "header_right": "mercredi 30 septembre 2026"}

    race_payload = inserts["races"]
    assert race_payload["race_key"] == "R1C1"
    assert race_payload["race_number"] == "1"
    assert race_payload["race_type"] == "trot"
    assert race_payload["source_url"] == RACE_HREF
    assert race_payload["status"] == "pending"
    assert race_payload["summary"]["q_plus"] is True
    assert race_payload["summary"]["distance_m"] == 2850
    assert race_payload["summary"]["name"] == "Grand Prix Anjou-maine"


def test_persist_refreshes_pending_race_on_rerun() -> None:
    client = _CatalogClient(
        existing_meeting={"id": "meeting-1", "name": "Laval", "source": "turfomania"},
        existing_races={"R1C1": {"id": "race-9", "race_key": "R1C1", "status": "pending", "race_type": "trot"}},
    )

    result = persist_turfomania_reunions(REUNIONS, meeting_date=date(2026, 9, 30), client=client)

    assert result["races_created"] == 0
    assert result["races_updated"] == 1
    assert client.inserts == []
    assert len(client.updates) == 1
    table, id_value, payload = client.updates[0]
    assert (table, id_value) == ("races", "race-9")
    assert payload["status"] == "pending"


def test_persist_skips_race_already_scraped() -> None:
    client = _CatalogClient(
        existing_meeting={"id": "meeting-1", "name": "Laval", "source": "turfomania"},
        existing_races={"R1C1": {"id": "race-9", "race_key": "R1C1", "status": "scraped", "race_type": "trot"}},
    )

    result = persist_turfomania_reunions(REUNIONS, meeting_date=date(2026, 9, 30), client=client)

    assert result["races_skipped"] == 1
    assert result["races"][0]["status"] == "scraped"
    assert client.inserts == []
    assert client.updates == []


def test_persist_skips_card_without_href() -> None:
    reunions = [{"reunion": "Réunion 2", "track": "Vincennes", "header_right": "", "races": [{"code": "R2 C1", "name": "Prix X", "href": "", "text": "R2 C1 Prix X"}]}]
    client = _CatalogClient()

    result = persist_turfomania_reunions(reunions, meeting_date=date(2026, 9, 30), client=client)

    assert result["race_count"] == 0
    assert client.meeting_filters == [[("source", "eq", "turfomania"), ("meeting_date", "eq", "2026-09-30"), ("name", "eq", "Vincennes")]]
