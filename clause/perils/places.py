"""Somewhere to start from, when a buyer does not know their coordinates.

The hazard model works on latitude and longitude, which is the right basis for
it and the wrong thing to ask a person for. So this is an index of places, used
only to turn a name into a coordinate. Nothing in the pricing depends on a place
being in this list: a coordinate that is nowhere near any of these prices
exactly the same way.

Coordinates are the centre points of the eighty one provinces, plus districts a
buyer is likely to look for, either because many people live there or because
something happened there. Fold insensitive search handles the Turkish alphabet,
so "canakkale" finds Çanakkale and "istanbul" finds İstanbul, which matters when
the person typing is on a keyboard that does not have those letters.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Place:
    name: str
    latitude: float
    longitude: float
    region: str
    kind: str          # province or district

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "region": self.region,
            "kind": self.kind,
        }


# The Turkish dotted and dotless i do not fold to the same letter under the
# default rules, and a buyer typing on any keyboard should still find their
# town, so folding is done explicitly rather than left to str.lower.
_FOLD = str.maketrans({
    "ı": "i", "İ": "i", "I": "i", "i": "i",
    "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
    "ü": "u", "Ü": "u", "ö": "o", "Ö": "o",
    "ç": "c", "Ç": "c", "â": "a", "Â": "a",
})


def fold(text: str) -> str:
    """A form two spellings of the same place agree on."""
    folded = text.translate(_FOLD).lower().strip()
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", folded)
        if not unicodedata.combining(ch)
    )


PLACES: tuple[Place, ...] = (
    Place("Adana", 37.00, 35.32, "Akdeniz", "province"),
    Place("Adıyaman", 37.76, 38.28, "Güneydoğu Anadolu", "province"),
    Place("Afyonkarahisar", 38.76, 30.54, "Ege", "province"),
    Place("Ağrı", 39.72, 43.05, "Doğu Anadolu", "province"),
    Place("Aksaray", 38.37, 34.03, "İç Anadolu", "province"),
    Place("Amasya", 40.65, 35.83, "Karadeniz", "province"),
    Place("Ankara", 39.93, 32.86, "İç Anadolu", "province"),
    Place("Antalya", 36.90, 30.69, "Akdeniz", "province"),
    Place("Ardahan", 41.11, 42.70, "Doğu Anadolu", "province"),
    Place("Artvin", 41.18, 41.82, "Karadeniz", "province"),
    Place("Aydın", 37.85, 27.84, "Ege", "province"),
    Place("Balıkesir", 39.65, 27.89, "Marmara", "province"),
    Place("Bartın", 41.64, 32.34, "Karadeniz", "province"),
    Place("Batman", 37.88, 41.13, "Güneydoğu Anadolu", "province"),
    Place("Bayburt", 40.26, 40.23, "Karadeniz", "province"),
    Place("Bilecik", 40.14, 29.98, "Marmara", "province"),
    Place("Bingöl", 38.89, 40.50, "Doğu Anadolu", "province"),
    Place("Bitlis", 38.40, 42.11, "Doğu Anadolu", "province"),
    Place("Bolu", 40.74, 31.61, "Karadeniz", "province"),
    Place("Burdur", 37.72, 30.29, "Akdeniz", "province"),
    Place("Bursa", 40.19, 29.06, "Marmara", "province"),
    Place("Çanakkale", 40.15, 26.41, "Marmara", "province"),
    Place("Çankırı", 40.60, 33.62, "İç Anadolu", "province"),
    Place("Çorum", 40.55, 34.95, "Karadeniz", "province"),
    Place("Denizli", 37.78, 29.09, "Ege", "province"),
    Place("Diyarbakır", 37.91, 40.24, "Güneydoğu Anadolu", "province"),
    Place("Düzce", 40.84, 31.16, "Karadeniz", "province"),
    Place("Edirne", 41.68, 26.56, "Marmara", "province"),
    Place("Elazığ", 38.68, 39.22, "Doğu Anadolu", "province"),
    Place("Erzincan", 39.75, 39.49, "Doğu Anadolu", "province"),
    Place("Erzurum", 39.90, 41.27, "Doğu Anadolu", "province"),
    Place("Eskişehir", 39.78, 30.52, "İç Anadolu", "province"),
    Place("Gaziantep", 37.07, 37.38, "Güneydoğu Anadolu", "province"),
    Place("Giresun", 40.91, 38.39, "Karadeniz", "province"),
    Place("Gümüşhane", 40.46, 39.48, "Karadeniz", "province"),
    Place("Hakkâri", 37.57, 43.74, "Doğu Anadolu", "province"),
    Place("Hatay", 36.20, 36.16, "Akdeniz", "province"),
    Place("Iğdır", 39.92, 44.04, "Doğu Anadolu", "province"),
    Place("Isparta", 37.77, 30.55, "Akdeniz", "province"),
    Place("İstanbul", 41.01, 28.98, "Marmara", "province"),
    Place("İzmir", 38.42, 27.14, "Ege", "province"),
    Place("Kahramanmaraş", 37.58, 36.93, "Akdeniz", "province"),
    Place("Karabük", 41.20, 32.63, "Karadeniz", "province"),
    Place("Karaman", 37.18, 33.22, "İç Anadolu", "province"),
    Place("Kars", 40.60, 43.10, "Doğu Anadolu", "province"),
    Place("Kastamonu", 41.39, 33.78, "Karadeniz", "province"),
    Place("Kayseri", 38.73, 35.49, "İç Anadolu", "province"),
    Place("Kilis", 36.72, 37.12, "Güneydoğu Anadolu", "province"),
    Place("Kırıkkale", 39.85, 33.52, "İç Anadolu", "province"),
    Place("Kırklareli", 41.74, 27.22, "Marmara", "province"),
    Place("Kırşehir", 39.15, 34.16, "İç Anadolu", "province"),
    Place("Kocaeli", 40.77, 29.92, "Marmara", "province"),
    Place("Konya", 37.87, 32.49, "İç Anadolu", "province"),
    Place("Kütahya", 39.42, 29.99, "Ege", "province"),
    Place("Malatya", 38.36, 38.31, "Doğu Anadolu", "province"),
    Place("Manisa", 38.62, 27.43, "Ege", "province"),
    Place("Mardin", 37.31, 40.74, "Güneydoğu Anadolu", "province"),
    Place("Mersin", 36.81, 34.64, "Akdeniz", "province"),
    Place("Muğla", 37.22, 28.36, "Ege", "province"),
    Place("Muş", 38.73, 41.49, "Doğu Anadolu", "province"),
    Place("Nevşehir", 38.62, 34.71, "İç Anadolu", "province"),
    Place("Niğde", 37.97, 34.68, "İç Anadolu", "province"),
    Place("Ordu", 40.98, 37.88, "Karadeniz", "province"),
    Place("Osmaniye", 37.07, 36.25, "Akdeniz", "province"),
    Place("Rize", 41.02, 40.52, "Karadeniz", "province"),
    Place("Sakarya", 40.78, 30.40, "Marmara", "province"),
    Place("Samsun", 41.29, 36.33, "Karadeniz", "province"),
    Place("Siirt", 37.93, 41.94, "Güneydoğu Anadolu", "province"),
    Place("Sinop", 42.03, 35.15, "Karadeniz", "province"),
    Place("Sivas", 39.75, 37.02, "İç Anadolu", "province"),
    Place("Şanlıurfa", 37.17, 38.79, "Güneydoğu Anadolu", "province"),
    Place("Şırnak", 37.52, 42.46, "Güneydoğu Anadolu", "province"),
    Place("Tekirdağ", 40.98, 27.51, "Marmara", "province"),
    Place("Tokat", 40.31, 36.55, "Karadeniz", "province"),
    Place("Trabzon", 41.00, 39.72, "Karadeniz", "province"),
    Place("Tunceli", 39.11, 39.55, "Doğu Anadolu", "province"),
    Place("Uşak", 38.68, 29.41, "Ege", "province"),
    Place("Van", 38.49, 43.38, "Doğu Anadolu", "province"),
    Place("Yalova", 40.66, 29.28, "Marmara", "province"),
    Place("Yozgat", 39.82, 34.81, "İç Anadolu", "province"),
    Place("Zonguldak", 41.46, 31.79, "Karadeniz", "province"),
    Place("İstanbul, Kadıköy", 40.99, 29.03, "Marmara", "district"),
    Place("İstanbul, Bakırköy", 40.98, 28.87, "Marmara", "district"),
    Place("İstanbul, Beşiktaş", 41.04, 29.01, "Marmara", "district"),
    Place("İstanbul, Büyükçekmece", 41.02, 28.58, "Marmara", "district"),
    Place("İstanbul, Pendik", 40.88, 29.24, "Marmara", "district"),
    Place("İstanbul, Şile", 41.17, 29.61, "Marmara", "district"),
    Place("Ankara, Çankaya", 39.90, 32.85, "İç Anadolu", "district"),
    Place("İzmir, Konak", 38.42, 27.13, "Ege", "district"),
    Place("İzmir, Bornova", 38.47, 27.22, "Ege", "district"),
    Place("Adana, Seyhan", 36.99, 35.30, "Akdeniz", "district"),
    Place("Antalya, Muratpaşa", 36.88, 30.71, "Akdeniz", "district"),
    Place("Bursa, Osmangazi", 40.18, 29.06, "Marmara", "district"),
    Place("Kocaeli, Gölcük", 40.72, 29.82, "Marmara", "district"),
    Place("Kahramanmaraş, Pazarcık", 37.49, 37.30, "Akdeniz", "district"),
    Place("Hatay, Antakya", 36.20, 36.16, "Akdeniz", "district"),
    Place("Elazığ, Sivrice", 38.45, 39.31, "Doğu Anadolu", "district"),
    Place("Muğla, Bodrum", 37.03, 27.43, "Ege", "district"),
    Place("Muğla, Fethiye", 36.62, 29.12, "Ege", "district"),
    Place("Denizli, Sarayköy", 37.92, 28.92, "Ege", "district"),
    Place("Konya, Çumra", 37.57, 32.77, "İç Anadolu", "district"),
    Place("Şanlıurfa, Harran", 36.86, 39.03, "Güneydoğu Anadolu", "district"),
    Place("Edirne, Keşan", 40.85, 26.63, "Marmara", "district"),
)

_INDEX = {fold(place.name): place for place in PLACES}

# The codes the five hand written locations used before the model worked on
# coordinates. Kept so existing policies, seeds and saved links keep resolving
# to the same point on the map rather than quietly moving.
LEGACY_CODES = {
    "IST-KADIKOY": "İstanbul, Kadıköy",
    "IST-BAKIRKOY": "İstanbul, Bakırköy",
    "IZM-KONAK": "İzmir, Konak",
    "ADY-MERKEZ": "Adıyaman",
    "ANK-CANKAYA": "Ankara, Çankaya",
}


def find_place(name: str) -> Place | None:
    """Resolve a name to a place, exactly or by a unique prefix."""
    if not name:
        return None
    legacy = LEGACY_CODES.get(name.upper().strip())
    if legacy is not None:
        return _INDEX[fold(legacy)]

    key = fold(name)
    exact = _INDEX.get(key)
    if exact is not None:
        return exact
    # A district is often given as just its own name.
    for place in PLACES:
        if fold(place.name).split(", ")[-1] == key:
            return place
    matches = [place for place in PLACES if fold(place.name).startswith(key)]
    return matches[0] if len(matches) == 1 else None


def search(query: str, limit: int = 8) -> list[Place]:
    """Places whose name contains the query, provinces first."""
    key = fold(query)
    if not key:
        return list(PLACES[:limit])
    hits = [place for place in PLACES if key in fold(place.name)]
    hits.sort(key=lambda place: (
        not fold(place.name).startswith(key),
        place.kind != "province",
        len(place.name),
    ))
    return hits[:limit]


# ---------------------------------------------------------------------------
# Everywhere else
# ---------------------------------------------------------------------------

_WORLD: list[tuple[dict[str, Any], tuple[str, ...], int]] | None = None


def _world() -> list[tuple[dict[str, Any], tuple[str, ...], int]]:
    """Cities from GeoNames in every country the build fitted a model for.

    Türkiye comes from the hand made list above, which has the districts a
    buyer there looks for; GeoNames rows for Türkiye are left out so the same
    town does not appear twice.
    """
    global _WORLD
    if _WORLD is not None:
        return _WORLD
    from ..hazard.model import places

    rows: list[tuple[dict[str, Any], tuple[str, ...], int]] = []
    for place in PLACES:
        rows.append((
            {**place.to_dict(), "country": "TR"},
            (fold(place.name),),
            10_000_000 if place.kind == "province" else 1_000_000,
        ))
    for name, ascii_name, country, admin, lat, lon, population, *rest in places().get("places", []):
        if country == "TR":
            continue
        alternates = rest[0] if rest else []
        keys = tuple(dict.fromkeys(fold(n) for n in (name, ascii_name, *alternates) if n))
        rows.append((
            {"name": name, "latitude": lat, "longitude": lon, "region": admin or "",
             "kind": "city", "country": country},
            keys,
            int(population or 0),
        ))
    _WORLD = rows
    return rows


def search_world(query: str, limit: int = 12, country: str | None = None,
                 peril: str | None = None) -> list[dict[str, Any]]:
    """Places anywhere with a model, best match first, then the larger place.

    Each result says whether cover can be priced there, so a buyer who types a
    city the protocol has no tested model for is told so at once rather than
    after choosing it. Whether it can depends on which cover is being bought:
    the rain model passes in six countries and the wind model in a different
    set, and answering both with the earthquake list marked the wrong places
    unavailable in each.
    """
    from . import EARTHQUAKE, REGISTRY

    key = fold(query)
    if not key:
        return []
    asked = REGISTRY.get(peril or "") if peril else None
    priced = (asked.territory if asked is not None and asked.territory is not None
              else EARTHQUAKE.territory)
    hits: list[tuple[tuple[int, int, int], dict[str, Any]]] = []
    for row, keys, population in _world():
        if country and row["country"] != country:
            continue
        rank = None
        for k in keys:
            if k == key:
                rank = 0
                break
            if k.startswith(key):
                rank = 1 if rank is None else min(rank, 1)
            elif key in k and rank is None:
                rank = 2
        if rank is None:
            continue
        hits.append(((rank, -population, len(row["name"])), row))
    hits.sort(key=lambda item: item[0])
    return [{**row, "priced": row["country"] in priced} for _, row in hits[:limit]]
