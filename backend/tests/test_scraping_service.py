from datetime import date

from app.services import scraping_service


def test_get_meetings_keeps_catalogued_turfomania_when_zone_turf_fails(monkeypatch) -> None:
    def zone_turf_is_unavailable(*_args, **_kwargs):
        raise RuntimeError("Zone-Turf is unavailable")

    monkeypatch.setattr(scraping_service, "scrape_meeting_urls", zone_turf_is_unavailable)
    monkeypatch.setattr(
        scraping_service,
        "_turfomania_meeting_options",
        lambda _: {"Turfomania · Laval": "turfomania://meetings/meeting-1"},
    )

    assert scraping_service.get_meetings(date(2026, 10, 1)) == {
        "Turfomania · Laval": "turfomania://meetings/meeting-1"
    }
