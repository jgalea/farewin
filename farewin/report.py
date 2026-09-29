from __future__ import annotations

import json

from .model import Family, Fees, Leg, Trip


def _leg(leg: Leg) -> str:
    if leg.departure is None:
        return f"{leg.day:%a %d %b}"
    return f"{leg.departure:%a %d %b %H:%M}"


def _hm(minutes: int | None) -> str:
    return "-" if minutes is None else f"{minutes // 60}h{minutes % 60:02d}"


def _stops(leg: Leg) -> str:
    return "-" if leg.stops is None else str(leg.stops)


def _leg_json(leg: Leg) -> dict:
    return {
        "day": leg.day.isoformat(),
        "departure": leg.departure.isoformat() if leg.departure else None,
        "arrival": leg.arrival.isoformat() if leg.arrival else None,
        "airlines": list(leg.airlines),
        "stops": leg.stops,
        "duration_minutes": leg.duration,
        "layover_minutes": list(leg.layovers),
        "fare": leg.price,
    }


def _trip_json(trip: Trip) -> dict:
    return {
        "source": trip.source,
        "out": _leg_json(trip.out),
        "back": _leg_json(trip.back),
        "nights": trip.nights,
        "airlines": list(trip.airlines),
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
        return "Every combo trips a limit; nothing is flag-free."
    if clean is cheapest:
        return "The cheapest combo is also flag-free."
    diff = round(clean.all_in - cheapest.all_in, 2)
    return (
        f"Cheapest is {_leg(cheapest.out)} / {_leg(cheapest.back)} at {cheapest.all_in:.2f} {currency}; "
        f"cheapest flag-free is {_leg(clean.out)} / {_leg(clean.back)} at {clean.all_in:.2f} {currency} "
        f"(+{diff:.2f})."
    )


BASIS = {
    "ryanair": "ryanair: Base = lowest one-person fare per day, out + back, x {paying} paying passengers.",
    "google": (
        "google: Base = Google Flights round-trip total for {paying} seated passengers; "
        "the return leg's times aren't shown."
    ),
}


def notes(
    trips: list[Trip], currency: str, family: Family, fees: Fees, sources: list[str], extra: list[str]
) -> list[str]:
    lines = [summary(trips, currency)]
    for source in sources:
        lines.append(BASIS[source].format(paying=family.paying))
    seat_adults = family.adults if family.children else 0
    lines.append(
        f"All-in adds the same estimated fees to every row, per leg: infant {fees.infant:.2f} x {family.infants}, "
        f"seat {fees.seat:.2f} x {seat_adults} adults, bag {fees.bag:.2f} x {family.bags}. Amounts in {currency}."
    )
    lines.extend(extra)
    return lines


def render_table(trips: list[Trip], top: int, sources: list[str], note_lines: list[str]) -> str:
    multi = len(sources) > 1
    header = ["Out", "Back", "Nights", "Airline", "Stops", "Dur", "Base", "All-in", "Flags"]
    if multi:
        header.insert(0, "Src")
    rows = [header]
    for t in trips[:top]:
        row = [
            _leg(t.out),
            _leg(t.back),
            str(t.nights),
            ", ".join(t.airlines),
            _stops(t.out),
            _hm(t.out.duration),
            f"{t.base_total:.2f}",
            f"{t.all_in:.2f}",
            ", ".join(t.flags),
        ]
        if multi:
            row.insert(0, t.source)
        rows.append(row)
    widths = [max(len(r[i]) for r in rows) for i in range(len(header))]
    right = {"Nights", "Stops", "Dur", "Base", "All-in"}
    lines = []
    for r in rows:
        cells = [c.rjust(w) if header[i] in right else c.ljust(w) for i, (c, w) in enumerate(zip(r, widths))]
        lines.append("  ".join(cells).rstrip())
    lines.append("")
    lines.extend(note_lines)
    return "\n".join(lines)


def render_json(
    trips: list[Trip],
    top: int,
    sources: list[str],
    note_lines: list[str],
    currency: str,
    family: Family,
    fees: Fees,
    route: dict,
    window: dict,
    stats: dict,
) -> str:
    clean = best_timed(trips)
    payload = {
        "route": route,
        "sources": sources,
        "window": window,
        "family": {
            "adults": family.adults,
            "children": family.children,
            "infants": family.infants,
            "bags": family.bags,
            "paying": family.paying,
        },
        "fees": {
            "infant": fees.infant,
            "seat": fees.seat,
            "bag": fees.bag,
            "estimated": True,
            "applied_uniformly": True,
        },
        "currency": currency,
        "basis": {s: BASIS[s].format(paying=family.paying) for s in sources},
        "stats": stats,
        "results": [_trip_json(t) for t in trips[:top]],
        "cheapest": _trip_json(trips[0]) if trips else None,
        "best_timed": _trip_json(clean) if clean else None,
        "notes": note_lines,
    }
    return json.dumps(payload, indent=2)
