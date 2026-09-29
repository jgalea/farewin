<div align="center">

# farewin

[![License](https://img.shields.io/badge/LICENSE-MIT-5C9E31?style=for-the-badge)](LICENSE)
[![Python](https://img.shields.io/badge/PYTHON-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org)
[![Built by](https://img.shields.io/badge/BUILT%20BY-JGALEA-8A2BE2?style=for-the-badge&logo=github&logoColor=white)](https://github.com/jgalea)

**Rank round-trip date combos by what the whole family pays, not the per-person headline fare.**

</div>

Fare calendars show the cheapest one-person fare per day. A family of five doesn't pay that. Two adults and two children pay four times the fare on each leg, the lap infant costs a flat fee per leg, and the checked bags add up on top. The cheapest-looking pair of days on the calendar is often not the cheapest trip once you multiply it out, and the trip that lands at 00:25 with three kids is a different kind of expensive.

`farewin` takes a route, a date window, a trip-length range and a family, pulls the per-day fares in both directions, builds every valid out/back pair and ranks them by the all-in estimate. It flags the combos that leave before or land after the hours you'd rather avoid, and `--json` gives an agent the same ranking as data.

## Install

Python 3.10+, no dependencies outside the standard library. It isn't on PyPI, so install from GitHub:

```
uv tool install git+https://github.com/jgalea/farewin
```

`pipx install git+https://github.com/jgalea/farewin` works too. For development, from a clone:

```
uv venv && uv pip install -e . pytest
```

## Use

```
farewin search LIS MLA --from 2026-12-11 --to 2027-01-03 --nights 8-13 \
  --adults 2 --children 2 --infants 1 --bags 2 \
  --include 2026-12-25 --not-before 07:00 --not-after 23:00
```

```
Out               Back              Nights     Pp    Base  All-in  Flags
Fri 18 Dec 05:55  Thu 31 Dec 16:20      13  60.14  240.56  390.56  out early 05:55
Wed 23 Dec 19:35  Thu 31 Dec 16:20       8  68.14  272.56  422.56  out lands 23:45
Wed 23 Dec 19:35  Fri 01 Jan 10:30       9  81.98  327.92  477.92  out lands 23:45
Thu 17 Dec 20:15  Wed 30 Dec 16:40      13  83.98  335.92  485.92  out lands 00:25 +1
Sun 20 Dec 06:50  Thu 31 Dec 16:20      11  84.14  336.56  486.56  out early 06:50
Thu 17 Dec 20:15  Tue 29 Dec 18:05      12  85.98  343.92  493.92  out lands 00:25 +1
Fri 18 Dec 05:55  Wed 30 Dec 16:40      12  85.98  343.92  493.92  out early 05:55
Fri 18 Dec 05:55  Tue 29 Dec 18:05      11  87.98  351.92  501.92  out early 05:55
Wed 16 Dec 19:35  Tue 29 Dec 18:05      13  89.98  359.92  509.92  out lands 23:45
Tue 22 Dec 13:30  Thu 31 Dec 16:20       9  91.14  364.56  514.56

Cheapest is Fri 18 Dec 05:55 / Thu 31 Dec 16:20 at 390.56 EUR; cheapest flag-free is Tue 22 Dec 13:30 / Thu 31 Dec 16:20 at 514.56 EUR (+124.00).
Pp = lowest one-person fare per day, out + back. Base = pp x 4 paying passengers. All-in adds estimated fees per leg: infant 25.00 x 1, seat 0.00 x 2 adults, bag 25.00 x 2. Amounts in EUR.
```

Fares move daily, so your numbers will differ.

`--from` is the earliest outbound date and `--to` the latest return date. `--nights` takes a range like `8-13` or a single number. `--include` names a date the trip has to span (departure on or before it, return on or after it). `--not-before` flags legs that depart earlier than the given time, `--not-after` flags legs that arrive later than it or on the following day, and `--strict` drops the flagged combos instead of marking them. `--top` limits the table (default 10), `--currency` defaults to EUR, and `--json` swaps the table for a JSON document with the same ranking, the fee assumptions, and separate `cheapest` and `best_timed` entries.

### How the cost is modelled

Paying seats are adults plus children. Ryanair has no child fare: children (2 to 11) and teens (12 to 15) pay the same fare as an adult, so `--children` is really "passengers who need a seat and are under 12", which matters only for the seat-fee rule below. Count teens as adults.

The all-in figure per combo is:

- the outbound fare plus the return fare, times paying passengers
- plus `--infant-fee` per infant per leg. Default 25, which is the €/£25 infant fee in Ryanair's [Table of Fees](https://www.ryanair.com/gb/en/useful-info/help-centre/terms-and-conditions/termsandconditionsar_1713394128) (effective 25 June 2026)
- plus `--seat-fee` per adult per leg, applied only when children are travelling. Default 0. Under Ryanair's current [family seat policy](https://help.ryanair.com/hc/en-us/articles/12892557860369-What-is-Ryanair-s-Family-Seat-Policy) families can take free random allocation and children are still seated next to an accompanying adult, so no fee is forced. If you'd rather reserve, standard seats run €/£3 to €/£27.50 per passenger per flight depending on route and date; pass the figure you see at booking
- plus `--bag-fee` per checked bag per leg. Default 25, an assumption sitting inside the €/£21.49 to €/£59.99 range the Table of Fees gives for a 20kg check-in bag bought online. The real price depends on route and date, so override it once you've seen yours

Everything after the fares is an estimate and the output says so. Nothing here models priority boarding, cabin bags beyond the free personal item, sports equipment, or the airport surcharges you'd pay for doing any of this at the desk.

## Limits

The fares come from Ryanair's unauthenticated fare-finder endpoint (`/api/farfnd/v4/oneWayFares/.../cheapestPerDay`), which is what the "cheapest per day" calendar on ryanair.com reads. It isn't a documented public API and can change or go away without notice.

It returns the lowest one-person fare on each day, on the cheapest flight that day. Two things follow. A group of four might not get four seats at that price, and on days with several flights you only see the cheapest one, so a better-timed flight the same day at a higher fare is invisible to this tool. Treat the ranking as a shortlist and confirm on the booking page.

Ryanair is the only provider in this version. The provider surface is one class with `check_route` and `fares`, kept small so another carrier can be added, but none is.

Times are local to each airport, as the endpoint reports them.

## Tests

```
pytest
```

The tests run offline against four captured fare-finder responses (LIS-MLA and MLA-LIS, December 2026 and January 2027). They cover the response parsing, month spanning across a year end, window, nights and include filtering, the cost model, the time flags, strict mode, and the CLI's error paths.
