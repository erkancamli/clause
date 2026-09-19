"""Build a country's earthquake model from the catalogue. Offline only.

    python -m clause.hazard.build            every region
    python -m clause.hazard.build JP CL      some of them

Needs numpy, which the protocol's server does not: the server reads the files
this writes, with nothing but the standard library. Install the build
requirements with ``pip install -r requirements-build.txt``.

The method, in the order it runs
--------------------------------
1.  Decluster. Gardner and Knopoff (1974) windows in time and distance around
    every event, largest first. What survives is the mainshocks. Rates are then
    rates of independent earthquakes, which is what a Poisson model of "at least
    one event in the term" assumes.
2.  Completeness and size. The magnitude of completeness by maximum curvature
    plus 0.2, on the modern part of the record. The b value by the Aki and Utsu
    maximum likelihood estimator above it, bounded to what nature shows.
3.  How many. The yearly rate of mainshocks of magnitude 5 or more in the whole
    region, counted over every year since 1973, which is when the global
    catalogue became complete at that size.
4.  Where. Mainshocks above completeness since 1990 are placed on a 0.1 degree
    grid and smoothed with a Gaussian kernel of 20 kilometres. A floor of two
    per cent of the region's rate is spread evenly, so no cell is ever priced
    at exactly zero, which no seismologist would defend for anywhere.
5.  How large at most. The largest magnitude in the record plus half a unit,
    capped at 9.5.

Every number the method chose is written into the model file next to the
rates, so the model card can be regenerated from the file alone.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import math
import sys
from pathlib import Path

try:
    import numpy as np
except ImportError as error:  # pragma: no cover
    raise SystemExit("the hazard build needs numpy: pip install -r requirements-build.txt") from error

from .regions import REGIONS, Region
from .sources import fetch_catalogue, fetch_outlines, fetch_places

VERSION = "2026.1"
GRID_STEP = 0.1
KERNEL_KM = 20.0
FLOOR_SHARE = 0.02
REFERENCE_MAGNITUDE = 5.0
COMPLETE_SINCE = 1973          # for magnitude 5 and above, globally
SPATIAL_SINCE = 1990           # for the smaller events that place the rate
KM_PER_DEGREE = 111.195

ROOT = Path(__file__).resolve().parent
MODELS = ROOT / "models"
CACHE = ROOT.parent.parent / "hazard_build" / "raw"


def year_of(timestamp: float) -> float:
    return dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).year + (
        dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).timetuple().tm_yday / 365.25)


# ---------------------------------------------------------------------------
# 1. Declustering
# ---------------------------------------------------------------------------


def gk_window(magnitude: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Gardner and Knopoff: days and kilometres an event's aftershocks occupy."""
    days = np.where(magnitude >= 6.5,
                    10 ** (0.032 * magnitude + 2.7389),
                    10 ** (0.5409 * magnitude - 0.547))
    km = 10 ** (0.1238 * magnitude + 0.983)
    return days, km


def decluster(events: list[dict]) -> np.ndarray:
    """A mask of the events that are mainshocks."""
    if not events:
        return np.zeros(0, dtype=bool)
    t = np.array([e["time"] for e in events]) / 86400.0
    lat = np.radians([e["latitude"] for e in events])
    lon = np.radians([e["longitude"] for e in events])
    mag = np.array([e["magnitude"] for e in events])
    order_t = np.argsort(t)
    t_sorted = t[order_t]
    days, km = gk_window(mag)
    dependent = np.zeros(len(events), dtype=bool)
    for i in np.argsort(-mag, kind="stable"):
        if dependent[i]:
            continue
        lo = np.searchsorted(t_sorted, t[i] - days[i] * 0.1)   # a short foreshock window
        hi = np.searchsorted(t_sorted, t[i] + days[i], side="right")
        idx = order_t[lo:hi]
        idx = idx[(idx != i) & ~dependent[idx] & (mag[idx] <= mag[i])]
        if idx.size == 0:
            continue
        # Great circle distance, haversine.
        dlat = lat[idx] - lat[i]
        dlon = lon[idx] - lon[i]
        a = np.sin(dlat / 2) ** 2 + np.cos(lat[i]) * np.cos(lat[idx]) * np.sin(dlon / 2) ** 2
        dist = 2 * 6371.0 * np.arcsin(np.sqrt(np.minimum(1.0, a)))
        dependent[idx[dist <= km[i]]] = True
    return ~dependent


# ---------------------------------------------------------------------------
# 2. Completeness and b value
# ---------------------------------------------------------------------------


def completeness(magnitudes: np.ndarray) -> float:
    """Maximum curvature plus 0.2, the usual correction for its bias."""
    if magnitudes.size < 20:
        return 5.0
    bins = np.round(magnitudes, 1)
    values, counts = np.unique(bins, return_counts=True)
    return float(values[np.argmax(counts)] + 0.2)


def b_value(magnitudes: np.ndarray, mc: float, delta: float = 0.1) -> float:
    above = magnitudes[magnitudes >= mc - 1e-9]
    if above.size < 30:
        return 1.0
    b = math.log10(math.e) / (above.mean() - (mc - delta / 2))
    return float(min(1.5, max(0.6, b)))


# ---------------------------------------------------------------------------
# 3 and 4. Rates on the grid
# ---------------------------------------------------------------------------


def grid_shape(region: Region) -> tuple[int, int]:
    rows = int(round((region.north - region.south) / GRID_STEP)) + 1
    cols = int(round((region.east - region.west) / GRID_STEP)) + 1
    return rows, cols


def smooth(counts: np.ndarray, region: Region) -> np.ndarray:
    """Separable Gaussian smoothing in kilometres, via the Fourier transform."""
    mid = math.radians((region.north + region.south) / 2)
    sigma_rows = KERNEL_KM / (KM_PER_DEGREE * GRID_STEP)
    sigma_cols = KERNEL_KM / (KM_PER_DEGREE * math.cos(mid) * GRID_STEP)
    out = counts.astype(float)
    for axis, sigma in ((0, sigma_rows), (1, sigma_cols)):
        half = int(math.ceil(4 * sigma))
        x = np.arange(-half, half + 1)
        kernel = np.exp(-0.5 * (x / sigma) ** 2)
        kernel /= kernel.sum()
        out = np.apply_along_axis(lambda v: np.convolve(v, kernel, mode="same"), axis, out)
    return out


def rate_grid(events: list[dict], mainshock: np.ndarray, region: Region, *,
              until: float, mc: float) -> tuple[np.ndarray, float, dict]:
    """Annual rate of mainshocks of magnitude 5 or more, per grid cell."""
    rows, cols = grid_shape(region)
    t_until = dt.datetime(int(until) + 1, 1, 1, tzinfo=dt.timezone.utc).timestamp()
    t_complete = dt.datetime(COMPLETE_SINCE, 1, 1, tzinfo=dt.timezone.utc).timestamp()
    t_spatial = dt.datetime(SPATIAL_SINCE, 1, 1, tzinfo=dt.timezone.utc).timestamp()

    years = (t_until - t_complete) / (365.25 * 86400)
    big = [e for e, keep in zip(events, mainshock)
           if keep and t_complete <= e["time"] < t_until and e["magnitude"] >= REFERENCE_MAGNITUDE]
    total = len(big) / years

    counts = np.zeros((rows, cols))
    placed = 0
    for e, keep in zip(events, mainshock):
        if not keep or not (t_spatial <= e["time"] < t_until) or e["magnitude"] < mc:
            continue
        r = int(round((e["latitude"] - region.south) / GRID_STEP))
        c = int(round((e["longitude"] - region.west) / GRID_STEP))
        if 0 <= r < rows and 0 <= c < cols:
            counts[r, c] += 1
            placed += 1
    density = smooth(counts, region)
    if density.sum() <= 0:
        density = np.ones((rows, cols))
    density = density / density.sum()
    density = (1 - FLOOR_SHARE) * density + FLOOR_SHARE / density.size
    stats = {"years_counted": round(years, 2), "mainshocks_m5": len(big),
             "events_placing_the_rate": placed}
    return density * total, total, stats


# ---------------------------------------------------------------------------
# The whole model
# ---------------------------------------------------------------------------


def fit(region: Region, events: list[dict], *, until: float) -> dict:
    """Everything a model file holds except its outline and its test record."""
    mainshock = decluster(events)
    t_until = dt.datetime(int(until) + 1, 1, 1, tzinfo=dt.timezone.utc).timestamp()
    t_spatial = dt.datetime(SPATIAL_SINCE, 1, 1, tzinfo=dt.timezone.utc).timestamp()
    recent = np.array([e["magnitude"] for e, keep in zip(events, mainshock)
                       if keep and t_spatial <= e["time"] < t_until])
    mc = max(4.5, completeness(recent))
    b = b_value(recent, mc)
    fitted = [e["magnitude"] for e in events if e["time"] < t_until]
    mmax = min(9.5, (max(fitted) if fitted else 7.0) + 0.5)
    rates, total, stats = rate_grid(events, mainshock, region, until=until, mc=mc)
    rows, cols = rates.shape
    return {
        "rates": rates, "b_value": round(b, 3), "completeness": round(mc, 2),
        "max_magnitude": round(mmax, 2), "total_rate_m5": round(total, 4),
        "grid": {"south": region.south, "west": region.west, "step": GRID_STEP,
                 "rows": rows, "cols": cols},
        "stats": {**stats, "events_in_record": len(events),
                  "mainshocks_in_record": int(mainshock.sum())},
        "mainshock": mainshock,
    }


def outline_for(region: Region, outlines: dict) -> list[list[list[float]]]:
    """The country's land, clipped to its box and simplified to about 2 km."""
    for feature in outlines["features"]:
        props = feature["properties"]
        if props.get("ISO_A2") == region.code or props.get("ISO_A2_EH") == region.code:
            geometry = feature["geometry"]
            polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
            rings = []
            for polygon in polygons:
                ring = polygon[0]
                if not any(region.contains(lat, lon) for lon, lat in ring):
                    continue
                simple = _simplify_ring(ring, 0.02)
                if len(simple) >= 4:
                    rings.append([[round(x, 3), round(y, 3)] for x, y in simple])
            return rings
    raise ValueError(f"no outline for {region.code}")


def _simplify_ring(ring: list[list[float]], tolerance: float) -> list[list[float]]:
    """A closed ring starts and ends on the same point, which gives the line
    between them no length, so it is split at the point farthest from the start
    and each half simplified on its own."""
    if len(ring) < 4:
        return ring
    x0, y0 = ring[0]
    far = max(range(len(ring)), key=lambda i: (ring[i][0] - x0) ** 2 + (ring[i][1] - y0) ** 2)
    first = _simplify(ring[: far + 1], tolerance)
    second = _simplify(ring[far:], tolerance)
    return first[:-1] + second


def _simplify(points: list[list[float]], tolerance: float) -> list[list[float]]:
    """Douglas and Peucker, iteratively so long coastlines do not recurse deep."""
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        ax, ay = points[start]
        bx, by = points[end]
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy) or 1e-12
        worst, index = 0.0, None
        for i in range(start + 1, end):
            px, py = points[i]
            d = abs(dy * px - dx * py + bx * ay - by * ax) / norm
            if d > worst:
                worst, index = d, i
        if index is not None and worst > tolerance:
            keep[index] = True
            stack.append((start, index))
            stack.append((index, end))
    return [p for p, k in zip(points, keep) if k]


def encode(rates: np.ndarray) -> str:
    return base64.b64encode(rates.astype("<f4").tobytes()).decode("ascii")


def write_model(region: Region, fitted: dict, outline, validation: dict,
                crosscheck: dict | None = None) -> Path:
    MODELS.mkdir(parents=True, exist_ok=True)
    doc = {
        "code": region.code, "name": region.name, "version": VERSION,
        "built": dt.date.today().isoformat(),
        "method": {
            "catalogue": "USGS ComCat, magnitude 4.5 and above, public domain",
            "declustering": "Gardner and Knopoff (1974) windows",
            "completeness": "maximum curvature plus 0.2",
            "b_value": "Aki and Utsu maximum likelihood",
            "smoothing": f"Gaussian kernel, {KERNEL_KM:g} km, on a {GRID_STEP:g} degree grid",
            "floor": f"{FLOOR_SHARE:.0%} of the regional rate, spread evenly",
            "rate_counted_since": COMPLETE_SINCE, "rate_placed_since": SPATIAL_SINCE,
            "reference_magnitude": REFERENCE_MAGNITUDE,
        },
        "box": {"south": region.south, "north": region.north, "west": region.west, "east": region.east},
        "b_value": fitted["b_value"], "completeness": fitted["completeness"],
        "max_magnitude": fitted["max_magnitude"], "total_rate_m5": fitted["total_rate_m5"],
        "stats": fitted["stats"],
        "grid": {**fitted["grid"], "rates_f32_b64": encode(fitted["rates"])},
        "outline": outline,
        "sources": [{"name": s.name, "url": s.url, "scope": s.scope} for s in region.sources],
        "validation": validation,
    }
    if crosscheck:
        doc["crosscheck"] = crosscheck
    path = MODELS / f"{region.code}.json"
    path.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
    return path


def write_places(codes: list[str]) -> Path:
    """Cities of 15,000 or more in the modelled countries, for the search box."""
    rows, admin = fetch_places(CACHE)
    wanted = set(codes) - {"TR"}           # Türkiye keeps its own, finer index
    out = []
    for r in rows:
        if len(r) < 15 or r[8] not in wanted:
            continue
        alternates = [a for a in r[3].split(",") if a and any(ord(ch) > 0x24F for ch in a) and len(a) <= 24][:4]
        out.append([r[1], r[2], r[8], admin.get(f"{r[8]}.{r[10]}", ""),
                    round(float(r[4]), 4), round(float(r[5]), 4), int(r[14] or 0), alternates])
    out.sort(key=lambda p: -p[6])
    path = MODELS / "places.json"
    path.write_text(json.dumps({
        "attribution": "Place names from GeoNames (geonames.org), CC BY 4.0",
        "places": out}, ensure_ascii=False, separators=(",", ":")))
    return path


def main(argv: list[str]) -> None:
    from .validate import backtest, crosscheck_turkey

    codes = [c.upper() for c in argv] or list(REGIONS)
    outlines = fetch_outlines(CACHE)
    this_year = dt.date.today().year
    for code in codes:
        region = REGIONS[code]
        events = fetch_catalogue(region, CACHE)
        outline = outline_for(region, outlines)
        validation = backtest(region, events, outline)
        final = fit(region, events, until=this_year - 1)   # whole years only
        check = crosscheck_turkey(region, final) if code == "TR" else None
        path = write_model(region, final, outline, validation, check)
        print(f"{code}: {'PASSED' if validation['passed'] else 'NOT PASSED'} "
              f"b={final['b_value']} mc={final['completeness']} "
              f"m5/yr={final['total_rate_m5']} -> {path.name}", flush=True)
    write_places(list(REGIONS))


if __name__ == "__main__":
    main(sys.argv[1:])
