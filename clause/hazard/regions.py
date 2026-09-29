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
    """One box of ground fitted as a unit, and the country whose law it is in.

    Those are two different things, and the United States is where they came
    apart. A region is the extent a catalogue can be fitted over: one b value,
    one completeness magnitude, one largest event, all of which describe a
    tectonic setting rather than a state. Alaska's largest recorded event is
    8.7 and the lower forty eight's is 7.8, and its rate of magnitude five is
    three times theirs; fitting them together would give California an Alaskan
    b value and Alaska a Californian ceiling. So they are separate regions.

    They are the same country. Whose licence writes the policy, whose law
    governs it and which register a buyer appears in are questions about the
    country, and the answer for Anchorage is the same as for Brooklyn.
    """

    code: str                                   # the region's own key
    name: str
    south: float
    north: float
    west: float
    east: float
    national: Source
    #: ISO 3166 alpha 2. Empty means the region is a whole country and its
    #: code is the country's, which is true of every region but two.
    country_code: str = ""

    @property
    def country(self) -> str:
        return self.country_code or self.code

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
    # Alaska and Hawaii, in the United States and not in that box. They were
    # left out because one box cannot hold all three, and that reasoning is
    # still right: it is the fit that cannot be shared, not the country. Over
    # the box below Alaska gives b=0.829, a largest event of 8.7 and 20.9
    # magnitude five earthquakes a year, against the lower forty eight's 0.745,
    # 7.8 and 7.2. Put together, each would be described by the other.
    #
    # Without them our own model answered Anchorage, Fairbanks, Juneau,
    # Honolulu and Hilo with the same number, the global background floor, once
    # in 11,119 years at intensity VII. Fitted here they read once in 41, 479,
    # 3,956, 15,398 and 108, against the USGS's own once in 87 at Anchorage and
    # once in 105 at Hilo.
    #
    # The Alaskan box stops at the antimeridian. The Aleutians run past it and
    # a box that wrapped would need every reader of it to handle the wrap; no
    # place this product offers is out there, the westernmost being Juneau at
    # -134, and the day one is the box is the thing to fix.
    Region("AK", "Alaska", 51.0, 72.0, -180.0, -129.0, USGS, country_code="US"),
    Region("HI", "Hawaii", 18.0, 23.5, -161.5, -154.0, USGS, country_code="US"),
)}
