import json
from datetime import date

import pytest

from farewin import cli
from farewin.google import Google
from farewin.model import Window
from farewin.ryanair import Ryanair

from .conftest import fake_google_fetch, fake_ryanair_fetch

ARGS = [
    "search", "LIS", "MLA", "--from", "2026-12-11", "--to", "2027-01-03", "--nights", "8-13",
    "--adults", "2", "--children", "2", "--infants", "1", "--bags", "2",
    "--include", "2026-12-25", "--not-before", "07:00", "--not-after", "23:00",
]


@pytest.fixture(autouse=True)
def offline_providers(monkeypatch, tmp_path):
    monkeypatch.setitem(cli.PROVIDERS, "ryanair", lambda: Ryanair(fetch=fake_ryanair_fetch([])))
    monkeypatch.setitem(
        cli.PROVIDERS,
        "google",
        lambda **kw: Google(fetch=fake_google_fetch([]), cache=tmp_path / "cache", log=lambda m: None, delay=0, **kw),
    )


def test_date_pairs_match_window():
    window = Window(date(2026, 12, 11), date(2027, 1, 3), 8, 13, include=date(2026, 12, 25))
    pairs = cli.date_pairs(window)
    assert len(pairs) == 59
    assert pairs[0] == (date(2026, 12, 12), date(2026, 12, 25))
    assert pairs[-1] == (date(2026, 12, 25), date(2027, 1, 3))
    assert all(window.accepts(o, b) for o, b in pairs)


def test_search_table(capsys):
    assert cli.main(ARGS + ["--top", "3"]) == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert lines[0].split() == ["Out", "Back", "Nights", "Airline", "Stops", "Dur", "Base", "All-in", "Flags"]
    assert all("Ryanair" in line for line in lines[1:4])
    assert "estimated fees" in out
    assert "lowest one-person fare" in out


def test_search_json_and_strict(capsys):
    assert cli.main(ARGS + ["--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["sources"] == ["ryanair"]
    assert payload["family"]["paying"] == 4
    assert payload["fees"]["estimated"] is True
    assert len(payload["results"]) == 10
    assert payload["cheapest"] == payload["results"][0]
    assert all(8 <= r["nights"] <= 13 for r in payload["results"])
    assert all(r["out"]["day"] <= "2026-12-25" <= r["back"]["day"] for r in payload["results"])
    assert [r for r in payload["results"] if r["flags"]], "the fixture has 05:55 departures, so something must be flagged"
    assert payload["best_timed"]["flags"] == []

    assert cli.main(ARGS + ["--json", "--strict"]) == 0
    strict = json.loads(capsys.readouterr().out)
    assert strict["results"]
    assert all(not r["flags"] for r in strict["results"])


def test_google_provider(capsys):
    assert cli.main(ARGS + ["--provider", "google", "--json", "--direct"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["sources"] == ["google"]
    assert payload["stats"]["google"]["date_pairs"] == 59
    assert payload["stats"]["google"]["queried"] == 59
    assert payload["stats"]["google"]["skipped"] == []
    results = payload["results"]
    assert results[0]["source"] == "google"
    assert results[0]["airlines"] == ["Ryanair"]
    assert results[0]["base_total"] == 241.0
    assert results[0]["all_in"] == 241.0 + 50 + 100
    assert results[0]["back"]["departure"] is None
    assert results[0]["per_person_base"] is None
    stopped = [r for r in results if r["out"]["stops"]]
    assert stopped and all("stop" in " ".join(r["flags"]) for r in stopped)
    assert "google" in payload["basis"]


def test_all_providers_merge(capsys):
    assert cli.main(ARGS + ["--provider", "all", "--json", "--top", "40"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["sources"] == ["ryanair", "google"]
    sources = {r["source"] for r in payload["results"]}
    assert sources == {"ryanair", "google"}
    keys = [(r["out"]["departure"], r["back"]["day"], tuple(r["airlines"])) for r in payload["results"]]
    assert len(keys) == len(set(keys))
    ryanair_rows = [r for r in payload["results"] if r["airlines"] == ["Ryanair"]]
    assert all(r["source"] == "ryanair" for r in ryanair_rows)
    assert any("same Ryanair flights" in n for n in payload["notes"])

    assert cli.main(ARGS + ["--provider", "all", "--top", "3"]) == 0
    table = capsys.readouterr().out
    assert table.splitlines()[0].startswith("Src")


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


def test_max_queries_guard_message(capsys):
    rc = cli.main(ARGS + ["--provider", "google", "--max-queries", "10"])
    assert rc == 1
    assert "needs 59 Google Flights queries" in capsys.readouterr().err
