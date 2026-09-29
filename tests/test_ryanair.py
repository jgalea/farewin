import json
from datetime import date, datetime

import pytest

from farewin.model import FarewinError
from farewin.ryanair import months_between, parse_month

from .conftest import FIXTURES


def test_parse_month_keeps_only_priced_days():
    payload = json.loads((FIXTURES / "ryanair_LIS_MLA_2026-12.json").read_text())
    assert len(payload["outbound"]["fares"]) == 31
    legs = parse_month(payload)
    assert len(legs) == 21
    assert {f.day.day for f in legs}.isdisjoint({5, 7, 12, 14, 19, 21, 24, 25, 26, 28})
    first = legs[0]
    assert first.day == date(2026, 12, 1)
    assert first.departure == datetime(2026, 12, 1, 13, 30)
    assert first.arrival == datetime(2026, 12, 1, 17, 40)
    assert first.price == 37.99
    assert first.airlines == ("Ryanair",)
    assert first.stops == 0


def test_parse_month_drops_sold_out_and_unavailable():
    payload = {
        "outbound": {
            "fares": [
                {"day": "2026-12-01", "departureDate": "2026-12-01T10:00:00", "arrivalDate": "2026-12-01T12:00:00",
                 "price": {"value": 10.0, "currencyCode": "EUR"}, "soldOut": True, "unavailable": False},
                {"day": "2026-12-02", "departureDate": None, "arrivalDate": None, "price": None,
                 "soldOut": False, "unavailable": True},
                {"day": "2026-12-03", "departureDate": "2026-12-03T10:00:00", "arrivalDate": "2026-12-03T12:00:00",
                 "price": {"value": 12.5, "currencyCode": "EUR"}, "soldOut": False, "unavailable": False},
            ]
        }
    }
    assert [f.day.day for f in parse_month(payload)] == [3]


def test_parse_month_rejects_wrong_shape():
    with pytest.raises(FarewinError):
        parse_month({"fares": []})


def test_months_between_spans_year_end():
    assert months_between(date(2026, 12, 11), date(2027, 1, 3)) == [date(2026, 12, 1), date(2027, 1, 1)]
    assert months_between(date(2026, 3, 5), date(2026, 3, 20)) == [date(2026, 3, 1)]
    assert months_between(date(2026, 1, 31), date(2026, 4, 1)) == [
        date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1), date(2026, 4, 1)
    ]


def test_fares_fetches_each_month_and_trims_to_window(ryanair, calls):
    legs = ryanair.fares("LIS", "MLA", date(2026, 12, 11), date(2027, 1, 3), "EUR")
    months = sorted(c.split("outboundMonthOfDate=")[1][:7] for c in calls)
    assert months == ["2026-12", "2027-01"]
    assert all(date(2026, 12, 11) <= f.day <= date(2027, 1, 3) for f in legs)
    assert [f.day.day for f in legs] == [11, 13, 15, 16, 17, 18, 20, 22, 23, 27, 29, 30, 31, 1, 3]


def test_check_route_errors_are_specific(ryanair):
    with pytest.raises(FarewinError, match="three-letter"):
        ryanair.check_route("LISBON", "MLA")
    with pytest.raises(FarewinError, match="isn't an airport Ryanair"):
        ryanair.check_route("LIS", "ZZZ")
    with pytest.raises(FarewinError, match="doesn't fly LIS-JFK"):
        ryanair.check_route("LIS", "JFK")
    ryanair.check_route("LIS", "MLA")
