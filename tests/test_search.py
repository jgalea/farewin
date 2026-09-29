from datetime import date, datetime, time, timedelta

from farewin.google import RoundTrip
from farewin.model import Family, Fees, Leg, Limits, Window
from farewin.search import compose, fee_lines, from_round_trips, leg_flags, merge, rank


def leg(day, dep="10:00", arr="12:00", price=20.0, arr_next_day=False, stops=0, layovers=(), airlines=("Ryanair",)):
    d = date.fromisoformat(day)
    departure = datetime.combine(d, time.fromisoformat(dep))
    arrival = datetime.combine(d + timedelta(days=1 if arr_next_day else 0), time.fromisoformat(arr))
    return Leg(d, departure, arrival, airlines, stops, None, tuple(layovers), price)


FAMILY = Family(adults=2, children=2, infants=1, bags=2)
FEES = Fees(infant=25.0, seat=3.0, bag=25.0)
WINDOW = Window(date(2026, 12, 11), date(2027, 1, 3), 8, 13)
WIDE = Window(date(2026, 12, 1), date(2027, 1, 10), 1, 20)


def test_fee_lines():
    assert fee_lines(FAMILY, FEES) == {"infants": 50.0, "seats": 12.0, "bags": 100.0}
    assert fee_lines(Family(adults=2), FEES) == {"infants": 0.0, "seats": 0.0, "bags": 0.0}


def test_compose_cost_model():
    out = [leg("2026-12-22", price=52.99)]
    back = [leg("2026-12-31", price=38.15)]
    (t,) = compose(out, back, WINDOW, FAMILY, FEES, Limits(), "ryanair")
    assert t.per_person == 91.14
    assert t.base_total == round(91.14 * 4, 2)
    assert t.breakdown == {"fares": 364.56, "infants": 50.0, "seats": 12.0, "bags": 100.0}
    assert t.all_in == 526.56
    assert t.source == "ryanair"
    assert t.airlines == ("Ryanair",)


def test_round_trip_cost_model_uses_google_total():
    out = leg("2026-12-22", price=None, airlines=("Lufthansa", "KM Malta Airlines"), stops=1, layovers=(95,))
    (t,) = from_round_trips([RoundTrip(out, date(2026, 12, 31), 1333.0)], WINDOW, FAMILY, FEES, Limits(), "google")
    assert t.per_person is None
    assert t.base_total == 1333.0
    assert t.all_in == 1333.0 + 50 + 12 + 100
    assert t.back.departure is None and t.back.day == date(2026, 12, 31)
    assert t.nights == 9
    assert t.airlines == ("Lufthansa", "KM Malta Airlines")


def test_window_and_nights_filter():
    out = [leg(d) for d in ("2026-12-10", "2026-12-11", "2026-12-20", "2026-12-28")]
    back = [leg(d) for d in ("2026-12-19", "2026-12-24", "2027-01-03", "2027-01-04")]
    trips = compose(out, back, WINDOW, FAMILY, FEES, Limits(), "ryanair")
    pairs = {(t.out.day.isoformat(), t.back.day.isoformat(), t.nights) for t in trips}
    assert pairs == {("2026-12-11", "2026-12-19", 8), ("2026-12-11", "2026-12-24", 13)}


def test_include_date_must_fall_inside_trip():
    window = Window(date(2026, 12, 1), date(2027, 1, 10), 1, 20, include=date(2026, 12, 25))
    out = [leg("2026-12-20"), leg("2026-12-27")]
    back = [leg("2026-12-30"), leg("2027-01-03")]
    trips = compose(out, back, window, FAMILY, FEES, Limits(), "ryanair")
    assert {(t.out.day.day, t.back.day.day) for t in trips} == {(20, 30), (20, 3)}
    assert window.accepts(date(2026, 12, 25), date(2026, 12, 26))
    assert not window.accepts(date(2026, 12, 26), date(2026, 12, 30))


def test_ranking_is_by_all_in():
    out = [leg("2026-12-20", price=50.0), leg("2026-12-21", price=10.0)]
    back = [leg("2026-12-28", price=10.0), leg("2026-12-29", price=90.0)]
    trips = rank(compose(out, back, WIDE, FAMILY, FEES, Limits(), "ryanair"))
    assert [(t.out.day.day, t.back.day.day) for t in trips] == [(21, 28), (20, 28), (21, 29), (20, 29)]


def test_time_flags():
    limits = Limits(not_before=time(7, 0), not_after=time(23, 0))
    assert leg_flags("out", leg("2026-12-04", dep="05:55", arr="10:05"), limits) == ["out early 05:55"]
    assert leg_flags("back", leg("2026-12-03", dep="20:15", arr="00:25", arr_next_day=True), limits) == ["back lands 00:25 +1"]
    assert leg_flags("back", leg("2026-12-02", dep="19:35", arr="23:45"), limits) == ["back lands 23:45"]
    assert leg_flags("out", leg("2026-12-01", dep="13:30", arr="17:40"), limits) == []
    assert leg_flags("out", leg("2026-12-04", dep="05:55", arr="10:05"), Limits()) == []


def test_stop_and_layover_flags():
    limits = Limits(max_stops=0, max_layover=180)
    assert leg_flags("out", leg("2026-12-04", stops=1, layovers=(95,)), limits) == ["out 1 stop"]
    assert leg_flags("out", leg("2026-12-04", stops=2, layovers=(95, 320)), limits) == ["out 2 stops", "out layover 5h20"]
    assert leg_flags("out", leg("2026-12-04", stops=0), limits) == []
    assert leg_flags("back", Leg(day=date(2026, 12, 31)), limits) == []


def test_flags_attach_to_trips_but_do_not_exclude():
    out = [leg("2026-12-20", dep="05:55", arr="10:05", price=10.0), leg("2026-12-21", price=30.0)]
    back = [leg("2026-12-28", price=10.0)]
    trips = rank(compose(out, back, WIDE, FAMILY, FEES, Limits(not_before=time(7, 0)), "ryanair"))
    assert trips[0].flags == ["out early 05:55"]
    assert trips[1].flags == []


def test_merge_prefers_ryanair_rows_for_the_same_flight():
    out = [leg("2026-12-22", dep="13:30", arr="17:40", price=52.99)]
    back = [leg("2026-12-31", price=38.15)]
    ryanair = compose(out, back, WINDOW, FAMILY, FEES, Limits(), "ryanair")
    same_leg = Leg(date(2026, 12, 22), datetime(2026, 12, 22, 13, 30), datetime(2026, 12, 22, 17, 40), ("Ryanair",), 0, 190)
    same = RoundTrip(same_leg, date(2026, 12, 31), 369.0)
    other_leg = leg("2026-12-22", dep="05:00", arr="13:00", price=None, airlines=("Lufthansa",), stops=1)
    other = RoundTrip(other_leg, date(2026, 12, 31), 1327.0)
    google = from_round_trips([same, other], WINDOW, FAMILY, FEES, Limits(), "google")
    merged, dropped = merge(ryanair, google)
    assert dropped == 1
    assert [(t.source, t.airlines) for t in merged] == [("ryanair", ("Ryanair",)), ("google", ("Lufthansa",))]
    assert merged[0].out.duration == 190
    assert merged[0].base_total == 364.56
