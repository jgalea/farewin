import json
from datetime import date, datetime

import pytest

from farewin.google import Google, cache_dir, parse_rows, to_round_trip
from farewin.model import Family, FarewinError

from .conftest import FIXTURES, GOOGLE_ROWS, fake_google_fetch

FAMILY = Family(adults=2, children=2, infants=1, bags=2)


def test_parse_rows_reads_best_and_other_lists():
    payload = json.loads((FIXTURES / "google_payload_LIS_MLA_2026-12-22_2026-12-31_1adult.json").read_text())
    rows = parse_rows(payload)
    assert [(r["price"], r["airlines"]) for r in rows] == [
        (92, ["Ryanair"]),
        (359, ["Lufthansa"]),
        (363, ["Lufthansa", "KM Malta Airlines"]),
        (381, ["Brussels Airlines", "KM Malta Airlines"]),
        (412, ["SWISS", "KM Malta Airlines"]),
        (441, ["KLM", "KM Malta Airlines"]),
    ]
    ryanair = rows[0]["segments"]
    assert len(ryanair) == 1
    assert ryanair[0]["from"] == "LIS" and ryanair[0]["to"] == "MLA"
    assert ryanair[0]["departure"] == [2026, 12, 22, 13, 30]
    assert ryanair[0]["arrival"] == [2026, 12, 22, 17, 40]
    assert ryanair[0]["duration"] == 190
    assert len(rows[1]["segments"]) == 2


def test_parse_rows_skips_unpriced_and_duplicate_items():
    seg = [None, None, None, "LIS", "Lisbon", "Malta", "MLA", None, [13, 30], None, [17, 40], 190] + [None] * 8 + [[2026, 12, 22], [2026, 12, 22]]
    priced = [["FR", ["Ryanair"], [seg]], [[None, 92]]]
    unpriced = [["LH", ["Lufthansa"], [seg]], [[None]]]
    payload = [None, None, [[priced, unpriced]], [[priced]]]
    rows = parse_rows(payload)
    assert len(rows) == 1
    assert rows[0]["price"] == 92
    assert parse_rows([]) == []


def test_to_round_trip_computes_stops_layovers_and_duration():
    row = GOOGLE_ROWS["2026-12-22/2026-12-31"][1]
    rt = to_round_trip(row, date(2026, 12, 31))
    assert rt.price == 1321.0
    assert rt.out.airlines == ("Tap Air Portugal", "KM Malta Airlines")
    assert rt.out.stops == 1
    assert rt.out.departure == datetime(2026, 12, 22, 12, 25)
    assert rt.out.arrival == datetime(2026, 12, 22, 22, 20)
    assert rt.out.layovers == (200,)
    assert rt.out.duration == sum(s["duration"] for s in row["segments"]) + 200 == 535
    assert rt.back_day == date(2026, 12, 31)


def test_round_trips_queries_each_pair_once_and_caches(google, calls):
    pairs = [(date(2026, 12, 18), date(2026, 12, 31)), (date(2026, 12, 22), date(2026, 12, 31))]
    trips = google.round_trips("LIS", "MLA", pairs, FAMILY, "EUR")
    assert len(calls) == 2
    assert calls[0] == ["2026-12-18", "2026-12-31"]
    assert len(trips) == len(GOOGLE_ROWS["2026-12-18/2026-12-31"]) + len(GOOGLE_ROWS["2026-12-22/2026-12-31"])
    assert google.outcome.queried == 2 and google.outcome.cached == 0

    again = Google(fetch=fake_google_fetch(calls), cache=google.cache, log=lambda m: None, delay=0)
    again.round_trips("LIS", "MLA", pairs, FAMILY, "EUR")
    assert len(calls) == 2
    assert again.outcome.cached == 2 and again.outcome.queried == 0


def test_round_trips_counts_empty_pairs(google):
    pairs = [(date(2026, 12, 25), date(2027, 1, 3))]
    assert google.round_trips("LIS", "MLA", pairs, FAMILY, "EUR") == []
    assert google.outcome.empty == 1


def test_max_queries_guard(tmp_path):
    google = Google(fetch=fake_google_fetch([]), cache=tmp_path, max_queries=1, log=lambda m: None, delay=0)
    pairs = [(date(2026, 12, 18), date(2026, 12, 31)), (date(2026, 12, 22), date(2026, 12, 31))]
    with pytest.raises(FarewinError, match="needs 2 Google Flights queries"):
        google.round_trips("LIS", "MLA", pairs, FAMILY, "EUR")


def test_failed_pair_is_skipped_not_fatal(tmp_path):
    def flaky(query):
        if query.flight_data[0].date == "2026-12-22":
            raise RuntimeError("boom")
        return GOOGLE_ROWS["2026-12-18/2026-12-31"]

    google = Google(fetch=flaky, cache=tmp_path, log=lambda m: None, delay=0)
    pairs = [(date(2026, 12, 18), date(2026, 12, 31)), (date(2026, 12, 22), date(2026, 12, 31))]
    trips = google.round_trips("LIS", "MLA", pairs, FAMILY, "EUR")
    assert len(trips) == len(GOOGLE_ROWS["2026-12-18/2026-12-31"])
    assert google.outcome.errors == ["2026-12-22 / 2026-12-31: boom"]

    always = Google(fetch=lambda q: (_ for _ in ()).throw(RuntimeError("blocked")), cache=tmp_path / "x", log=lambda m: None, delay=0)
    with pytest.raises(FarewinError, match="every Google Flights query failed"):
        always.round_trips("LIS", "MLA", pairs[1:], FAMILY, "EUR")


def test_query_asks_google_for_seated_passengers_only(google, calls):
    google.round_trips("LIS", "MLA", [(date(2026, 12, 18), date(2026, 12, 31))], FAMILY, "EUR")
    assert calls == [["2026-12-18", "2026-12-31"]]


def test_cache_dir_respects_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert cache_dir() == tmp_path / "farewin" / "google"
