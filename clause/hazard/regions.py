"""The countries modelled, where they are, and who measures earthquakes there.

The box is the region fetched from the catalogue and gridded. It is wider than
the country, because an earthquake just offshore shakes the coast and a policy
circle on the coast reaches over the water.

The sources are what the validators read at settlement. A country is only
offered if at least three independent publishers report magnitudes for it,
because the aggregation rule needs three of four agreeing, and a rule that can
only ever hear one voice is not an aggregation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Source:
    name: str
    url: str
    scope: str          # "global" or "national"


USGS = Source("USGS National Earthquake Information Center",
              "https://earthquake.usgs.gov/fdsnws/event/1/", "global")
EMSC = Source("European Mediterranean Seismological Centre",
              "https://www.seismicportal.eu/fdsnws/event/1/", "global")
GFZ = Source("GFZ GEOFON", "https://geofon.gfz.de/fdsnws/event/1/", "global")


@dataclass(frozen=True, slots=True)
class Region:
    code: str                                   # ISO 3166 alpha 2
    name: str
    south: float
    north: float
    west: float
    east: float
    national: Source

    @property
    def sources(self) -> tuple[Source, ...]:
        """Who reports magnitudes here, each publisher once.

        Most countries have four: three global networks and their own. The
        United States has three, because the body that runs its national
        network is the one that publishes the global catalogue. Counting it
        twice would make a country look better watched than it is.
        """
        seen: list[Source] = []
        for source in (USGS, EMSC, GFZ, self.national):
            if all(source.url != kept.url for kept in seen):
                seen.append(source)
        return tuple(seen)

    def contains(self, latitude: float, longitude: float) -> bool:
        return self.south <= latitude <= self.north and self.west <= longitude <= self.east


REGIONS: dict[str, Region] = {r.code: r for r in (
    Region("TR", "Türkiye", 35.5, 42.5, 25.5, 45.0,
           Source("AFAD Earthquake Department", "https://deprem.afad.gov.tr/", "national")),
    Region("JP", "Japan", 24.0, 46.0, 122.0, 154.0,
           Source("Japan Meteorological Agency", "https://www.jma.go.jp/", "national")),
    Region("CL", "Chile", -56.5, -17.0, -77.5, -66.0,
           Source("Centro Sismológico Nacional", "https://www.sismologia.cl/", "national")),
    Region("MX", "Mexico", 14.0, 33.0, -118.5, -86.0,
           Source("Servicio Sismológico Nacional", "http://www.ssn.unam.mx/", "national")),
    Region("ID", "Indonesia", -11.5, 6.5, 94.5, 141.5,
           Source("BMKG", "https://www.bmkg.go.id/", "national")),
    Region("PH", "Philippines", 4.5, 21.5, 116.0, 127.5,
           Source("PHIVOLCS", "https://www.phivolcs.dost.gov.ph/", "national")),
    Region("GR", "Greece", 34.5, 42.0, 19.0, 30.0,
           Source("National Observatory of Athens", "https://www.gein.noa.gr/", "national")),
    Region("IT", "Italy", 35.5, 47.5, 6.5, 19.0,
           Source("INGV", "https://terremoti.ingv.it/", "national")),
    Region("NZ", "New Zealand", -47.5, -34.0, 166.0, 179.0,
           Source("GeoNet", "https://www.geonet.org.nz/", "national")),
    Region("TW", "Taiwan", 21.5, 25.5, 119.5, 122.5,
           Source("Central Weather Administration", "https://www.cwa.gov.tw/", "national")),
    # The lower forty eight. Alaska and Hawaii are not in this box and are not
    # covered by this model: one box cannot hold the Aleutians, which cross the
    # antimeridian, and stretching it over the Pacific would sweep the whole
    # rim's seismicity into the rate for California.
    #
    # The national network here is the same body that publishes the global
    # catalogue, so this country has three independent voices rather than four.
    # That is still enough for a rule that needs three of four to agree, and it
    # is said rather than hidden behind a list that looks one longer than it is.
    # Its national network is USGS itself, named once rather than twice under a
    # second title: the Advanced National Seismic System is the same body that
    # publishes the global catalogue, and listing it again would make the
    # country look better watched than it is.
    Region("US", "United States", 24.0, 50.0, -125.5, -66.0, USGS),
)}
