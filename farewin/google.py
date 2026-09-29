from __future__ import annotations

import hashlib
import json
import os
import random
import sys
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .model import Family, FarewinError, Leg

NAME = "google"
URL = "https://www.google.com/travel/flights"
CACHE_TTL = 6 * 3600
WORKERS = 2
DELAY = 0.4


@dataclass(frozen=True)
class RoundTrip:
    out: Leg
    back_day: date
    price: float


def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "farewin" / "google"


def build_query(orig: str, dest: str, out_day: date, back_day: date, family: Family, currency: str):
    from fast_flights import FlightQuery, Passengers, create_query

    if family.paying > 9:
        raise FarewinError("Google Flights prices at most 9 seated passengers per search")
    return create_query(
        flights=[
            FlightQuery(date=out_day.isoformat(), from_airport=orig, to_airport=dest),
            FlightQuery(date=back_day.isoformat(), from_airport=dest, to_airport=orig),
        ],
        trip="round-trip",
        passengers=Passengers(adults=family.adults, children=family.children),
        currency=currency,
    )


def fetch_html(query) -> str:
    from primp import Client

    client = Client(impersonate="chrome_145", impersonate_os="macos", referer=True, cookie_store=True)
    response = client.get(URL, params=query.params(), headers={"Cookie": "SOCS=CAI"})
    if response.status_code != 200:
        raise FarewinError(f"Google Flights returned HTTP {response.status_code}")
    return response.text


def extract_payload(html: str) -> list:
    from selectolax.lexbor import LexborHTMLParser

    script = LexborHTMLParser(html).css_first(r"script.ds\:1")
    if script is None:
        if "consent.google.com" in html:
            raise FarewinError("Google Flights answered with a consent page instead of results")
        raise FarewinError("Google Flights page layout changed; no results script found")
    data = script.text().split("data:", 1)[1].rsplit(",", 1)[0]
    if data.endswith("errorHasStatus: true"):
        return []
    return json.loads(data)


def _time(value) -> tuple[int, int]:
    padded = [*(value or []), None, None]
    return (padded[0] or 0, padded[1] or 0)


def parse_rows(payload: list) -> list[dict]:
    rows = []
    if not payload:
        return rows
    for section in (2, 3):
        block = payload[section] if section < len(payload) else None
        items = block[0] if isinstance(block, list) and block and isinstance(block[0], list) else []
        for item in items:
            flight = item[0]
            try:
                price = item[1][0][1]
            except (IndexError, TypeError):
                price = None
            if price is None:
                continue
            segments = []
            for seg in flight[2]:
                segments.append(
                    {
                        "from": seg[3],
                        "to": seg[6],
                        "departure": list(seg[20]) + list(_time(seg[8])),
                        "arrival": list(seg[21]) + list(_time(seg[10])),
                        "duration": seg[11],
                    }
                )
            row = {"price": price, "airlines": list(flight[1]), "segments": segments}
            if row not in rows:
                rows.append(row)
    return rows


def _dt(parts: list[int]) -> datetime:
    return datetime(*parts[:5])


def to_round_trip(row: dict, back_day: date) -> RoundTrip:
    segments = row["segments"]
    departure = _dt(segments[0]["departure"])
    arrival = _dt(segments[-1]["arrival"])
    layovers = tuple(
        int((_dt(b["departure"]) - _dt(a["arrival"])).total_seconds() // 60)
        for a, b in zip(segments, segments[1:])
    )
    out = Leg(
        day=departure.date(),
        departure=departure,
        arrival=arrival,
        airlines=tuple(row["airlines"]),
        stops=len(segments) - 1,
        duration=sum(s["duration"] for s in segments) + sum(layovers),
        layovers=layovers,
    )
    return RoundTrip(out=out, back_day=back_day, price=float(row["price"]))


@dataclass
class Outcome:
    queried: int = 0
    cached: int = 0
    empty: int = 0
    errors: list[str] = None
    seconds: float = 0.0

    def __post_init__(self):
        self.errors = self.errors or []


class Google:
    name = NAME

    def __init__(
        self,
        fetch: Callable[[object], list[dict]] | None = None,
        cache: Path | None = None,
        max_queries: int = 100,
        refresh: bool = False,
        log: Callable[[str], None] | None = None,
        delay: float = DELAY,
    ):
        self.fetch = fetch or (lambda query: parse_rows(extract_payload(fetch_html(query))))
        self.cache = cache_dir() if cache is None else cache
        self.max_queries = max_queries
        self.refresh = refresh
        self.delay = delay
        self.log = log or (lambda msg: print(msg, file=sys.stderr))
        self.outcome = Outcome()

    def check_route(self, orig: str, dest: str) -> None:
        for code in (orig, dest):
            if len(code) != 3 or not code.isalpha():
                raise FarewinError(f"{code!r} isn't a three-letter IATA airport code")

    def _cache_path(self, query) -> Path:
        key = hashlib.sha1(json.dumps(query.params(), sort_keys=True).encode()).hexdigest()
        return self.cache / f"{key}.json"

    def _read_cache(self, path: Path) -> list[dict] | None:
        if self.refresh or not path.exists():
            return None
        try:
            stored = json.loads(path.read_text())
        except (OSError, ValueError):
            return None
        if time.time() - stored.get("fetched", 0) > CACHE_TTL:
            return None
        return stored.get("rows")

    def _write_cache(self, path: Path, rows: list[dict]) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"fetched": time.time(), "rows": rows}))
        except OSError:
            pass

    def _fetch_pair(self, query) -> list[dict]:
        time.sleep(self.delay + random.random() * self.delay)
        return self.fetch(query)

    def round_trips(
        self, orig: str, dest: str, pairs: list[tuple[date, date]], family: Family, currency: str
    ) -> list[RoundTrip]:
        queries = [(pair, build_query(orig, dest, pair[0], pair[1], family, currency)) for pair in pairs]
        results: dict[tuple[date, date], list[dict]] = {}
        pending = []
        for pair, query in queries:
            rows = self._read_cache(self._cache_path(query))
            if rows is None:
                pending.append((pair, query))
            else:
                results[pair] = rows
        self.outcome.cached = len(results)
        if len(pending) > self.max_queries:
            raise FarewinError(
                f"{orig}-{dest} needs {len(pending)} Google Flights queries for this window "
                f"(limit {self.max_queries}); narrow --from/--to or --nights, or raise --max-queries"
            )
        if pending:
            self.log(f"google: {len(pairs)} date pairs, {len(results)} cached, querying {len(pending)}")
        started = time.time()

        def run(item):
            pair, query = item
            try:
                rows = self._fetch_pair(query)
            except Exception as exc:
                return pair, None, f"{pair[0]} / {pair[1]}: {exc}"
            self._write_cache(self._cache_path(query), rows)
            return pair, rows, None

        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for pair, rows, error in pool.map(run, pending):
                if error:
                    self.outcome.errors.append(error)
                else:
                    results[pair] = rows
        self.outcome.queried = len(pending)
        self.outcome.seconds = round(time.time() - started, 1)
        if not results and self.outcome.errors:
            raise FarewinError(f"every Google Flights query failed; first error: {self.outcome.errors[0]}")

        trips = []
        for pair, rows in results.items():
            if not rows:
                self.outcome.empty += 1
            for row in rows:
                trips.append(to_round_trip(row, pair[1]))
        return trips
