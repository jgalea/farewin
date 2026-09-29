import json
import re
from pathlib import Path

import pytest

from farewin.ryanair import Ryanair

FIXTURES = Path(__file__).parent / "fixtures"
FARES_URL = re.compile(r"oneWayFares/([A-Z]{3})/([A-Z]{3})/cheapestPerDay\?outboundMonthOfDate=(\d{4}-\d{2})-01")


def fake_fetch(calls: list[str]):
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


@pytest.fixture
def calls():
    return []


@pytest.fixture
def provider(calls):
    return Ryanair(fetch=fake_fetch(calls))
