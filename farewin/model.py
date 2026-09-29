from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time


class FarewinError(Exception):
    pass


@dataclass(frozen=True)
class Fare:
    day: date
    departure: datetime
    arrival: datetime
    price: float
    currency: str
    origin: str
    destination: str


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


@dataclass
class Trip:
    out: Fare
    back: Fare
    nights: int
    base_total: float
    all_in: float
    breakdown: dict[str, float]
    flags: list[str] = field(default_factory=list)

    @property
    def per_person(self) -> float:
        return round(self.out.price + self.back.price, 2)
