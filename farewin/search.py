from __future__ import annotations

from dataclasses import replace

from .google import RoundTrip
from .model import Family, Fees, Leg, Limits, Trip, Window


def fee_lines(family: Family, fees: Fees) -> dict[str, float]:
    legs = 2
    return {
        "infants": round(fees.infant * family.infants * legs, 2),
        "seats": round(fees.seat * family.adults * legs, 2) if family.children else 0.0,
        "bags": round(fees.bag * family.bags * legs, 2),
    }


def _hm(minutes: int) -> str:
    return f"{minutes // 60}h{minutes % 60:02d}"


def leg_flags(label: str, leg: Leg, limits: Limits) -> list[str]:
    flags = []
    if limits.not_before and leg.departure and leg.departure.time() < limits.not_before:
        flags.append(f"{label} early {leg.departure:%H:%M}")
    if limits.not_after and leg.departure and leg.arrival:
        next_day = leg.arrival.date() > leg.departure.date()
        if next_day or leg.arrival.time() > limits.not_after:
            suffix = " +1" if next_day else ""
            flags.append(f"{label} lands {leg.arrival:%H:%M}{suffix}")
    if limits.max_stops is not None and leg.stops is not None and leg.stops > limits.max_stops:
        flags.append(f"{label} {leg.stops} stop{'s' if leg.stops != 1 else ''}")
    if limits.max_layover is not None and leg.layovers and max(leg.layovers) > limits.max_layover:
        flags.append(f"{label} layover {_hm(max(leg.layovers))}")
    return flags


def _trip(out: Leg, back: Leg, source: str, base: float, family: Family, fees: Fees, limits: Limits) -> Trip:
    extras = fee_lines(family, fees)
    breakdown = {"fares": round(base, 2), **extras}
    all_in = round(base + sum(extras.values()), 2)
    flags = leg_flags("out", out, limits) + leg_flags("back", back, limits)
    return Trip(out, back, (back.day - out.day).days, source, round(base, 2), all_in, breakdown, flags)


def compose(
    outbound: list[Leg], inbound: list[Leg], window: Window, family: Family, fees: Fees, limits: Limits, source: str
) -> list[Trip]:
    trips = []
    for out in outbound:
        for back in inbound:
            if not window.accepts(out.day, back.day):
                continue
            base = (out.price + back.price) * family.paying
            trips.append(_trip(out, back, source, base, family, fees, limits))
    return trips


def from_round_trips(
    round_trips: list[RoundTrip], window: Window, family: Family, fees: Fees, limits: Limits, source: str
) -> list[Trip]:
    trips = []
    for rt in round_trips:
        if not window.accepts(rt.out.day, rt.back_day):
            continue
        trips.append(_trip(rt.out, Leg(day=rt.back_day), source, rt.price, family, fees, limits))
    return trips


def rank(trips: list[Trip]) -> list[Trip]:
    return sorted(trips, key=lambda t: (t.all_in, t.out.day, t.back.day, t.out.departure or t.out.day))


def _key(trip: Trip):
    return (trip.out.day, trip.out.departure, trip.back.day, trip.airlines)


def merge(preferred: list[Trip], others: list[Trip]) -> tuple[list[Trip], int]:
    twins = {_key(t): t for t in others}
    kept = []
    for trip in preferred:
        twin = twins.get(_key(trip))
        if twin and trip.out.duration is None:
            trip.out = replace(trip.out, duration=twin.out.duration)
        kept.append(trip)
    seen = {_key(t) for t in preferred}
    dropped = 0
    for trip in others:
        if _key(trip) in seen:
            dropped += 1
            continue
        kept.append(trip)
    return kept, dropped
