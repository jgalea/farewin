import json

import pytest

from farewin import cli
from farewin.ryanair import Ryanair

from .conftest import fake_fetch

ARGS = [
    "search", "LIS", "MLA", "--from", "2026-12-11", "--to", "2027-01-03", "--nights", "8-13",
    "--adults", "2", "--children", "2", "--infants", "1", "--bags", "2",
    "--include", "2026-12-25", "--not-before", "07:00", "--not-after", "23:00",
]


@pytest.fixture(autouse=True)
def offline_provider(monkeypatch):
    monkeypatch.setitem(cli.PROVIDERS, "ryanair", lambda: Ryanair(fetch=fake_fetch([])))


def test_search_table(capsys):
    assert cli.main(ARGS + ["--top", "3"]) == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert lines[0].startswith("Out")
    assert len([l for l in lines[1:] if l and l[0].isalpha() and l[3] == " "]) >= 3
    assert "estimated fees" in out
    assert "lowest one-person fare" in out


def test_search_json_and_strict(capsys):
    assert cli.main(ARGS + ["--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["route"] == {"provider": "ryanair", "origin": "LIS", "destination": "MLA"}
    assert payload["family"]["paying"] == 4
    assert payload["fees"]["estimated"] is True
    assert len(payload["results"]) == 10
    assert payload["cheapest"] == payload["results"][0]
    assert all(8 <= r["nights"] <= 13 for r in payload["results"])
    assert all(r["out"]["day"] <= "2026-12-25" <= r["back"]["day"] for r in payload["results"])
    flagged = [r for r in payload["results"] if r["flags"]]
    assert flagged, "the LIS-MLA fixture has 05:55 departures, so something must be flagged"
    assert payload["best_timed"]["flags"] == []

    assert cli.main(ARGS + ["--json", "--strict"]) == 0
    strict = json.loads(capsys.readouterr().out)
    assert strict["results"]
    assert all(not r["flags"] for r in strict["results"])


def test_no_flights_in_window_is_a_clear_error(capsys):
    rc = cli.main(["search", "LIS", "MLA", "--from", "2027-06-01", "--to", "2027-06-20"])
    assert rc == 1
    assert "no LIS-MLA flights between 2027-06-01 and 2027-06-20" in capsys.readouterr().err


def test_bad_route_is_a_clear_error(capsys):
    rc = cli.main(["search", "LIS", "JFK", "--from", "2026-12-11", "--to", "2027-01-03"])
    assert rc == 1
    assert "doesn't fly LIS-JFK" in capsys.readouterr().err


def test_window_validation(capsys):
    rc = cli.main(["search", "LIS", "MLA", "--from", "2027-01-03", "--to", "2026-12-11"])
    assert rc == 1
    assert "--to is before --from" in capsys.readouterr().err
