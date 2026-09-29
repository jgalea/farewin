from datetime import date, datetime, time, timedelta

from farewin.model import Family, Fare, Fees, Limits
from farewin.search import build_trips, cost, leg_flags


def fare(day: str, dep="10:00", arr="12:00", price=20.0, orig="AAA", dest="BBB", arr_next_day=False) -> Fare:
    d = date.fromisoformat(day)
    departure = datetime.combine(d, time.fromisoformat(dep))
    arrival = datetime.combine(d + timedelta(days=1 if arr_next_day else 0), time.fromisoformat(arr))
    return Fare(d, departure, arrival, price, "EUR", orig, dest)


FAMILY = Family(adults=2, children=2, infants=1, bags=2)
FEES = Fees(infant=25.0, seat=3.0, bag=25.0)


def test_cost_model():
    base, all_in, breakdown = cost(fare("2026-12-22", price=52.99), fare("2026-12-31", price=38.15), FAMILY, FEES)
    assert base == round((52.99 + 38.15) * 4, 2)
    assert breakdown == {"fares": 364.56, "infants": 50.0, "seats": 12.0, "bags": 100.0}
    assert all_in == 526.56


def test_seat_fee_only_when_children_travel():
    solo = Family(adults=2, children=0, infants=0, bags=0)
    _, all_in, breakdown = cost(fare("2026-12-22", price=10.0), fare("2026-12-30", price=10.0), solo, FEES)
    assert breakdown["seats"] == 0.0
    assert all_in == 40.0


def test_window_and_nights_filter():
    out = [fare(d) for d in ("2026-12-10", "2026-12-11", "2026-12-20", "2026-12-28")]
    back = [fare(d, orig="BBB", dest="AAA") for d in ("2026-12-19", "2026-12-24", "2027-01-03", "2027-01-04")]
    trips = build_trips(out, back, date(2026, 12, 11), date(2027, 1, 3), 8, 13, FAMILY, FEES)
    pairs = {(t.out.day.isoformat(), t.back.day.isoformat(), t.nights) for t in trips}
    assert pairs == {("2026-12-11", "2026-12-19", 8), ("2026-12-11", "2026-12-24", 13)}
    assert all(t.out.day >= date(2026, 12, 11) for t in trips)
    assert all(t.back.day <= date(2027, 1, 3) for t in trips)
    assert all(8 <= t.nights <= 13 for t in trips)


def test_include_date_must_fall_inside_trip():
    out = [fare("2026-12-20"), fare("2026-12-27")]
    back = [fare("2026-12-30"), fare("2027-01-03")]
    trips = build_trips(out, back, date(2026, 12, 1), date(2027, 1, 10), 1, 20, FAMILY, FEES, include=date(2026, 12, 25))
    assert {(t.out.day.day, t.back.day.day) for t in trips} == {(20, 30), (20, 3)}


def test_ranking_is_by_all_in():
    out = [fare("2026-12-20", price=50.0), fare("2026-12-21", price=10.0)]
    back = [fare("2026-12-28", price=10.0), fare("2026-12-29", price=90.0)]
    trips = build_trips(out, back, date(2026, 12, 1), date(2027, 1, 10), 1, 20, FAMILY, FEES)
    assert [(t.out.day.day, t.back.day.day) for t in trips] == [(21, 28), (20, 28), (21, 29), (20, 29)]
    assert trips[0].all_in < trips[-1].all_in


def test_time_flags():
    limits = Limits(not_before=time(7, 0), not_after=time(23, 0))
    assert leg_flags("out", fare("2026-12-04", dep="05:55", arr="10:05"), limits) == ["out early 05:55"]
    assert leg_flags("back", fare("2026-12-03", dep="20:15", arr="00:25", arr_next_day=True), limits) == ["back lands 00:25 +1"]
    assert leg_flags("back", fare("2026-12-02", dep="19:35", arr="23:45"), limits) == ["back lands 23:45"]
    assert leg_flags("out", fare("2026-12-01", dep="13:30", arr="17:40"), limits) == []
    assert leg_flags("out", fare("2026-12-04", dep="05:55", arr="10:05"), Limits()) == []


def test_flags_attach_to_trips_but_do_not_exclude():
    out = [fare("2026-12-20", dep="05:55", arr="10:05", price=10.0), fare("2026-12-21", price=30.0)]
    back = [fare("2026-12-28", price=10.0)]
    limits = Limits(not_before=time(7, 0))
    trips = build_trips(out, back, date(2026, 12, 1), date(2027, 1, 10), 1, 20, FAMILY, FEES, limits)
    assert trips[0].flags == ["out early 05:55"]
    assert trips[1].flags == []
