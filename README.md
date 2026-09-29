<div align="center">

# farewin

[![License](https://img.shields.io/badge/LICENSE-MIT-5C9E31?style=for-the-badge)](LICENSE)
[![Python](https://img.shields.io/badge/PYTHON-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org)
[![Built by](https://img.shields.io/badge/BUILT%20BY-JGALEA-8A2BE2?style=for-the-badge&logo=github&logoColor=white)](https://github.com/jgalea)

**Rank round-trip date combos by what the whole family pays, not the per-person headline fare.**

</div>

Fare calendars show the cheapest one-person fare per day. A family of five doesn't pay that. Two adults and two children pay four times the fare on each leg, the lap infant costs a flat fee per leg, and the checked bags add up on top. The cheapest-looking pair of days on the calendar is often not the cheapest trip once you multiply it out, and the trip that lands at 00:25 with three kids is a different kind of expensive.

`farewin` takes a route, a date window, a trip-length range and a family, pulls fares from Ryanair's calendar or from Google Flights, builds every valid out/back pair and ranks them by the all-in estimate. It flags the combos that leave before or land after the hours you'd rather avoid, or that connect when you wanted direct, and `--json` gives an agent the same ranking as data.

## Install

Python 3.10+. It isn't on PyPI, so install from GitHub:

```
uv tool install git+https://github.com/jgalea/farewin
```

`pipx install git+https://github.com/jgalea/farewin` works too. For development, from a clone:

```
uv venv && uv pip install -e . pytest
```

The Ryanair provider uses only the standard library. The Google provider pulls in [fast-flights](https://github.com/AWeirdDev/flights) for its query encoding, and that is the one runtime dependency.

## Use

```
farewin search LIS MLA --from 2026-12-11 --to 2027-01-03 --nights 8-13 \
  --adults 2 --children 2 --infants 1 --bags 2 \
  --include 2026-12-25 --not-before 07:00 --not-after 23:00 --top 5
```

```
Out               Back              Nights  Airline  Stops  Dur    Base  All-in  Flags
Fri 18 Dec 05:55  Thu 31 Dec 16:20      13  Ryanair      0    -  240.56  390.56  out early 05:55
Wed 23 Dec 19:35  Thu 31 Dec 16:20       8  Ryanair      0    -  272.56  422.56  out lands 23:45
Wed 23 Dec 19:35  Fri 01 Jan 10:30       9  Ryanair      0    -  327.92  477.92  out lands 23:45
Sun 20 Dec 06:50  Thu 31 Dec 16:20      11  Ryanair      0    -  336.56  486.56  out early 06:50
Thu 17 Dec 20:15  Tue 29 Dec 18:05      12  Ryanair      0    -  343.92  493.92  out lands 00:25 +1

Cheapest is Fri 18 Dec 05:55 / Thu 31 Dec 16:20 at 390.56 EUR; cheapest flag-free is Tue 22 Dec 13:30 / Thu 31 Dec 16:20 at 514.56 EUR (+124.00).
ryanair: Base = lowest one-person fare per day, out + back, x 4 paying passengers.
All-in adds the same estimated fees to every row, per leg: infant 25.00 x 1, seat 0.00 x 2 adults, bag 25.00 x 2. Amounts in EUR.
```

Fares move daily, so your numbers will differ.

`--from` is the earliest outbound date and `--to` the latest return date. `--nights` takes a range like `8-13` or a single number. `--include` names a date the trip has to span (departure on or before it, return on or after it). `--not-before` flags legs that depart earlier than the given time, `--not-after` flags legs that arrive later than it or on the following day, `--max-stops` (or `--direct`) flags connections, and `--max-layover` flags long ones, in hours. `--strict` drops the flagged combos instead of marking them. `--top` limits the table (default 10), `--currency` defaults to EUR, and `--json` swaps the table for a JSON document with the same ranking, the fee assumptions, per-provider stats, and separate `cheapest` and `best_timed` entries.

### Providers

`--provider ryanair` (the default) reads Ryanair's cheapest-fare-per-day calendar in both directions, two requests per month spanned, and composes round trips from the one-way fares. Ryanair sells round trips as two one-ways, so that is the real price basis. Both legs come with departure and arrival times.

`--provider google` asks Google Flights for each valid out/back date pair as a round trip, priced for the seated party (adults plus children), so the base figure is what Google would show you for that group, on every airline Google lists. The Christmas example is 59 date pairs:

```
farewin search LIS MLA --from 2026-12-11 --to 2027-01-03 --nights 8-13 \
  --adults 2 --children 2 --infants 1 --bags 2 --include 2026-12-25 --provider google --top 5
```

```
Out               Back        Nights  Airline  Stops   Dur    Base  All-in  Flags
Fri 18 Dec 05:55  Thu 31 Dec      13  Ryanair      0  3h10  241.00  391.00
Wed 23 Dec 19:35  Thu 31 Dec       8  Ryanair      0  3h10  277.00  427.00
Wed 23 Dec 19:35  Fri 01 Jan       9  Ryanair      0  3h10  332.00  482.00
Thu 17 Dec 20:15  Wed 30 Dec      13  Ryanair      0  3h10  336.00  486.00
Sun 20 Dec 06:50  Thu 31 Dec      11  Ryanair      0  3h10  337.00  487.00

The cheapest combo is also flag-free.
google: Base = Google Flights round-trip total for 4 seated passengers; the return leg's times aren't shown.
All-in adds the same estimated fees to every row, per leg: infant 25.00 x 1, seat 0.00 x 2 adults, bag 25.00 x 2. Amounts in EUR.
google: 59 date pairs, 59 fetched in 45.4s, 0 from cache, 0 with no flights, 0 skipped.
```

Google's round-trip page lists outbound itineraries with a total that already includes the cheapest matching return, so you get the outbound's times, airlines, stops and duration, and only the date of the return. Responses are cached for six hours under `~/.cache/farewin/google` (or `$XDG_CACHE_HOME`), fetches run two at a time with a short pause between them, and `--max-queries` (default 100) refuses a window that would need more page fetches than that. A date pair that fails to fetch or parse is reported as skipped rather than aborting the run. `--refresh` ignores the cache.

`--provider all` runs both and merges them. Ryanair's flights show up in Google's results too; when the same outbound flight and return date appear in both, the Ryanair row is kept because it carries the return leg's times, it borrows Google's duration, and the output says how many Google rows were dropped for that reason.

### How the cost is modelled

Paying seats are adults plus children. Ryanair has no child fare: children (2 to 11) and teens (12 to 15) pay the same fare as an adult, so `--children` is really "passengers who need a seat and are under 12", which matters only for the seat-fee rule below. Count teens as adults.

The base per combo is the Ryanair one-way fares times paying passengers, or Google's round-trip total for the seated party. On top of that, the same estimated fees are added to every row whatever the source:

- `--infant-fee` per infant per leg. Default 25, which is the €/£25 infant fee in Ryanair's [Table of Fees](https://www.ryanair.com/gb/en/useful-info/help-centre/terms-and-conditions/termsandconditionsar_1713394128) (effective 25 June 2026). Google isn't asked to price the infant: in testing, adding a lap infant to the Google query cut the itineraries returned to a fraction and priced a Ryanair infant at a full adult fare, so the seated party is queried and the infant fee is estimated here
- `--seat-fee` per adult per leg, applied only when children are travelling. Default 0. Under Ryanair's current [family seat policy](https://help.ryanair.com/hc/en-us/articles/12892557860369-What-is-Ryanair-s-Family-Seat-Policy) families can take free random allocation and children are still seated next to an accompanying adult, so no fee is forced. If you'd rather reserve, standard seats run €/£3 to €/£27.50 per passenger per flight depending on route and date; pass the figure you see at booking
- `--bag-fee` per checked bag per leg. Default 25, an assumption sitting inside the €/£21.49 to €/£59.99 range the Table of Fees gives for a 20kg check-in bag bought online. Bag fees differ by airline and many full-service fares include a checked bag, and this tool doesn't keep a per-airline table, so the same estimate is applied to every row. Set it to 0 to compare bare fares, or to your carrier's figure once you know it. Google Flights can fold bag fees into its prices for some airlines, but that made no difference on the routes tested, so it isn't relied on

Everything after the base is an estimate and the output says so. Nothing here models priority boarding, cabin bags beyond the free personal item, sports equipment, or the airport surcharges you'd pay for doing any of this at the desk.

## Limits

The Ryanair fares come from Ryanair's unauthenticated fare-finder endpoint (`/api/farfnd/v4/oneWayFares/.../cheapestPerDay`), which is what the "cheapest per day" calendar on ryanair.com reads. It returns the lowest one-person fare on each day, on the cheapest flight that day. A group of four might not get four seats at that price, and on days with several flights you only see the cheapest one, so a better-timed flight the same day at a higher fare is invisible.

The Google provider reads Google Flights result pages through fast-flights. That is unofficial, it isn't something Google's terms of service invite, and it can break whenever Google changes the page. Requests are throttled and cached to stay at human rates for personal trip planning. Google also lists only the itineraries it puts on the first page for each date pair, usually its "best" set plus a handful of others.

Neither endpoint is a documented public API and either can change or go away without notice. Treat the ranking as a shortlist and confirm on the booking page. Times are local to each airport.

## Tests

```
pytest
```

The tests run offline against captured responses: four Ryanair fare-finder months (LIS-MLA and MLA-LIS, December 2026 and January 2027), a trimmed Google Flights payload, and the parsed Google rows for seven date pairs. They cover both parsers, month spanning across a year end, window, nights and include filtering, the cost model, time, stop and layover flags, strict mode, the Google cache, query cap and skip-on-error behaviour, the provider merge, and the CLI's error paths.
