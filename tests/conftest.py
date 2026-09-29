import json
import re
from pathlib import Path

import pytest

from farewin.google import Google
from farewin.ryanair import Ryanair

FIXTURES = Path(__file__).parent / "fixtures"
FARES_URL = re.compile(r"oneWayFares/([A-Z]{3})/([A-Z]{3})/cheapestPerDay\?outboundMonthOfDate=(\d{4}-\d{2})-01")
GOOGLE_ROWS = json.loads((FIXTURES / "google_rows_LIS_MLA_2A2C.json").read_text())


def fake_ryanair_fetch(calls: list):
    def fetch(url: str):
        calls.append(url)
        if url.endswith("/airports/en/active"):
            return [{"code": "LIS"}, {"code": "MLA"}, {"code": "JFK"}]
        if "/routes/en/airport/" in url:
            return [{"arrivalAirport": {"code": "MLA"}}]
        m = FARES_URL.search(url)
        assert m, url
        orig, dest, month = m.groups()
        path = FIXTURES / f"ryanair_{orig}_{dest}_{month}.json"
        if not path.exists():
            return {"outbound": {"fares": [], "minFare": None, "maxFare": None}}
        return json.loads(path.read_text())

    return fetch


def fake_google_fetch(calls: list):
    def fetch(query):
        dates = [f.date for f in query.flight_data]
        calls.append(dates)
        return GOOGLE_ROWS.get("/".join(dates), [])

    return fetch


@pytest.fixture
def calls():
    return []


@pytest.fixture
def ryanair(calls):
    return Ryanair(fetch=fake_ryanair_fetch(calls))


@pytest.fixture
def google(calls, tmp_path):
    return Google(fetch=fake_google_fetch(calls), cache=tmp_path / "cache", log=lambda msg: None, delay=0)
