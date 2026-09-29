"""Hazard curves as the national authorities publish them. Offline only.

    python -m clause.hazard.published JP US
    python -m clause.hazard.published JP --limit 40
    python -m clause.hazard.published JP --refresh

Why this exists
---------------
The models in this directory are built from the catalogue since 1973 and
nothing else: no faults, no subduction interfaces, and a shaking calculation
of our own on top. That is a defensible way to price a country nobody has
modelled, and it is the wrong way to price one somebody has. Japan publishes
a national probabilistic hazard model, so does the United States, and where a
country does, its own figure is the one that should price the cover.

What is fetched is a hazard curve: ground motion against the annual frequency
of exceeding it, at a point. That is the same object for every publisher, so
the runtime reads one shape whatever wrote it.

Honesty about what is still ours
--------------------------------
The index this product settles on is intensity, because that is what the
shaking maps publish after an earthquake. Turning a published ground motion
into an intensity is one step, and it is a published relation rather than one
of ours: Worden, Gerstenberger, Rhoades and Wald (2012), for peak ground
velocity. Before this the chain was our event rates and our intensity
equation; after it, it is their hazard and one cited conversion.
"""

from __future__ import annotations

import json
import math
import sys
import time
import urllib.error
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterable

MODELS = Path(__file__).resolve().parent / "models"
OUT = MODELS / "published.json"
VERSION = "2026.1"
AGENT = "clause.insure hazard build (offline); contact via clause.insure"

#: Worden, Gerstenberger, Rhoades and Wald (2012), peak ground velocity to
#: modified Mercalli intensity: the relation ShakeMap itself uses to draw the
#: intensity a network reports, with the coefficients its own implementation
#: carries (shakelib.gmice.wgrw12). Three straight pieces in log velocity.
PGV_TO_MMI = ((-1.21, 4.62, 2.17), (0.53, 3.78, 1.47), (None, 2.89, 3.16))
#: The scatter the same paper reports for this direction, in intensity units.
PGV_TO_MMI_SIGMA = 0.63


def mmi_from_pgv(pgv_cm_s: float) -> float:
    """The relation itself, not clipped to the scale.

    ShakeMap clips its answer to I and X because that is the range of the
    intensity scale a person reads. Here the answer is an axis to interpolate a
    hazard curve along, and clipping it puts several of a curve's points at the
    same intensity with different frequencies, which is not a curve. So the
    line runs where the coefficients take it, and the reading of it below is
    what refuses the parts of the curve that mean nothing.
    """
    if pgv_cm_s <= 0:
        return 0.0
    log = math.log10(pgv_cm_s)
    for upper, c1, c2 in PGV_TO_MMI:
        if upper is None or log < upper:
            return c1 + c2 * log
    raise AssertionError


class Busy(Exception):
    """The publisher answered, and the answer was that it could not answer."""


def _get(url: str, *, timeout: float = 120.0, tries: int = 2) -> Any:
    """One request, retried briefly, then given up on and come back to later.

    These services answer 200 with a status of error when their own backend is
    busy, which the first version of this build read as "no curve here" and
    passed over. A place the publisher covers and the build missed is worse
    than a build that takes longer: nothing downstream can tell the two apart.

    But sitting on one place through five long backoffs is the wrong shape for
    a service having a bad afternoon: it turns a refusal rate into a wall. So
    a place is tried twice, then left for the next pass. ``build`` keeps what
    it got and skips it next time, so passes converge instead of restarting.
    """
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as reply:
                data = json.loads(reply.read())
            if isinstance(data, dict) and data.get("status") == "error":
                raise Busy(str(data.get("response") or "")[:120])
            return data
        except (urllib.error.URLError, TimeoutError, Busy):
            if attempt == tries - 1:
                raise
            time.sleep(5 * (attempt + 1))
    raise AssertionError


# -- the United States -------------------------------------------------------

#: The resolved revisions, not the `conus-2023` style aliases. An alias answers
#: with a 302 whose Location downgrades to http, which no sane client follows,
#: and naming the revision also puts it in the model file: a hazard curve
#: should say which revision of which national model drew it.
#:
#: There are three, because the United States is not one piece of ground. CONUS
#: stops at the border of the lower forty eight, so this build asked it about
#: Anchorage and was told there is no curve there: one of the most seismic
#: cities in the world, four hundred kilometres from the 1964 rupture, and the
#: USGS has published a model for it since 2007. Honolulu, the largest American
#: place after the CONUS two hundred, came back the same way. Each model is
#: asked about the ground it covers, and each curve carries the name of the one
#: that drew it, because "the national model" is three different models and a
#: buyer reading the source line should see which.
USGS = "https://earthquake.usgs.gov/ws/nshmp/{model}/dynamic/hazard/{lon}/{lat}/{vs30}"
#: Revision, printed name, and the box of ground it answers for: south, north,
#: west, east. The boxes are the publishers' own footprints rounded outwards,
#: and every American place this product offers falls in exactly one of them,
#: which is checked in the tests rather than assumed here. A place in none is
#: named as missed rather than asked of a model that does not cover it.
USGS_MODELS = (
    ("alaska-2023.R1", "Alaska 2023 R1", (48.0, 72.0, -180.0, -129.0)),
    ("hawaii-2021.R1", "Hawaii 2021 R1", (18.0, 23.5, -161.5, -154.0)),
    ("conus-2023.R2", "CONUS 2023 R2", (24.0, 50.0, -125.5, -66.0)),
)


def usgs_model(latitude: float, longitude: float) -> tuple[str, str] | None:
    """Which of the three national models covers a point, and what it is called."""
    for revision, name, (south, north, west, east) in USGS_MODELS:
        if south <= latitude <= north and west <= longitude <= east:
            return revision, name
    return None


def usgs_curve(latitude: float, longitude: float, *, vs30: int = 760) -> list[list[float]] | None:
    """The national model's curve at a point: PGV against annual rate.

    Soil is left at the reference 760 m/s because the buyer's own site class
    is not known, and saying so is better than assuming a softer one and
    quietly pricing every address as though it stood on it.
    """
    chosen = usgs_model(latitude, longitude)
    if chosen is None:
        return None
    data = _get(USGS.format(model=chosen[0], lon=round(longitude, 4),
                            lat=round(latitude, 4), vs30=vs30))
    for curve in (data.get("response") or {}).get("hazardCurves", []):
        if (curve.get("imt") or {}).get("value") != "PGV":
            continue
        for part in curve.get("data", []):
            if part.get("component") != "Total":
                continue
            values = part.get("values") or {}
            xs, ys = values.get("xs") or [], values.get("ys") or []
            # USGS gives PGV in cm/s already for the PGV intensity measure.
            return [[float(x), float(y)] for x, y in zip(xs, ys) if y > 0]
    return None


# -- Japan -------------------------------------------------------------------

JSHIS = ("https://www.j-shis.bosai.go.jp/map/api/pshm/Y2023/AVR/TTL_MTTL/"
         "meshinfo.geojson?position={lon},{lat}&epsg=4301")
#: Surface velocity at six exceedance probabilities, which is how J-SHIS
#: publishes the strong end of its national model: the probability of
#: exceedance in thirty or fifty years, and the velocity that goes with it.
JSHIS_VELOCITIES = (("T30_P03", 0.03, 30.0), ("T30_P06", 0.06, 30.0),
                    ("T50_P02", 0.02, 50.0), ("T50_P05", 0.05, 50.0),
                    ("T50_P10", 0.10, 50.0), ("T50_P39", 0.39, 50.0))
#: And the probability in thirty years of reaching a JMA intensity, which is
#: how it publishes the frequent end. These are the levels a policy is actually
#: written at: at Osaka the velocities above start at a return period of 101
#: years, and these reach 13.
JSHIS_INTENSITIES = (("T30_I45_PS", 4.5), ("T30_I50_PS", 5.0),
                     ("T30_I55_PS", 5.5), ("T30_I60_PS", 6.0))


def _rate(probability: float, years: float) -> float:
    return -math.log(1.0 - probability) / years


def _velocity_of(pairs: list[tuple[float, float]], intensity: float) -> float | None:
    """A JMA intensity as a velocity, by the site's own published pairs.

    J-SHIS gives both a velocity and a JMA intensity at each probability level,
    which is the same hazard described twice, so the pairs are that mesh's own
    relation between the two. Converting one of its intensity thresholds with
    them needs no general JMA to intensity rule, which is the step that cannot
    be settled from outside and which an earlier version of this got backwards.
    Straight in log velocity, and down the end slope just past either end.
    """
    # One intensity can carry two velocities: at Osaka J-SHIS answers 5.9 with
    # both 71.7 and 75.9, from a thirty year and a fifty year level. They are
    # the same intensity, so they are one point, and leaving them as two put a
    # zero in the denominator below and ended a two hour build at its 970th
    # place.
    together: dict[float, list[float]] = {}
    for intensity_, velocity_ in pairs:
        together.setdefault(intensity_, []).append(math.log10(velocity_))
    xs = sorted(together)
    ys = [sum(together[x]) / len(together[x]) for x in xs]
    if len(xs) < 2:
        return None
    if intensity <= xs[0]:
        slope = (ys[1] - ys[0]) / (xs[1] - xs[0])
        if xs[0] - intensity > 1.5:
            return None
        return 10 ** (ys[0] + slope * (intensity - xs[0]))
    if intensity >= xs[-1]:
        slope = (ys[-1] - ys[-2]) / (xs[-1] - xs[-2])
        if intensity - xs[-1] > 1.5:
            return None
        return 10 ** (ys[-1] + slope * (intensity - xs[-1]))
    for i in range(1, len(xs)):
        if intensity <= xs[i]:
            part = (intensity - xs[i - 1]) / (xs[i] - xs[i - 1])
            return 10 ** (ys[i - 1] + part * (ys[i] - ys[i - 1]))
    return None


def jshis_curve(latitude: float, longitude: float) -> list[list[float]] | None:
    data = _get(JSHIS.format(lon=round(longitude, 5), lat=round(latitude, 5)))
    features = data.get("features") or []
    if not features:
        return None
    said = features[0].get("properties") or {}

    points: dict[float, float] = {}
    pairs: list[tuple[float, float]] = []
    for key, probability, years in JSHIS_VELOCITIES:
        if key + "_SV" not in said:
            continue
        velocity = float(said[key + "_SV"])
        points[velocity] = _rate(probability, years)
        if key + "_SI" in said:
            pairs.append((float(said[key + "_SI"]), velocity))
    pairs = sorted(set(pairs))

    for key, intensity in JSHIS_INTENSITIES:
        if key not in said:
            continue
        probability = float(said[key])
        if not 0.0 < probability < 1.0:
            continue
        velocity = _velocity_of(pairs, intensity)
        if velocity is None or velocity <= 0:
            continue
        # A velocity already published keeps its own rate: that one came
        # straight from the model and this one came through a conversion.
        points.setdefault(round(velocity, 4), _rate(probability, 30.0))

    # A hazard curve falls. Where the two families cross and disagree, the
    # stronger shaking cannot be the more frequent, so the rate is held down,
    # and a point that ends up at the rate of the one before it is dropped: at
    # Tokyo an intensity threshold converts to within a fifth of a percent of a
    # published velocity, because the conversion goes through the very pairs
    # that velocity belongs to, and the two are one point measured twice. Two
    # points at one rate is a flat step in a curve the map is read along.
    out: list[list[float]] = []
    last = float("inf")
    for velocity in sorted(points):
        rate = min(points[velocity], last)
        if rate <= 0 or rate >= last:
            continue
        out.append([round(velocity, 4), rate])
        last = rate
    return out if len(out) >= 2 else None


SOURCES: dict[str, dict[str, Any]] = {
    "US": {"fetch": usgs_curve, "pause": 3.0, "names": usgs_model,
           "publisher": "USGS National Seismic Hazard Model",
           "reference": "https://earthquake.usgs.gov/ws/nshmp/",
           "measure": "PGV, cm/s, at a reference site of 760 m/s"},
    "JP": {"fetch": jshis_curve, "pause": 0.5,
           "publisher": "NIED J-SHIS, national probabilistic model Y2023",
           "reference": "https://www.j-shis.bosai.go.jp/",
           "measure": "PGV, cm/s, at the surface"},
}


def places_of(code: str) -> list[tuple[str, float, float, int]]:
    """The places this product offers in a country, largest first.

    The same list the interface searches, so what is fetched is what a buyer
    can actually choose rather than a grid of ocean.
    """
    data = json.loads((MODELS / "places.json").read_text(encoding="utf-8"))
    out = []
    seen: set[tuple[float, float]] = set()
    for row in data.get("places", []):
        if len(row) < 7 or row[2] != code:
            continue
        latitude, longitude = float(row[4]), float(row[5])
        # One place per coordinate. Japan offers Choshi and Hasaki at the same
        # point, and Furano twice under two spellings, so the build fetched two
        # identical curves and the model file carried both. Harmless to a search
        # that works in kilometres, and still two rows where there is one place.
        key = (round(latitude, 4), round(longitude, 4))
        if key in seen:
            continue
        seen.add(key)
        out.append((str(row[0]), latitude, longitude, int(row[6])))
    out.sort(key=lambda r: -r[3])
    return out


def build(code: str, *, limit: int | None = None,
          keep: list[dict[str, Any]] | None = None,
          save: Callable[[list[dict[str, Any]], list[str]], None] | None = None
          ) -> dict[str, Any]:
    """Fetch a country's published curves, keeping what an earlier run got.

    These are public services with their own load, and asking one for two
    hundred points takes as long as it takes. A run that is interrupted, or
    that a publisher's own backend refuses half way through, should cost only
    the places it did not reach: ``keep`` is the previous run's points, and a
    place already in it is not asked for again -- a place being a coordinate,
    which is unique here, rather than a name, which is not.
    """
    source = SOURCES[code]
    fetch: Callable[..., Any] = source["fetch"]
    # Where a country is covered by more than one published model, each point
    # carries the name of the one that answered for it. A point fetched before
    # this build learned that is stamped from its coordinate rather than asked
    # for again: which model covers a place is arithmetic, not a request.
    names: Callable[..., Any] | None = source.get("names")
    rows: list[dict[str, Any]] = list(keep or [])
    if names is not None:
        for row in rows:
            if not row.get("model"):
                found = names(float(row["latitude"]), float(row["longitude"]))
                if found:
                    row["model"] = found[1]
    # A place is its coordinate, not its name. The United States offers eight
    # Springfields and five Columbuses -- Ohio at nine hundred thousand and
    # Mississippi at twenty three -- and Japan two Sendais, and keying the
    # already-fetched set by name meant the first of each pair was fetched and
    # every other one silently skipped for ever, counted as done and never
    # asked for. Three hundred and eight repeated American names cover seven
    # hundred and sixty nine of the places this product offers.
    #
    # places_of already guarantees one place per coordinate, so the coordinate
    # is a key and the name is not.
    def where(latitude: float, longitude: float) -> tuple[float, float]:
        return (round(float(latitude), 4), round(float(longitude), 4))

    already = {where(row["latitude"], row["longitude"]) for row in rows}
    missed: list[str] = []
    places = places_of(code)
    if limit:
        places = places[:limit]
    wanted = {where(la, lo) for _n, la, lo, _p in places}
    rows = [row for row in rows if where(row["latitude"], row["longitude"]) in wanted]
    for name, latitude, longitude, _people in places:
        if where(latitude, longitude) in already:
            continue
        try:
            curve = fetch(latitude, longitude)
        except (urllib.error.URLError, TimeoutError, Busy) as error:
            print(f"  {code} {name}: {type(error).__name__} {error}", file=sys.stderr)
            missed.append(name)
            continue
        except Exception as error:      # noqa: BLE001 - one bad mesh, not the run
            # A publisher's answer is data, and data surprises. Whatever one
            # place's figures do to the arithmetic, the other twelve hundred
            # have already been fetched and the run is worth finishing: the
            # place is named as missed and the build carries on.
            print(f"  {code} {name}: {type(error).__name__} {error}", file=sys.stderr)
            missed.append(name)
            continue
        if not curve:
            print(f"  {code} {name}: no curve", file=sys.stderr)
            missed.append(name)
            continue
        row = {"name": name, "latitude": round(latitude, 4),
               "longitude": round(longitude, 4), "curve": curve}
        if names is not None:
            found = names(latitude, longitude)
            if found:
                row["model"] = found[1]
        rows.append(row)
        print(f"  {code} {name}: {len(curve)} points", flush=True)
        if save is not None and len(rows) % 10 == 0:
            # This run's misses, not the last one's. The partial save used to
            # carry the missed list frozen at the start of the run, so a build
            # killed half way wrote a file that named no gaps at all: four
            # interrupted American passes in a row shipped as models with
            # nothing missing, while the log showed a hundred refusals. The
            # test that holds the missed list under a fiftieth of the points
            # could not see any of it.
            save(rows, missed)
        time.sleep(source["pause"])
    return _record(code, rows, missed)


def _record(code: str, rows: list[dict[str, Any]], missed: list[str]) -> dict[str, Any]:
    """A country's model file entry. Every write goes through here.

    A build interrupted half way used to leave a country with nothing but its
    points, which the runtime read as a model with no publisher. A model file
    should never hold a state nothing can read, so the partial saves and the
    final one write the same shape.
    """
    source = SOURCES[code]
    return {
        "code": code, "version": VERSION, "built": time.strftime("%Y-%m-%d"),
        "publisher": source["publisher"], "reference": source["reference"],
        "measure": source["measure"],
        "conversion": ("Worden, Gerstenberger, Rhoades and Wald (2012), "
                       "peak ground velocity to modified Mercalli intensity"),
        # Named, not passed over: a place the publisher covers and this build
        # could not read is a gap somebody should be able to see.
        "points": rows, "missed": missed,
    }


def _write(doc: dict[str, Any]) -> None:
    """Replace the model file in one step.

    A build that saves as it goes rewrites this file while a server, or a test
    run, is reading it, and a reader that catches it half written sees a model
    with no publisher or no curves at all. Writing beside it and renaming makes
    every reader see either the old file or the new one.
    """
    beside = OUT.with_suffix(".json.part")
    beside.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    beside.replace(OUT)


def main(argv: list[str]) -> int:
    # An option's value is not a country. Reading the arguments in one pass,
    # rather than picking out the ones without a dash and separately hunting
    # for --limit, is what stops "--limit 250" asking for a country called 250.
    wanted: list[str] = []
    limit: int | None = None
    # A country already fetched is skipped, which is what makes a long build
    # resumable. When the reader itself changes, as it did when J-SHIS turned
    # out to publish the frequent end of its curve as well, the stored points
    # are the old shape and skipping them keeps the old answer.
    refresh = False
    rest = list(argv)
    while rest:
        arg = rest.pop(0)
        if arg == "--limit":
            if not rest:
                print("--limit wants a number after it", file=sys.stderr)
                return 2
            limit = int(rest.pop(0))
        elif arg == "--refresh":
            refresh = True
        elif arg.startswith("-"):
            print(f"no such option: {arg}", file=sys.stderr)
            return 2
        else:
            wanted.append(arg.upper())
    wanted = wanted or list(SOURCES)
    have = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    for code in wanted:
        if code not in SOURCES:
            print(f"no published model wired for {code}", file=sys.stderr)
            continue
        so_far = {} if refresh else dict(have.get(code) or {})

        def save(rows: list[dict[str, Any]], missed: list[str],
                 _code: str = code) -> None:
            have[_code] = _record(_code, rows, missed)
            _write(have)

        have[code] = build(code, limit=limit, keep=so_far.get("points"), save=save)
        _write(have)
        print(f"{code}: {len(have[code]['points'])} places -> {OUT.name}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


# ---------------------------------------------------------------------------
# Reading, at runtime
# ---------------------------------------------------------------------------
#
# What the build wrote is ground motion against annual frequency at a list of
# places. What the runtime wants is intensity against annual frequency at one
# address. The conversion is Worden 2012 above; the rest is arithmetic.

#: The weakest shaking worth carrying. Below this the curve describes ground
#: motion nobody insures against and no policy attaches to, and the lowest of
#: these published points sit where the relation above stops meaning anything.
LEAST_INTENSITY = 3.0

#: How far a published point may be from an address and still describe it.
#: A hazard curve is drawn for a place, not a plot, and the national grids
#: behind these figures are coarser than this anyway.
NEAR_KM = 60.0


@lru_cache(maxsize=1)
def curves() -> tuple[dict[str, Any], ...]:
    """Every published point as intensity against annual rate, largest first."""
    if not OUT.exists():
        return ()
    doc = json.loads(OUT.read_text(encoding="utf-8"))
    out: list[dict[str, Any]] = []
    for code, country in sorted(doc.items()):
        for row in country.get("points", []):
            curve = _read_curve(row.get("curve", []))
            if len(curve) < 2:
                continue
            out.append({
                "country": code, "name": row["name"],
                "latitude": float(row["latitude"]), "longitude": float(row["longitude"]),
                "curve": curve, "publisher": _said(country, row),
                "reference": country.get("reference", ""),
                "measure": country.get("measure", ""),
                "conversion": country.get("conversion", ""),
                "version": country.get("version", ""),
            })
    return tuple(out)


def _said(country: dict[str, Any], row: dict[str, Any]) -> str:
    """Who published this one curve.

    The country names the model family and the point names the revision that
    drew it, because the United States is three models under one name and a
    source line that says only the family tells a buyer in Anchorage that their
    price came from a model of the lower forty eight.
    """
    said = str(country.get("publisher", ""))
    model = str(row.get("model") or "")
    return f"{said}, {model}" if said and model else (said or model)


def _read_curve(stored: Any) -> tuple[tuple[float, float], ...]:
    """A stored curve as the runtime wants it: intensity, falling, no flat steps.

    Hygiene at reading rather than at building, so the file keeps everything the
    publisher said and a file built by an older version is cleaned all the same.
    Two points at the same rate are a flat step in the axis the site term map is
    read along, and they happen honestly: at Tokyo an intensity threshold
    converts to within a fifth of a percent of a published velocity, because the
    conversion runs through the very pairs that velocity belongs to. They are one
    point measured twice.
    """
    out: list[tuple[float, float]] = []
    last = float("inf")
    for level, rate in sorted((mmi_from_pgv(float(x)), float(y)) for x, y in stored
                              if float(y) > 0 and mmi_from_pgv(float(x)) >= LEAST_INTENSITY):
        if rate >= last:
            continue
        out.append((level, rate))
        last = rate
    return tuple(out)


def rate_at(curve: tuple[tuple[float, float], ...], level: float) -> float:
    """The published annual rate of shaking at or above an intensity.

    Straight between the published points in log rate, and down the last slope
    beyond the strongest of them, which is where a policy's higher trigger
    usually sits. Extrapolating a hazard curve is a real assumption, so it is
    made the one way that cannot invent hazard: the curve's own slope.
    """
    if not curve:
        return 0.0
    if level <= curve[0][0]:
        return curve[0][1]
    for i in range(1, len(curve)):
        x0, y0 = curve[i - 1]
        x1, y1 = curve[i]
        if level <= x1:
            if x1 <= x0 or y0 <= 0 or y1 <= 0:
                return y1
            part = (level - x0) / (x1 - x0)
            return math.exp(math.log(y0) + part * (math.log(y1) - math.log(y0)))
    x0, y0 = curve[-2]
    x1, y1 = curve[-1]
    if x1 <= x0 or y0 <= 0 or y1 <= 0:
        return y1
    slope = (math.log(y1) - math.log(y0)) / (x1 - x0)
    return math.exp(math.log(y1) + slope * (level - x1))


@lru_cache(maxsize=4096)
def nearest(latitude: float, longitude: float, *, within_km: float = NEAR_KM
            ) -> dict[str, Any] | None:
    """The published curve closest to an address, if one is close enough."""
    from .model import haversine_km

    best, best_km = None, within_km
    for point in curves():
        km = haversine_km(latitude, longitude, point["latitude"], point["longitude"])
        if km <= best_km:
            best, best_km = point, km
    if best is None:
        return None
    return dict(best, distance_km=round(best_km, 1))
