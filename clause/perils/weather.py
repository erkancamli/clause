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
    season: str
    window_days: int
    normal_mm: float       # long run mean rainfall across the window
    variability: float     # coefficient of variation of that total

    def __post_init__(self) -> None:
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
        "April to August", 150, 186.0, 0.34,
    ),
    "TR-KIRKLARELI": Station(
        "TR-KIRKLARELI", "Kırklareli", "Thrace", 41.74, 27.22,
        "April to August", 150, 178.0, 0.35,
    ),
    "TR-TEKIRDAG": Station(
        "TR-TEKIRDAG", "Tekirdağ", "Thrace", 40.98, 27.51,
        "April to August", 150, 165.0, 0.36,
    ),
    "TR-BALIKESIR": Station(
        "TR-BALIKESIR", "Balıkesir", "Marmara", 39.65, 27.89,
        "April to August", 150, 158.0, 0.37,
    ),
    "TR-BURSA": Station(
        "TR-BURSA", "Bursa", "Marmara", 40.19, 29.06,
        "April to August", 150, 172.0, 0.35,
    ),
    "TR-CANAKKALE": Station(
        "TR-CANAKKALE", "Çanakkale", "Marmara", 40.15, 26.41,
        "April to August", 150, 148.0, 0.38,
    ),
    "TR-SAKARYA": Station(
        "TR-SAKARYA", "Sakarya", "Marmara", 40.78, 30.40,
        "April to August", 150, 245.0, 0.31,
    ),
    "TR-IZMIR": Station(
        "TR-IZMIR", "İzmir", "Aegean", 38.42, 27.14,
        "April to August", 150, 112.0, 0.42,
    ),
    "TR-MANISA": Station(
        "TR-MANISA", "Manisa", "Aegean", 38.62, 27.43,
        "April to August", 150, 126.0, 0.41,
    ),
    "TR-AYDIN": Station(
        "TR-AYDIN", "Aydın", "Aegean", 37.85, 27.84,
        "April to August", 150, 118.0, 0.43,
    ),
    "TR-DENIZLI": Station(
        "TR-DENIZLI", "Denizli", "Aegean", 37.78, 29.09,
        "April to August", 150, 132.0, 0.40,
    ),
    "TR-MUGLA": Station(
        "TR-MUGLA", "Muğla", "Aegean", 37.22, 28.36,
        "April to August", 150, 124.0, 0.44,
    ),
    "TR-USAK": Station(
        "TR-USAK", "Uşak", "Aegean", 38.68, 29.41,
        "April to August", 150, 141.0, 0.39,
    ),
    "TR-AFYON": Station(
        "TR-AFYON", "Afyonkarahisar", "Aegean", 38.76, 30.54,
        "April to August", 150, 136.0, 0.39,
    ),
    "TR-KUTAHYA": Station(
        "TR-KUTAHYA", "Kütahya", "Aegean", 39.42, 29.99,
        "April to August", 150, 152.0, 0.38,
    ),
    "TR-ADANA": Station(
        "TR-ADANA", "Çukurova", "Mediterranean", 37.00, 35.33,
        "March to July", 140, 162.0, 0.38,
    ),
    "TR-MERSIN": Station(
        "TR-MERSIN", "Mersin", "Mediterranean", 36.81, 34.64,
        "March to July", 140, 148.0, 0.40,
    ),
    "TR-HATAY": Station(
        "TR-HATAY", "Hatay", "Mediterranean", 36.20, 36.16,
        "March to July", 140, 186.0, 0.39,
    ),
    "TR-ANTALYA": Station(
        "TR-ANTALYA", "Antalya", "Mediterranean", 36.90, 30.69,
        "March to July", 140, 138.0, 0.45,
    ),
    "TR-ISPARTA": Station(
        "TR-ISPARTA", "Isparta", "Mediterranean", 37.77, 30.55,
        "April to August", 150, 164.0, 0.38,
    ),
    "TR-BURDUR": Station(
        "TR-BURDUR", "Burdur", "Mediterranean", 37.72, 30.29,
        "April to August", 150, 145.0, 0.40,
    ),
    "TR-KMARAS": Station(
        "TR-KMARAS", "Kahramanmaraş", "Mediterranean", 37.58, 36.93,
        "March to July", 140, 172.0, 0.40,
    ),
    "TR-OSMANIYE": Station(
        "TR-OSMANIYE", "Osmaniye", "Mediterranean", 37.07, 36.25,
        "March to July", 140, 178.0, 0.39,
    ),
    "TR-KONYA": Station(
        "TR-KONYA", "Konya Plain", "Central Anatolia", 37.87, 32.48,
        "April to August", 150, 118.0, 0.41,
    ),
    "TR-ANKARA": Station(
        "TR-ANKARA", "Ankara", "Central Anatolia", 39.93, 32.86,
        "April to August", 150, 148.0, 0.38,
    ),
    "TR-ESKISEHIR": Station(
        "TR-ESKISEHIR", "Eskişehir", "Central Anatolia", 39.78, 30.52,
        "April to August", 150, 134.0, 0.39,
    ),
    "TR-KAYSERI": Station(
        "TR-KAYSERI", "Kayseri", "Central Anatolia", 38.73, 35.49,
        "April to August", 150, 142.0, 0.40,
    ),
    "TR-SIVAS": Station(
        "TR-SIVAS", "Sivas", "Central Anatolia", 39.75, 37.02,
        "April to August", 150, 158.0, 0.38,
    ),
    "TR-YOZGAT": Station(
        "TR-YOZGAT", "Yozgat", "Central Anatolia", 39.82, 34.81,
        "April to August", 150, 166.0, 0.37,
    ),
    "TR-AKSARAY": Station(
        "TR-AKSARAY", "Aksaray", "Central Anatolia", 38.37, 34.03,
        "April to August", 150, 122.0, 0.42,
    ),
    "TR-NIGDE": Station(
        "TR-NIGDE", "Niğde", "Central Anatolia", 37.97, 34.68,
        "April to August", 150, 128.0, 0.41,
    ),
    "TR-NEVSEHIR": Station(
        "TR-NEVSEHIR", "Nevşehir", "Central Anatolia", 38.62, 34.71,
        "April to August", 150, 131.0, 0.41,
    ),
    "TR-KIRSEHIR": Station(
        "TR-KIRSEHIR", "Kırşehir", "Central Anatolia", 39.15, 34.16,
        "April to August", 150, 139.0, 0.39,
    ),
    "TR-KARAMAN": Station(
        "TR-KARAMAN", "Karaman", "Central Anatolia", 37.18, 33.22,
        "April to August", 150, 115.0, 0.43,
    ),
    "TR-CANKIRI": Station(
        "TR-CANKIRI", "Çankırı", "Central Anatolia", 40.60, 33.62,
        "April to August", 150, 151.0, 0.38,
    ),
    "TR-SANLIURFA": Station(
        "TR-SANLIURFA", "Şanlıurfa", "Southeastern Anatolia", 37.16, 38.79,
        "March to July", 140, 96.0, 0.47,
    ),
    "TR-DIYARBAKIR": Station(
        "TR-DIYARBAKIR", "Diyarbakır", "Southeastern Anatolia", 37.91, 40.24,
        "March to July", 140, 118.0, 0.45,
    ),
    "TR-GAZIANTEP": Station(
        "TR-GAZIANTEP", "Gaziantep", "Southeastern Anatolia", 37.07, 37.38,
        "March to July", 140, 142.0, 0.43,
    ),
    "TR-MARDIN": Station(
        "TR-MARDIN", "Mardin", "Southeastern Anatolia", 37.31, 40.74,
        "March to July", 140, 128.0, 0.46,
    ),
    "TR-ADIYAMAN": Station(
        "TR-ADIYAMAN", "Adıyaman", "Southeastern Anatolia", 37.76, 38.28,
        "March to July", 140, 156.0, 0.42,
    ),
    "TR-BATMAN": Station(
        "TR-BATMAN", "Batman", "Southeastern Anatolia", 37.88, 41.13,
        "March to July", 140, 122.0, 0.46,
    ),
    "TR-SIIRT": Station(
        "TR-SIIRT", "Siirt", "Southeastern Anatolia", 37.93, 41.94,
        "March to July", 140, 148.0, 0.44,
    ),
    "TR-KILIS": Station(
        "TR-KILIS", "Kilis", "Southeastern Anatolia", 36.72, 37.12,
        "March to July", 140, 134.0, 0.44,
    ),
    "TR-MALATYA": Station(
        "TR-MALATYA", "Eastern Anatolia", "Eastern Anatolia", 38.36, 38.31,
        "April to August", 150, 144.0, 0.41,
    ),
    "TR-ELAZIG": Station(
        "TR-ELAZIG", "Elazığ", "Eastern Anatolia", 38.68, 39.22,
        "April to August", 150, 151.0, 0.40,
    ),
    "TR-ERZURUM": Station(
        "TR-ERZURUM", "Erzurum", "Eastern Anatolia", 39.90, 41.27,
        "April to August", 150, 172.0, 0.38,
    ),
    "TR-VAN": Station(
        "TR-VAN", "Van", "Eastern Anatolia", 38.49, 43.38,
        "April to August", 150, 138.0, 0.42,
    ),
    "TR-MUS": Station(
        "TR-MUS", "Muş", "Eastern Anatolia", 38.73, 41.49,
        "April to August", 150, 165.0, 0.39,
    ),
    "TR-AGRI": Station(
        "TR-AGRI", "Ağrı", "Eastern Anatolia", 39.72, 43.05,
        "April to August", 150, 158.0, 0.40,
    ),
    "TR-SAMSUN": Station(
        "TR-SAMSUN", "Samsun", "Black Sea", 41.29, 36.33,
        "April to August", 150, 268.0, 0.29,
    ),
    "TR-TOKAT": Station(
        "TR-TOKAT", "Tokat", "Black Sea", 40.31, 36.55,
        "April to August", 150, 186.0, 0.35,
    ),
    "TR-CORUM": Station(
        "TR-CORUM", "Çorum", "Black Sea", 40.55, 34.95,
        "April to August", 150, 172.0, 0.36,
    ),
    "TR-AMASYA": Station(
        "TR-AMASYA", "Amasya", "Black Sea", 40.65, 35.83,
        "April to August", 150, 178.0, 0.35,
    ),
    "TR-ORDU": Station(
        "TR-ORDU", "Ordu", "Black Sea", 40.98, 37.88,
        "April to August", 150, 312.0, 0.27,
    ),
    "TR-TRABZON": Station(
        "TR-TRABZON", "Trabzon", "Black Sea", 41.00, 39.72,
        "April to August", 150, 296.0, 0.28,
    ),
    "TR-DUZCE": Station(
        "TR-DUZCE", "Düzce", "Black Sea", 40.84, 31.16,
        "April to August", 150, 252.0, 0.30,
    ),
    "TR-BOLU": Station(
        "TR-BOLU", "Bolu", "Black Sea", 40.74, 31.61,
        "April to August", 150, 238.0, 0.31,
    ),
    "TR-KASTAMONU": Station(
        "TR-KASTAMONU", "Kastamonu", "Black Sea", 41.39, 33.78,
        "April to August", 150, 196.0, 0.34,
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
