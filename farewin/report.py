from __future__ import annotations

import json

from .model import Family, Fees, Trip


def _leg(fare) -> str:
    return f"{fare.departure:%a %d %b %H:%M}"


def _fare_json(fare) -> dict:
    return {
        "day": fare.day.isoformat(),
        "departure": fare.departure.isoformat(),
        "arrival": fare.arrival.isoformat(),
        "fare": fare.price,
        "origin": fare.origin,
        "destination": fare.destination,
    }


def _trip_json(trip: Trip) -> dict:
    return {
        "out": _fare_json(trip.out),
        "back": _fare_json(trip.back),
        "nights": trip.nights,
        "per_person_base": trip.per_person,
        "base_total": trip.base_total,
        "all_in": trip.all_in,
        "breakdown": trip.breakdown,
        "flags": trip.flags,
    }


def best_timed(trips: list[Trip]) -> Trip | None:
    return next((t for t in trips if not t.flags), None)


def summary(trips: list[Trip], currency: str) -> str:
    cheapest = trips[0]
    clean = best_timed(trips)
    if clean is None:
        return "Every combo trips a time limit; nothing is flag-free."
    if clean is cheapest:
        return "The cheapest combo is also flag-free."
    diff = round(clean.all_in - cheapest.all_in, 2)
    return (
        f"Cheapest is {_leg(cheapest.out)} / {_leg(cheapest.back)} at {cheapest.all_in:.2f} {currency}; "
        f"cheapest flag-free is {_leg(clean.out)} / {_leg(clean.back)} at {clean.all_in:.2f} {currency} "
        f"(+{diff:.2f})."
    )


def render_table(trips: list[Trip], currency: str, family: Family, fees: Fees, top: int) -> str:
    rows = [("Out", "Back", "Nights", "Pp", "Base", "All-in", "Flags")]
    for t in trips[:top]:
        rows.append(
            (
                _leg(t.out),
                _leg(t.back),
                str(t.nights),
                f"{t.per_person:.2f}",
                f"{t.base_total:.2f}",
                f"{t.all_in:.2f}",
                ", ".join(t.flags),
            )
        )
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    lines = []
    for r in rows:
        cells = [c.ljust(w) if i in (0, 1, 6) else c.rjust(w) for i, (c, w) in enumerate(zip(r, widths))]
        lines.append("  ".join(cells).rstrip())
    lines.append("")
    lines.append(summary(trips, currency))
    lines.append(
        f"Pp = lowest one-person fare per day, out + back. Base = pp x {family.paying} paying "
        f"passengers. All-in adds estimated fees per leg: infant {fees.infant:.2f} x {family.infants}, "
        f"seat {fees.seat:.2f} x {family.adults if family.children else 0} adults, "
        f"bag {fees.bag:.2f} x {family.bags}. Amounts in {currency}."
    )
    return "\n".join(lines)


def render_json(
    trips: list[Trip], currency: str, family: Family, fees: Fees, top: int, route: dict, window: dict
) -> str:
    clean = best_timed(trips)
    payload = {
        "route": route,
        "window": window,
        "family": {
            "adults": family.adults,
            "children": family.children,
            "infants": family.infants,
            "bags": family.bags,
            "paying": family.paying,
        },
        "fees": {"infant": fees.infant, "seat": fees.seat, "bag": fees.bag, "estimated": True},
        "currency": currency,
        "fare_basis": "lowest one-person fare per day; group availability not guaranteed",
        "results": [_trip_json(t) for t in trips[:top]],
        "cheapest": _trip_json(trips[0]) if trips else None,
        "best_timed": _trip_json(clean) if clean else None,
        "note": summary(trips, currency) if trips else "no combos",
    }
    return json.dumps(payload, indent=2)
