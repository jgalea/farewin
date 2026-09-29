from __future__ import annotations

import argparse
import sys
from datetime import date, time, timedelta

from . import __version__, report
from .google import Google
from .model import Family, FarewinError, Fees, Limits, Window
from .ryanair import Ryanair
from .search import compose, from_round_trips, merge, rank

PROVIDERS = {"ryanair": Ryanair, "google": Google}


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} isn't a YYYY-MM-DD date")


def _time(value: str) -> time:
    try:
        return time.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} isn't an HH:MM time")


def _nights(value: str) -> tuple[int, int]:
    lo, _, hi = value.partition("-")
    try:
        low = int(lo)
        high = int(hi) if hi else low
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} isn't a nights range like 7-10 or 7")
    if low < 0 or high < low:
        raise argparse.ArgumentTypeError(f"{value!r} isn't a valid nights range")
    return low, high


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="farewin",
        description="Rank round-trip date combos by what the whole family pays.",
    )
    parser.add_argument("--version", action="version", version=f"farewin {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("search", help="rank date combos for a route and a family")
    s.add_argument("origin", help="origin airport IATA code, e.g. STN")
    s.add_argument("destination", help="destination airport IATA code, e.g. DUB")
    s.add_argument("--from", dest="start", type=_date, required=True, help="earliest outbound date")
    s.add_argument("--to", dest="end", type=_date, required=True, help="latest return date")
    s.add_argument("--nights", type=_nights, default=(1, 14), help="trip length range, e.g. 8-13 (default 1-14)")
    s.add_argument("--adults", type=int, default=1)
    s.add_argument("--children", type=int, default=0, help="children aged 2 to 11 (teens count as adults)")
    s.add_argument("--infants", type=int, default=0, help="lap infants under 2")
    s.add_argument("--bags", type=int, default=0, help="checked bags per leg")
    s.add_argument("--include", type=_date, help="a date the trip must span, e.g. 2026-12-25")
    s.add_argument("--not-before", type=_time, help="flag departures earlier than HH:MM")
    s.add_argument("--not-after", type=_time, help="flag arrivals later than HH:MM (or next day)")
    s.add_argument("--max-stops", type=int, help="flag itineraries with more stops than this")
    s.add_argument("--direct", action="store_true", help="same as --max-stops 0")
    s.add_argument("--max-layover", type=float, help="flag layovers longer than this many hours")
    s.add_argument("--strict", action="store_true", help="drop flagged combos instead of marking them")
    s.add_argument("--top", type=int, default=10)
    s.add_argument("--currency", default="EUR")
    s.add_argument("--infant-fee", type=float, default=Fees.infant, help="per infant per leg (default 25)")
    s.add_argument(
        "--seat-fee",
        type=float,
        default=Fees.seat,
        help="reserved seat per adult per leg, applied when children travel (default 0: random allocation is free)",
    )
    s.add_argument("--bag-fee", type=float, default=Fees.bag, help="per 20kg checked bag per leg (default 25)")
    s.add_argument("--provider", choices=["ryanair", "google", "all"], default="ryanair")
    s.add_argument("--max-queries", type=int, default=100, help="cap on Google Flights page fetches (default 100)")
    s.add_argument("--refresh", action="store_true", help="ignore the Google Flights cache")
    s.add_argument("--json", dest="as_json", action="store_true", help="emit JSON")
    s.set_defaults(func=search)
    return parser


def date_pairs(window: Window) -> list[tuple[date, date]]:
    pairs = []
    out_day = window.start
    while out_day <= window.end:
        for nights in range(window.min_nights, window.max_nights + 1):
            back_day = out_day + timedelta(days=nights)
            if window.accepts(out_day, back_day):
                pairs.append((out_day, back_day))
        out_day += timedelta(days=1)
    return pairs


def search(args: argparse.Namespace) -> int:
    orig, dest = args.origin.upper(), args.destination.upper()
    if args.end < args.start:
        raise FarewinError("--to is before --from")
    if args.include and not args.start <= args.include <= args.end:
        raise FarewinError("--include falls outside the --from/--to window")
    if args.adults < 1:
        raise FarewinError("need at least one adult")
    if args.infants > args.adults:
        raise FarewinError("each lap infant needs an adult")

    family = Family(args.adults, args.children, args.infants, args.bags)
    fees = Fees(args.infant_fee, args.seat_fee, args.bag_fee)
    max_stops = 0 if args.direct else args.max_stops
    max_layover = int(args.max_layover * 60) if args.max_layover is not None else None
    limits = Limits(args.not_before, args.not_after, max_stops, max_layover)
    min_nights, max_nights = args.nights
    window = Window(args.start, args.end, min_nights, max_nights, args.include)
    sources = ["ryanair", "google"] if args.provider == "all" else [args.provider]

    trips = []
    extra_notes = []
    stats = {}
    if "ryanair" in sources:
        ryanair = PROVIDERS["ryanair"]()
        ryanair.check_route(orig, dest)
        outbound = ryanair.fares(orig, dest, args.start, args.end, args.currency)
        inbound = ryanair.fares(dest, orig, args.start, args.end, args.currency)
        if len(sources) == 1:
            if not outbound:
                raise FarewinError(f"no {orig}-{dest} flights between {args.start} and {args.end}")
            if not inbound:
                raise FarewinError(f"no {dest}-{orig} flights between {args.start} and {args.end}")
        trips = compose(outbound, inbound, window, family, fees, limits, "ryanair")
        stats["ryanair"] = {"outbound_days": len(outbound), "inbound_days": len(inbound), "combos": len(trips)}
    if "google" in sources:
        google = PROVIDERS["google"](max_queries=args.max_queries, refresh=args.refresh)
        google.check_route(orig, dest)
        pairs = date_pairs(window)
        round_trips = google.round_trips(orig, dest, pairs, family, args.currency)
        found = from_round_trips(round_trips, window, family, fees, limits, "google")
        outcome = google.outcome
        stats["google"] = {
            "date_pairs": len(pairs),
            "queried": outcome.queried,
            "cached": outcome.cached,
            "seconds": outcome.seconds,
            "pairs_without_flights": outcome.empty,
            "skipped": outcome.errors,
            "itineraries": len(found),
        }
        extra_notes.append(
            f"google: {len(pairs)} date pairs, {outcome.queried} fetched in {outcome.seconds}s, "
            f"{outcome.cached} from cache, {outcome.empty} with no flights, {len(outcome.errors)} skipped."
        )
        for error in outcome.errors:
            extra_notes.append(f"google skipped {error}")
        if trips:
            trips, dropped = merge(trips, found)
            if dropped:
                extra_notes.append(
                    f"{dropped} Google itineraries were the same Ryanair flights; the Ryanair rows are kept "
                    f"because they carry the return leg's times."
                )
        else:
            trips = found

    trips = rank(trips)
    if args.strict:
        trips = [t for t in trips if not t.flags]
    if not trips:
        raise FarewinError("no round trips match the window, nights and limits")

    currency = args.currency.upper()
    note_lines = report.notes(trips, currency, family, fees, sources, extra_notes)
    if args.as_json:
        route = {"origin": orig, "destination": dest}
        window_json = {
            "from": args.start.isoformat(),
            "to": args.end.isoformat(),
            "nights": [min_nights, max_nights],
            "include": args.include.isoformat() if args.include else None,
            "not_before": args.not_before.isoformat("minutes") if args.not_before else None,
            "not_after": args.not_after.isoformat("minutes") if args.not_after else None,
            "max_stops": max_stops,
            "max_layover_minutes": max_layover,
            "strict": args.strict,
        }
        print(
            report.render_json(
                trips, args.top, sources, note_lines, currency, family, fees, route, window_json, stats
            )
        )
    else:
        print(report.render_table(trips, args.top, sources, note_lines))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except FarewinError as exc:
        print(f"farewin: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
