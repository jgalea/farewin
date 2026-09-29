from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import date, datetime, timedelta

from .model import Fare, FarewinError

NAME = "ryanair"
FARES_URL = (
    "https://www.ryanair.com/api/farfnd/v4/oneWayFares/{orig}/{dest}/cheapestPerDay"
    "?outboundMonthOfDate={month}&currency={currency}"
)
AIRPORTS_URL = "https://www.ryanair.com/api/views/locate/5/airports/en/active"
ROUTES_URL = "https://www.ryanair.com/api/views/locate/searchWidget/routes/en/airport/{orig}"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)
IATA = re.compile(r"^[A-Z]{3}$")


def fetch_json(url: str, timeout: float = 20.0) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
    except urllib.error.HTTPError as exc:
        raise FarewinError(f"Ryanair returned HTTP {exc.code} for {url}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise FarewinError(f"network failure talking to Ryanair: {reason}") from exc
    try:
        return json.loads(body)
    except ValueError as exc:
        raise FarewinError(f"Ryanair sent something that isn't JSON for {url}") from exc


def months_between(start: date, end: date) -> list[date]:
    months = []
    cursor = start.replace(day=1)
    while cursor <= end:
        months.append(cursor)
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    return months


def parse_month(payload: object, orig: str, dest: str) -> list[Fare]:
    if not isinstance(payload, dict) or "outbound" not in payload:
        raise FarewinError("unexpected fare-finder response shape (no 'outbound' key)")
    fares = []
    for row in payload["outbound"].get("fares", []):
        price = row.get("price")
        if not price or row.get("unavailable") or row.get("soldOut"):
            continue
        if not row.get("departureDate") or not row.get("arrivalDate"):
            continue
        fares.append(
            Fare(
                day=date.fromisoformat(row["day"]),
                departure=datetime.fromisoformat(row["departureDate"]),
                arrival=datetime.fromisoformat(row["arrivalDate"]),
                price=float(price["value"]),
                currency=price.get("currencyCode", ""),
                origin=orig,
                destination=dest,
            )
        )
    return fares


class Ryanair:
    name = NAME

    def __init__(self, fetch: Callable[[str], object] = fetch_json):
        self.fetch = fetch

    def check_route(self, orig: str, dest: str) -> None:
        for code in (orig, dest):
            if not IATA.match(code):
                raise FarewinError(f"{code!r} isn't a three-letter IATA airport code")
        airports = self.fetch(AIRPORTS_URL)
        known = {a["code"] for a in airports} if isinstance(airports, list) else set()
        for code in (orig, dest):
            if code not in known:
                raise FarewinError(f"{code} isn't an airport Ryanair flies to")
        routes = self.fetch(ROUTES_URL.format(orig=orig))
        served = {r["arrivalAirport"]["code"] for r in routes} if isinstance(routes, list) else set()
        if dest not in served:
            raise FarewinError(f"Ryanair doesn't fly {orig}-{dest}")

    def fares(self, orig: str, dest: str, start: date, end: date, currency: str) -> list[Fare]:
        found = []
        for month in months_between(start, end):
            url = FARES_URL.format(orig=orig, dest=dest, month=month.isoformat(), currency=currency)
            found.extend(parse_month(self.fetch(url), orig, dest))
        return [f for f in found if start <= f.day <= end]
