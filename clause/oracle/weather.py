"""Daily weather, from the reanalyses that publish it.

Earthquake has three agencies that each measured the same ground moving.
Weather does not work that way at a point: outside a national network's own
station list there is no second instrument at the address, and what is
published instead is a model's estimate for a cell containing it. So the
honest second reading here is a second *model*, not a second thermometer, and
the spread between them is a real measure of how much the number could have
been otherwise.

That is weaker than three seismic networks and it is said plainly rather than
dressed up. It is also the exact failure the Paris Charles de Gaulle station
showed in April 2026: a single instrument with money on it, tampered with by
hand, reading four degrees high and agreeing with nothing around it. A cover
settled on one station would have paid. A cover settled on models that
disagree would not have.

Open-Meteo serves both the archive (ERA5 and ERA5-Land, the reanalysis, final
after about five days) and the forecast endpoint's recent past. The archive is
what settles; the forecast endpoint is only ever used to see that something is
happening, never to pay.
"""

from __future__ import annotations

import datetime as dt
import json
import urllib.parse
from typing import Any, Iterable

from .observation import Observation, digest_of

ARCHIVE = "archive-api.open-meteo.com/v1/archive"
FORECAST = "api.open-meteo.com/v1/forecast"

#: What each index this protocol writes is called in Open-Meteo's daily block,
#: and the unit it comes back in. The names are theirs; the mapping is ours and
#: is the only place the two vocabularies meet.
DAILY_FIELD = {
    "rain_24h_mm": ("precipitation_sum", "mm"),
    "wind_24h_kmh": ("wind_speed_10m_max", "km/h"),
    "rainfall_mm": ("precipitation_sum", "mm"),
}

#: The models read against each other. ERA5 is the reanalysis everything else
#: is judged against; ERA5-Land runs the same atmosphere over a finer surface,
#: which is where a rainfall total at a point actually differs. Two runs of one
#: provider's pipeline, which is what there is, and the spread between them is
#: reported rather than hidden.
MODELS = ("era5", "era5_land")


def _day(text: str) -> float:
    """Midnight UTC of a yyyy-mm-dd, which is when Open-Meteo's day starts."""
    return dt.datetime.strptime(text, "%Y-%m-%d").replace(
        tzinfo=dt.timezone.utc).timestamp()


def archive_query(*, latitude: float, longitude: float, since: float,
                  until: float, index_field: str, model: str = "") -> str:
    """The archive request for one place, one window and one index."""
    daily, _ = DAILY_FIELD.get(index_field, DAILY_FIELD["rain_24h_mm"])
    terms = {
        "latitude": f"{latitude:.4f}", "longitude": f"{longitude:.4f}",
        "start_date": dt.datetime.fromtimestamp(since, dt.timezone.utc).strftime("%Y-%m-%d"),
        "end_date": dt.datetime.fromtimestamp(until, dt.timezone.utc).strftime("%Y-%m-%d"),
        "daily": daily, "timezone": "GMT",
    }
    if model:
        terms["models"] = model
    return f"{ARCHIVE}?{urllib.parse.urlencode(terms)}"


def read_openmeteo(body: bytes, url: str, *, index_field: str,
                   source: str = "", now: float | None = None) -> list[Observation]:
    """Every day in the response, as one observation each.

    One per day rather than one maximum, because which day a reading falls on
    is what decides whether it is inside the policy term and outside its
    waiting period, and a maximum over the window has thrown that away.

    A null is not a zero. Open-Meteo returns null for a day it has no value
    for, and a day with no value is a day that says nothing about the weather,
    not a day with no rain.
    """
    payload: dict[str, Any] = json.loads(body.decode("utf-8"))
    daily = payload.get("daily") or {}
    name, unit = DAILY_FIELD.get(index_field, DAILY_FIELD["rain_24h_mm"])
    days = daily.get("time") or []
    values = daily.get(name) or []
    latitude = float(payload.get("latitude", 0.0) or 0.0)
    longitude = float(payload.get("longitude", 0.0) or 0.0)
    fetched = now if now is not None else 0.0
    said = digest_of(body)
    if not source:
        source = "ERA5-Land" if "era5_land" in url else "ERA5"

    out: list[Observation] = []
    for index, when in enumerate(days):
        if index >= len(values):
            break
        value = values[index]
        if value is None:
            continue
        measured = _day(str(when))
        out.append(Observation(
            source=source, value=float(value), unit=unit,
            measured_at=measured,
            # A reanalysis day is published after the day is over, and the
            # archive's own lag is about five days. Recorded as the day's end
            # rather than guessed at, so nothing downstream reads a publication
            # time that is earlier than the measurement.
            published_at=measured + 86400,
            retrieved_at=fetched, url=url, digest=said,
            record_id=f"{source}:{when}", scale=name,
            latitude=latitude, longitude=longitude,
        ))
    return out


def largest_day(observations: Iterable[Observation]) -> list[Observation]:
    """The day with the highest value any model gives it, and every model's
    reading for that same day.

    Matching is by day rather than by proximity in time: two models describing
    the same Tuesday are describing the same weather, and the whole point of
    reading them together is to compare them on it.
    """
    seen = list(observations)
    if not seen:
        return []
    by_day: dict[float, list[Observation]] = {}
    for one in seen:
        by_day.setdefault(one.measured_at, []).append(one)
    when = max(by_day, key=lambda day: max(o.value for o in by_day[day]))
    return sorted(by_day[when], key=lambda o: o.source)
