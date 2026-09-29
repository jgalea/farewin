from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time


class FarewinError(Exception):
    pass


@dataclass(frozen=True)
class Leg:
    day: date
    departure: datetime | None = None
    arrival: datetime | None = None
    airlines: tuple[str, ...] = ()
    stops: int | None = None
    duration: int | None = None
    layovers: tuple[int, ...] = ()
    price: float | None = None


@dataclass(frozen=True)
class Family:
    adults: int = 1
    children: int = 0
    infants: int = 0
    bags: int = 0

    @property
    def paying(self) -> int:
        return self.adults + self.children


@dataclass(frozen=True)
class Fees:
    infant: float = 25.0
    seat: float = 0.0
    bag: float = 25.0


@dataclass(frozen=True)
class Limits:
    not_before: time | None = None
    not_after: time | None = None
    max_stops: int | None = None
    max_layover: int | None = None


@dataclass(frozen=True)
class Window:
    start: date
    end: date
    min_nights: int
    max_nights: int
    include: date | None = None

    def accepts(self, out_day: date, back_day: date) -> bool:
        if not self.start <= out_day <= self.end or back_day > self.end:
            return False
        nights = (back_day - out_day).days
        if nights < self.min_nights or nights > self.max_nights:
            return False
        return self.include is None or out_day <= self.include <= back_day


@dataclass
class Trip:
    out: Leg
    back: Leg
    nights: int
    source: str
    base_total: float
    all_in: float
    breakdown: dict[str, float]
    flags: list[str] = field(default_factory=list)

    @property
    def per_person(self) -> float | None:
        if self.out.price is None or self.back.price is None:
            return None
        return round(self.out.price + self.back.price, 2)

    @property
    def airlines(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(self.out.airlines + self.back.airlines))
