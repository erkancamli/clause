"""Fetching what the models are built from. Run offline, by the build script.

Nothing in this module runs on the protocol's server at request time. The
server reads the model files the build writes; the catalogue itself stays on
the machine that built them.

Licences, because a model is only as publishable as its inputs:
    USGS ComCat            United States government work, public domain
    Natural Earth          public domain
    GeoNames               Creative Commons Attribution 4.0, credited on the
                           page wherever a place name from it is shown
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from .regions import Region

USER_AGENT = "Clause hazard build (+https://clause.insure)"
FDSN = "https://earthquake.usgs.gov/fdsnws/event/1/query"
OUTLINES = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
            "master/geojson/ne_50m_admin_0_countries.geojson")
PLACES = "https://download.geonames.org/export/dump/cities15000.zip"
ADMIN1 = "https://download.geonames.org/export/dump/admin1CodesASCII.txt"


def _get(url: str, *, timeout: float = 120.0) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as reply:  # noqa: S310
        return reply.read()


def fetch_catalogue(region: Region, cache: Path, *, start: int = 1973,
                    min_magnitude: float = 4.5, refresh: bool = False) -> list[dict]:
    """Every event of at least this magnitude in the region's box since a year.

    Fetched a few years at a time because the service caps one answer at twenty
    thousand events, and cached as CSV so a rebuild does not ask again.
    """
    path = cache / f"usgs_{region.code}.csv"
    if path.exists() and not refresh:
        return _read(path)
    rows: list[dict] = []
    year, end_year = start, dt.date.today().year
    while year <= end_year:
        stop = min(year + 4, end_year)
        query = urllib.parse.urlencode({
            "format": "csv", "orderby": "time-asc",
            "starttime": f"{year}-01-01", "endtime": f"{stop + 1}-01-01",
            "minmagnitude": min_magnitude,
            "minlatitude": region.south, "maxlatitude": region.north,
            "minlongitude": region.west, "maxlongitude": region.east,
            "eventtype": "earthquake",
        })
        text = _get(f"{FDSN}?{query}").decode("utf-8")
        for row in csv.DictReader(io.StringIO(text)):
            try:
                rows.append({
                    "time": dt.datetime.fromisoformat(row["time"].replace("Z", "+00:00")).timestamp(),
                    "latitude": float(row["latitude"]), "longitude": float(row["longitude"]),
                    "depth": float(row["depth"] or 0.0), "magnitude": float(row["mag"]),
                    "id": row["id"],
                })
            except (KeyError, ValueError):
                continue
        year = stop + 1
    rows.sort(key=lambda r: r["time"])
    cache.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["time", "latitude", "longitude", "depth", "magnitude", "id"])
        writer.writeheader(); writer.writerows(rows)
    return rows


def _read(path: Path) -> list[dict]:
    with path.open() as handle:
        return [{"time": float(r["time"]), "latitude": float(r["latitude"]),
                 "longitude": float(r["longitude"]), "depth": float(r["depth"]),
                 "magnitude": float(r["magnitude"]), "id": r["id"]}
                for r in csv.DictReader(handle)]


def fetch_outlines(cache: Path) -> dict:
    path = cache / "ne_50m_admin_0_countries.geojson"
    if not path.exists():
        cache.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_get(OUTLINES))
    return json.loads(path.read_text())


def fetch_places(cache: Path) -> tuple[list[list[str]], dict[str, str]]:
    """GeoNames cities of 15,000 people or more, and first level region names."""
    zpath, apath = cache / "cities15000.zip", cache / "admin1CodesASCII.txt"
    if not zpath.exists():
        cache.mkdir(parents=True, exist_ok=True)
        zpath.write_bytes(_get(PLACES))
    if not apath.exists():
        apath.write_bytes(_get(ADMIN1))
    with zipfile.ZipFile(zpath) as archive:
        text = archive.read("cities15000.txt").decode("utf-8")
    rows = [line.split("\t") for line in text.splitlines() if line]
    admin = {}
    for line in apath.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            admin[parts[0]] = parts[1]
    return rows, admin
