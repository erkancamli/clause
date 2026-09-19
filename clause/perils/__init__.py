"""The insurable perils Clause offers."""

from .base import (
    Breakpoint,
    DataSource,
    Direction,
    PayoutCurve,
    Peril,
    Shape,
    curve_from_spec,
)
from .flight import FlightDelay, ROUTES
from .quake import Earthquake, LOCATIONS, ZONES
from .weather import Drought, STATIONS
from .vehicle import VehicleFlood
from .storm import Storm

# One instance each: perils are stateless, and everything that varies between
# policies travels in the subject.
FLIGHT_DELAY = FlightDelay()
DROUGHT = Drought()
EARTHQUAKE = Earthquake()
VEHICLE_FLOOD = VehicleFlood()
STORM = Storm()

REGISTRY: dict[str, Peril] = {
    FLIGHT_DELAY.key: FLIGHT_DELAY,
    DROUGHT.key: DROUGHT,
    EARTHQUAKE.key: EARTHQUAKE,
    VEHICLE_FLOOD.key: VEHICLE_FLOOD,
    STORM.key: STORM,
}


def get_peril(key: str) -> Peril:
    """Look up a peril, with an error that names the alternatives."""
    try:
        return REGISTRY[key]
    except KeyError:
        raise ValueError(
            f"unknown peril {key!r}; offered perils are {', '.join(sorted(REGISTRY))}"
        ) from None


__all__ = [
    "Breakpoint",
    "DataSource",
    "Direction",
    "PayoutCurve",
    "Peril",
    "Shape",
    "curve_from_spec",
    "FlightDelay",
    "Drought",
    "Earthquake",
    "Storm",
    "VehicleFlood",
    "FLIGHT_DELAY",
    "DROUGHT",
    "EARTHQUAKE",
    "VEHICLE_FLOOD",
    "STORM",
    "REGISTRY",
    "get_peril",
    "ROUTES",
    "STATIONS",
    "LOCATIONS",
    "ZONES",
]
