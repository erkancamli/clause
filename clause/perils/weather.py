"""Drought cover on cumulative rainfall.

The index is total rainfall recorded at a named weather station across a
defined window, usually a growing season. The policy pays as the total falls
below a share of the station's long run normal, which is how agricultural
parametric cover is written almost everywhere it exists.

Model. Cumulative rainfall over a season is conventionally fitted as a gamma
distribution: it is non negative, right skewed, and the fit is good enough that
meteorological services publish gamma parameters for exactly this purpose. Two
numbers per station and season pin it down:

    normal_mm     the long run mean for the window
    variability   the coefficient of variation

From those, shape = 1 / variability squared and scale = normal / shape, which
is the standard method of moments fit.

Because the policy pays when the index falls, its exceedance function is a
lower tail probability, and the curve runs downwards. Everything else, pricing
included, is unchanged, which is the point of keeping the structure and the
model separate.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Callable

from ..mathx import gamma_cdf
from .base import DataSource, Direction, Peril, PayoutCurve, Shape, curve_from_spec


@dataclass(frozen=True, slots=True)
class Station:
    """A weather station and the seasonal rainfall it normally records."""

    code: str
    name: str
    region: str
    latitude: float
    longitude: float
    #: The month and day the season's window opens, the same every year. This
    #: is a date in the calendar and not a length of time, because the rain a
    #: policy is written on falls in particular months: a window that began
    #: whenever a policy was bought would be measuring a different season for
    #: every buyer, and there would be nothing for a sales deadline to close
    #: against.
    opens: tuple[int, int]
    window_days: int
    normal_mm: float       # long run mean rainfall across the window
    variability: float     # coefficient of variation of that total

    def __post_init__(self) -> None:
        month, day = self.opens
        if not 1 <= month <= 12 or not 1 <= day <= 28:
            raise ValueError(f"the season opens on a real date every year, not {self.opens}")
        if self.window_days < 30:
            raise ValueError("a rainfall season is longer than a month")
        if self.normal_mm <= 0:
            raise ValueError("normal rainfall must be positive")
        if not 0.05 <= self.variability <= 2.0:
            raise ValueError(
                f"coefficient of variation out of plausible range: {self.variability}"
            )

    @property
    def country(self) -> str:
        """The country the station stands in, from its code."""
        return self.code.split("-", 1)[0].upper()

    def window(self, year: int) -> tuple[dt.date, dt.date]:
        """The first and last day of this station's season in a given year."""
        opens = dt.date(year, *self.opens)
        return opens, opens + dt.timedelta(days=self.window_days - 1)

    def opens_on_or_after(self, day: dt.date) -> dt.date:
        """The next opening of this season on or after a day."""
        this_year = dt.date(day.year, *self.opens)
        return this_year if this_year >= day else dt.date(day.year + 1, *self.opens)

    @property
    def season(self) -> str:
        """The window in words, read off the dates so the two cannot drift."""
        opens, closes = self.window(2001)  # a common year; the label has no year
        return f"{opens:%B} to {closes:%B}"

    @property
    def shape(self) -> float:
        """Gamma shape by method of moments."""
        return 1.0 / (self.variability ** 2)

    @property
    def scale(self) -> float:
        """Gamma scale by method of moments."""
        return self.normal_mm / self.shape


# Stations the demo offers. A live deployment reads these from the national
# meteorological service; the figures below are the shape of that input.
STATIONS: dict[str, Station] = {
    "TR-EDIRNE": Station(
        "TR-EDIRNE", "Edirne", "Thrace", 41.68, 26.56,
        (4, 1), 150, 186.0, 0.34,
    ),
    "TR-KIRKLARELI": Station(
        "TR-KIRKLARELI", "Kırklareli", "Thrace", 41.74, 27.22,
        (4, 1), 150, 178.0, 0.35,
    ),
    "TR-TEKIRDAG": Station(
        "TR-TEKIRDAG", "Tekirdağ", "Thrace", 40.98, 27.51,
        (4, 1), 150, 165.0, 0.36,
    ),
    "TR-BALIKESIR": Station(
        "TR-BALIKESIR", "Balıkesir", "Marmara", 39.65, 27.89,
        (4, 1), 150, 158.0, 0.37,
    ),
    "TR-BURSA": Station(
        "TR-BURSA", "Bursa", "Marmara", 40.19, 29.06,
        (4, 1), 150, 172.0, 0.35,
    ),
    "TR-CANAKKALE": Station(
        "TR-CANAKKALE", "Çanakkale", "Marmara", 40.15, 26.41,
        (4, 1), 150, 148.0, 0.38,
    ),
    "TR-SAKARYA": Station(
        "TR-SAKARYA", "Sakarya", "Marmara", 40.78, 30.40,
        (4, 1), 150, 245.0, 0.31,
    ),
    "TR-IZMIR": Station(
        "TR-IZMIR", "İzmir", "Aegean", 38.42, 27.14,
        (4, 1), 150, 112.0, 0.42,
    ),
    "TR-MANISA": Station(
        "TR-MANISA", "Manisa", "Aegean", 38.62, 27.43,
        (4, 1), 150, 126.0, 0.41,
    ),
    "TR-AYDIN": Station(
        "TR-AYDIN", "Aydın", "Aegean", 37.85, 27.84,
        (4, 1), 150, 118.0, 0.43,
    ),
    "TR-DENIZLI": Station(
        "TR-DENIZLI", "Denizli", "Aegean", 37.78, 29.09,
        (4, 1), 150, 132.0, 0.40,
    ),
    "TR-MUGLA": Station(
        "TR-MUGLA", "Muğla", "Aegean", 37.22, 28.36,
        (4, 1), 150, 124.0, 0.44,
    ),
    "TR-USAK": Station(
        "TR-USAK", "Uşak", "Aegean", 38.68, 29.41,
        (4, 1), 150, 141.0, 0.39,
    ),
    "TR-AFYON": Station(
        "TR-AFYON", "Afyonkarahisar", "Aegean", 38.76, 30.54,
        (4, 1), 150, 136.0, 0.39,
    ),
    "TR-KUTAHYA": Station(
        "TR-KUTAHYA", "Kütahya", "Aegean", 39.42, 29.99,
        (4, 1), 150, 152.0, 0.38,
    ),
    "TR-ADANA": Station(
        "TR-ADANA", "Çukurova", "Mediterranean", 37.00, 35.33,
        (3, 1), 140, 162.0, 0.38,
    ),
    "TR-MERSIN": Station(
        "TR-MERSIN", "Mersin", "Mediterranean", 36.81, 34.64,
        (3, 1), 140, 148.0, 0.40,
    ),
    "TR-HATAY": Station(
        "TR-HATAY", "Hatay", "Mediterranean", 36.20, 36.16,
        (3, 1), 140, 186.0, 0.39,
    ),
    "TR-ANTALYA": Station(
        "TR-ANTALYA", "Antalya", "Mediterranean", 36.90, 30.69,
        (3, 1), 140, 138.0, 0.45,
    ),
    "TR-ISPARTA": Station(
        "TR-ISPARTA", "Isparta", "Mediterranean", 37.77, 30.55,
        (4, 1), 150, 164.0, 0.38,
    ),
    "TR-BURDUR": Station(
        "TR-BURDUR", "Burdur", "Mediterranean", 37.72, 30.29,
        (4, 1), 150, 145.0, 0.40,
    ),
    "TR-KMARAS": Station(
        "TR-KMARAS", "Kahramanmaraş", "Mediterranean", 37.58, 36.93,
        (3, 1), 140, 172.0, 0.40,
    ),
    "TR-OSMANIYE": Station(
        "TR-OSMANIYE", "Osmaniye", "Mediterranean", 37.07, 36.25,
        (3, 1), 140, 178.0, 0.39,
    ),
    "TR-KONYA": Station(
        "TR-KONYA", "Konya Plain", "Central Anatolia", 37.87, 32.48,
        (4, 1), 150, 118.0, 0.41,
    ),
    "TR-ANKARA": Station(
        "TR-ANKARA", "Ankara", "Central Anatolia", 39.93, 32.86,
        (4, 1), 150, 148.0, 0.38,
    ),
    "TR-ESKISEHIR": Station(
        "TR-ESKISEHIR", "Eskişehir", "Central Anatolia", 39.78, 30.52,
        (4, 1), 150, 134.0, 0.39,
    ),
    "TR-KAYSERI": Station(
        "TR-KAYSERI", "Kayseri", "Central Anatolia", 38.73, 35.49,
        (4, 1), 150, 142.0, 0.40,
    ),
    "TR-SIVAS": Station(
        "TR-SIVAS", "Sivas", "Central Anatolia", 39.75, 37.02,
        (4, 1), 150, 158.0, 0.38,
    ),
    "TR-YOZGAT": Station(
        "TR-YOZGAT", "Yozgat", "Central Anatolia", 39.82, 34.81,
        (4, 1), 150, 166.0, 0.37,
    ),
    "TR-AKSARAY": Station(
        "TR-AKSARAY", "Aksaray", "Central Anatolia", 38.37, 34.03,
        (4, 1), 150, 122.0, 0.42,
    ),
    "TR-NIGDE": Station(
        "TR-NIGDE", "Niğde", "Central Anatolia", 37.97, 34.68,
        (4, 1), 150, 128.0, 0.41,
    ),
    "TR-NEVSEHIR": Station(
        "TR-NEVSEHIR", "Nevşehir", "Central Anatolia", 38.62, 34.71,
        (4, 1), 150, 131.0, 0.41,
    ),
    "TR-KIRSEHIR": Station(
        "TR-KIRSEHIR", "Kırşehir", "Central Anatolia", 39.15, 34.16,
        (4, 1), 150, 139.0, 0.39,
    ),
    "TR-KARAMAN": Station(
        "TR-KARAMAN", "Karaman", "Central Anatolia", 37.18, 33.22,
        (4, 1), 150, 115.0, 0.43,
    ),
    "TR-CANKIRI": Station(
        "TR-CANKIRI", "Çankırı", "Central Anatolia", 40.60, 33.62,
        (4, 1), 150, 151.0, 0.38,
    ),
    "TR-SANLIURFA": Station(
        "TR-SANLIURFA", "Şanlıurfa", "Southeastern Anatolia", 37.16, 38.79,
        (3, 1), 140, 96.0, 0.47,
    ),
    "TR-DIYARBAKIR": Station(
        "TR-DIYARBAKIR", "Diyarbakır", "Southeastern Anatolia", 37.91, 40.24,
        (3, 1), 140, 118.0, 0.45,
    ),
    "TR-GAZIANTEP": Station(
        "TR-GAZIANTEP", "Gaziantep", "Southeastern Anatolia", 37.07, 37.38,
        (3, 1), 140, 142.0, 0.43,
    ),
    "TR-MARDIN": Station(
        "TR-MARDIN", "Mardin", "Southeastern Anatolia", 37.31, 40.74,
        (3, 1), 140, 128.0, 0.46,
    ),
    "TR-ADIYAMAN": Station(
        "TR-ADIYAMAN", "Adıyaman", "Southeastern Anatolia", 37.76, 38.28,
        (3, 1), 140, 156.0, 0.42,
    ),
    "TR-BATMAN": Station(
        "TR-BATMAN", "Batman", "Southeastern Anatolia", 37.88, 41.13,
        (3, 1), 140, 122.0, 0.46,
    ),
    "TR-SIIRT": Station(
        "TR-SIIRT", "Siirt", "Southeastern Anatolia", 37.93, 41.94,
        (3, 1), 140, 148.0, 0.44,
    ),
    "TR-KILIS": Station(
        "TR-KILIS", "Kilis", "Southeastern Anatolia", 36.72, 37.12,
        (3, 1), 140, 134.0, 0.44,
    ),
    "TR-MALATYA": Station(
        "TR-MALATYA", "Eastern Anatolia", "Eastern Anatolia", 38.36, 38.31,
        (4, 1), 150, 144.0, 0.41,
    ),
    "TR-ELAZIG": Station(
        "TR-ELAZIG", "Elazığ", "Eastern Anatolia", 38.68, 39.22,
        (4, 1), 150, 151.0, 0.40,
    ),
    "TR-ERZURUM": Station(
        "TR-ERZURUM", "Erzurum", "Eastern Anatolia", 39.90, 41.27,
        (4, 1), 150, 172.0, 0.38,
    ),
    "TR-VAN": Station(
        "TR-VAN", "Van", "Eastern Anatolia", 38.49, 43.38,
        (4, 1), 150, 138.0, 0.42,
    ),
    "TR-MUS": Station(
        "TR-MUS", "Muş", "Eastern Anatolia", 38.73, 41.49,
        (4, 1), 150, 165.0, 0.39,
    ),
    "TR-AGRI": Station(
        "TR-AGRI", "Ağrı", "Eastern Anatolia", 39.72, 43.05,
        (4, 1), 150, 158.0, 0.40,
    ),
    "TR-SAMSUN": Station(
        "TR-SAMSUN", "Samsun", "Black Sea", 41.29, 36.33,
        (4, 1), 150, 268.0, 0.29,
    ),
    "TR-TOKAT": Station(
        "TR-TOKAT", "Tokat", "Black Sea", 40.31, 36.55,
        (4, 1), 150, 186.0, 0.35,
    ),
    "TR-CORUM": Station(
        "TR-CORUM", "Çorum", "Black Sea", 40.55, 34.95,
        (4, 1), 150, 172.0, 0.36,
    ),
    "TR-AMASYA": Station(
        "TR-AMASYA", "Amasya", "Black Sea", 40.65, 35.83,
        (4, 1), 150, 178.0, 0.35,
    ),
    "TR-ORDU": Station(
        "TR-ORDU", "Ordu", "Black Sea", 40.98, 37.88,
        (4, 1), 150, 312.0, 0.27,
    ),
    "TR-TRABZON": Station(
        "TR-TRABZON", "Trabzon", "Black Sea", 41.00, 39.72,
        (4, 1), 150, 296.0, 0.28,
    ),
    "TR-DUZCE": Station(
        "TR-DUZCE", "Düzce", "Black Sea", 40.84, 31.16,
        (4, 1), 150, 252.0, 0.30,
    ),
    "TR-BOLU": Station(
        "TR-BOLU", "Bolu", "Black Sea", 40.74, 31.61,
        (4, 1), 150, 238.0, 0.31,
    ),
    "TR-KASTAMONU": Station(
        "TR-KASTAMONU", "Kastamonu", "Black Sea", 41.39, 33.78,
        (4, 1), 150, 196.0, 0.34,
    ),
}


class Drought(Peril):
    key = "drought"
    name = "Drought, on seasonal rainfall"
    index_name = "cumulative rainfall at the named station"
    unit = "mm"
    basis_risk = (
        "Moderate to high, and the highest of anything offered here. Rainfall "
        "is local: a field ten kilometres from the station can have a good "
        "season while the station records a bad one, and the policy follows "
        "the station. Distance from the station is the single largest driver "
        "of whether this cover behaves the way a buyer expects."
    )
    basis_risk_level = "high"

    # Fifteen days, and it works differently here. A dry season is not a
    # forecast, it is a thing you watch happen: by the time a farmer knows the
    # rain has not come, weeks of the window are gone and the total is already
    # low, and no waiting period short enough to sell can outlast that. So the
    # fifteen days are a sales deadline rather than a wait. The station's
    # season is a fixed range of calendar dates; sales for it close fifteen
    # days before it opens; and cover bought after the deadline is cover for
    # the next season, which starts on the day that season opens. See
    # starts_in_days and refuse_to_write below.
    waiting_days = 15.0

    # Only where there is a station with a fitted season. Derived rather than
    # declared, so adding a station in another country opens that country.
    territory = frozenset(station.country for station in STATIONS.values())

    def risk_country(self, subject: dict[str, Any]) -> str | None:
        station = STATIONS.get(str(subject.get("station", "")).upper().strip())
        return station.country if station else None

    def validate_subject(self, subject: dict[str, Any]) -> dict[str, Any]:
        station = str(subject.get("station", "")).upper().strip()
        if station not in STATIONS:
            raise ValueError(
                f"unknown station {station!r}; offered stations are "
                f"{', '.join(sorted(STATIONS))}"
            )
        distance = float(subject.get("distance_km", 0.0))
        if distance < 0 or distance > 60:
            raise ValueError(
                "the insured field must be within sixty kilometres of the "
                "station, and the distance must not be negative"
            )
        hectares = float(subject.get("hectares", 0.0))
        if hectares <= 0:
            raise ValueError("insured area must be positive")
        return {"station": station, "distance_km": distance, "hectares": hectares}

    def station(self, subject: dict[str, Any]) -> Station:
        return STATIONS[subject["station"]]

    # -- the season a policy measures, and the day sales for it close --------

    @staticmethod
    def _day(now: float | None) -> dt.date:
        import time as _time
        return dt.datetime.fromtimestamp(
            now if now is not None else _time.time(), dt.timezone.utc
        ).date()

    def window_for(self, subject: dict[str, Any], *, now: float | None = None
                   ) -> tuple[dt.date, dt.date]:
        """The season this cover would measure if it were bought now.

        The next one to open. A season already under way is never it: half its
        rain has fallen and both sides can see how much.
        """
        station = self.station(subject)
        opens = station.opens_on_or_after(self._day(now))
        return opens, opens + dt.timedelta(days=station.window_days - 1)

    def starts_in_days(self, subject: dict[str, Any], *, now: float | None = None) -> float:
        """Cover starts on the day the season opens, not the day it is bought.

        One date with one meaning, rather than a start in October and a season
        beginning in April. The sales deadline below is what keeps that date at
        least ``waiting_days`` away.
        """
        import time as _time
        opens, _ = self.window_for(subject, now=now)
        when = dt.datetime.combine(opens, dt.time(), dt.timezone.utc).timestamp()
        return max(0.0, (when - (now if now is not None else _time.time())) / 86400.0)

    def refuse_to_write(self, subject: dict[str, Any], *, now: float | None = None) -> str:
        """The sales deadline.

        Every other peril here waits out its forecast. A season cannot be
        waited out: it is a hundred and fifty days long, and a farmer standing
        in a dry June already knows what the total will be. So sales for a
        season close before it opens, which is how crop cover has always been
        sold, and a policy bought after the deadline is cover for the season
        after this one. The deadline is stated on the page and in the contract,
        with the date it falls on, so nobody meets it by surprise.
        """
        station = self.station(subject)
        opens, closes = self.window_for(subject, now=now)
        lead = (opens - self._day(now)).days
        del station
        if lead >= self.waiting_days:
            return ""
        # The only way to be here is the last few days before an opening: a
        # season already under way was rolled past by window_for, and its
        # successor is a year off.
        return (
            f"sales for the {opens:%d %B %Y} season closed on "
            f"{opens - dt.timedelta(days=int(self.waiting_days)):%d %B %Y}, "
            f"{int(self.waiting_days)} days before it opens; cover for the season "
            f"after it can be bought from {closes + dt.timedelta(days=1):%d %B %Y}"
        )

    def data_source(self, subject: dict[str, Any]) -> DataSource:
        station = self.station(subject)
        return DataSource(
            reference=f"api.meteo.example/v1/station/{station.code}/cumulative",
            field="rainfall_mm",
            unit=self.unit,
            publisher="national meteorological service, attested by validators",
            resolution="daily, with the settlement reading taken at window close",
            settlement_deadline_days=14,
            on_missing_data=(
                "If the station publishes no closing total within fourteen days "
                "of the window ending, the policy expires and the premium is "
                "returned in full. A station that goes dark must not quietly "
                "keep a farmer's money."
            ),
        )

    def default_curve(self) -> PayoutCurve:
        """Pays proportionally as rainfall falls from 80% to 40% of normal.

        Expressed as shares of normal rather than millimetres, so one structure
        reads the same at every station. The levels are converted when a policy
        is written.
        """
        return curve_from_spec(
            [(0.80, 0.00), (0.60, 0.50), (0.40, 1.00)],
            shape=Shape.RAMP,
            direction=Direction.BELOW,
        )

    def curve_in_mm(self, subject: dict[str, Any], curve: PayoutCurve) -> PayoutCurve:
        """Convert a curve expressed in shares of normal into millimetres."""
        station = self.station(subject)
        return curve_from_spec(
            [
                (point.level * station.normal_mm, point.share)
                for point in curve.breakpoints
            ],
            shape=curve.shape,
            direction=curve.direction,
        )

    def exceedance(
        self, subject: dict[str, Any], term_days: float
    ) -> Callable[[float], float]:
        """Probability that rainfall falls to or below a level, in millimetres.

        The window is fixed by the season, so a shorter term does not reduce
        the exposure: the policy either covers the season or it does not.
        """
        del term_days
        station = self.station(subject)
        shape, scale = station.shape, station.scale

        def probability(level_mm: float) -> float:
            if level_mm <= 0:
                return 0.0
            return gamma_cdf(level_mm, shape, scale)

        return probability

    def predicate(
        self, subject: dict[str, Any], curve: PayoutCurve, policy_id: str
    ) -> str:
        """Settle on the closing total, not on the running one.

        The window_closed guard is the whole difference between insurance and a
        lottery on the weather so far. A cumulative total that happens to be
        low in June says nothing about the harvest, and a policy that paid on it
        would be paying for a season that had not happened yet.
        """
        source = self.data_source(subject)
        in_mm = self.curve_in_mm(subject, curve)
        return (
            f'edge("{source.reference}").window_closed >= 1 '
            f'and edge("{source.reference}").{source.field} <= {in_mm.attachment:g}'
        )

    def describe_subject(self, subject: dict[str, Any]) -> str:
        station = self.station(subject)
        return (
            f"{subject['hectares']:g} hectares, {subject['distance_km']:g} km from "
            f"{station.name}, {station.season}"
        )

    def basis_risk_for(self, subject: dict[str, Any]) -> tuple[str, float]:
        """How much the distance from the station widens the gap.

        Rainfall correlation falls with separation. The decay used here is the
        common exponential form with a range of about thirty kilometres for
        convective summer rainfall, which is deliberately conservative.
        """
        distance = float(subject["distance_km"])
        correlation = pow(2.718281828459045, -distance / 30.0)
        if distance <= 5:
            verdict = "the field is close enough that the station is a fair proxy"
        elif distance <= 20:
            verdict = "the station is a reasonable proxy, with real seasons where it will disagree"
        else:
            verdict = (
                "at this separation the station and the field will disagree often; "
                "this cover is priced for it, but the buyer should understand it"
            )
        return verdict, correlation
