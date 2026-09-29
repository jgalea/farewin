from __future__ import annotations

from datetime import date

from .model import Family, Fare, Fees, Limits, Trip


def cost(out: Fare, back: Fare, family: Family, fees: Fees) -> tuple[float, float, dict[str, float]]:
    legs = 2
    fares = (out.price + back.price) * family.paying
    infants = fees.infant * family.infants * legs
    seats = fees.seat * family.adults * legs if family.children else 0.0
    bags = fees.bag * family.bags * legs
    breakdown = {
        "fares": round(fares, 2),
        "infants": round(infants, 2),
        "seats": round(seats, 2),
        "bags": round(bags, 2),
    }
    return round(fares, 2), round(fares + infants + seats + bags, 2), breakdown


def leg_flags(label: str, fare: Fare, limits: Limits) -> list[str]:
    flags = []
    if limits.not_before and fare.departure.time() < limits.not_before:
        flags.append(f"{label} early {fare.departure:%H:%M}")
    if limits.not_after:
        next_day = fare.arrival.date() > fare.departure.date()
        if next_day or fare.arrival.time() > limits.not_after:
            suffix = " +1" if next_day else ""
            flags.append(f"{label} lands {fare.arrival:%H:%M}{suffix}")
    return flags


def build_trips(
    outbound: list[Fare],
    inbound: list[Fare],
    start: date,
    end: date,
    min_nights: int,
    max_nights: int,
    family: Family,
    fees: Fees,
    limits: Limits = Limits(),
    include: date | None = None,
) -> list[Trip]:
    trips = []
    for out in outbound:
        if not start <= out.day <= end:
            continue
        for back in inbound:
            if back.day > end:
                continue
            nights = (back.day - out.day).days
            if nights < min_nights or nights > max_nights:
                continue
            if include and not out.day <= include <= back.day:
                continue
            base, all_in, breakdown = cost(out, back, family, fees)
            flags = leg_flags("out", out, limits) + leg_flags("back", back, limits)
            trips.append(Trip(out, back, nights, base, all_in, breakdown, flags))
    trips.sort(key=lambda t: (t.all_in, t.out.day, t.back.day))
    return trips
