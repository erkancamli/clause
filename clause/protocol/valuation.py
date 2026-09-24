"""How much something is worth, from how big it is.

Cover is capped by the value at risk; that cap is what makes this insurance
rather than a wager. Until this module the buyer typed the value, so a 100 m²
garden and a 100 hectare farm could buy the same cover. Now the value comes
from what the buyer describes, and the protocol does the arithmetic:

    a home      floor area x rebuild cost per square metre, by country and
                building type, adjusted for the building's age
    a field     area x expected revenue per hectare, by country and crop
    a trip      what the trip cost, as stated (there is nothing to measure)
    a vehicle   its stated value, checked against what a car of that age can
                be worth, and capped at the market's depreciation curve

Every per unit figure here is a *Figure*: an amount, the currency it was
published in, the date it was published for, who published it, and what kind
of figure it is. The last of those is the one that matters most, because four
different numbers are published in every country and three of them are traps.

    rebuild     what it costs to build the thing again. What we want.
    insurance   a scheme's own sum insured per square metre. Official and
                current, usually below rebuild cost on purpose.
    market      a builder's or a valuer's quote. Real money, no authority.
    permit      the base for a building permit fee or a property tax.
    budget      a ceiling on what a public body may appropriate or pay. Not a
                measure of what building costs, and sometimes says so itself.

A permit figure looks the most official of the four and is always the most
wrong. Italy publishes one at 505.90 EUR/m² against a real rebuild cost near
1,800; Chile's MINVU table is five to eight times below what a house costs to
build; the Philippine PSA figure is what applicants *declare* to a building
officer, and puts a single house at 113 USD/m². All three are genuine
government publications and none of them is a rebuild cost, so this module
refuses to price from one: a figure of kind "permit" raises rather than
quietly under-insuring a family by a factor of four.

Two more facts about official data shaped this file. First, statistics
offices publish *indices*, not levels: ISTAT, ELSTAT, TUIK and INEGI all say
how fast building costs are rising and none of them says what building costs.
An index cannot set a sum insured, but it can carry a level forward from the
day it was published to today, which is what ESCALATION does. Second, a
national figure is not a local one, and only three countries publish the
relative cost of building in each of their regions -- Indonesia's IKK, Japan's
building starts statistics and Taiwan's own insurance schedule. Where a
country publishes no such thing this module says so rather than inventing a
multiplier.

Age matters in two opposite directions and both are modelled. An old building
is worth less to rebuild like for like (the schedule's rebuild cost is for a
new one), but it is more likely to be damaged: Turkiye's compulsory scheme
charges more for what was built before the 2000 code, and everything built
before 2000 is the stock that fell in 2023. So an older home gets a lower
ceiling and a higher price, which is what age does everywhere in insurance. A
car simply loses value with age; a fifteen year old car does not carry a new
car's cover whatever the owner says it is worth.

The figures are starting points and are published with every quote, with
their source, so the buyer sees how the ceiling was reached. They are
indicative figures in the protocol's unit of account, not a valuation of any
property, and an issuing insurer replaces them with its own schedule.
"""

from __future__ import annotations

import datetime as dt
import time

from dataclasses import dataclass, field
from typing import Any

#: The four kinds of published figure, and the one that must never set a sum
#: insured. See the module docstring for why each of the three traps is a trap.
FIGURE_KINDS = ("rebuild", "insurance", "market", "permit", "budget")
NOT_A_RATE = ("permit", "budget")


@dataclass(frozen=True, slots=True)
class Figure:
    """A published number, with everything needed to judge it.

    Without the date it cannot be carried forward; without the source it
    cannot be checked; without the kind it cannot be trusted at all.
    """

    # The amount is None for a figure that is published somewhere but could
    # not be read. Those are recorded anyway: what has to be remembered about
    # a trap is which instrument it is, not what number is in it.
    amount: float | None
    currency: str
    as_at: str
    source: str
    kind: str
    note: str = ""

    def __post_init__(self) -> None:
        if self.kind not in FIGURE_KINDS:
            raise ValueError(f"{self.kind!r} is not one of {FIGURE_KINDS}")
        if self.amount is None and self.kind not in NOT_A_RATE:
            raise ValueError("only a figure that may never price a policy can go unread")

    def to_dict(self) -> dict[str, Any]:
        out = {"amount": self.amount, "currency": self.currency, "as_at": self.as_at,
               "source": self.source, "kind": self.kind}
        if self.note:
            out["note"] = self.note
        return out

    def said(self) -> str:
        much = "value not obtained" if self.amount is None else f"{self.amount:,.0f} {self.currency}"
        return f"{much} per m², {self.source}, {self.as_at}"


@dataclass(frozen=True, slots=True)
class Rate:
    """How much of a currency goes to one unit of the protocol's account."""

    per_unit: float
    as_at: str
    source: str


@dataclass(frozen=True, slots=True)
class Index:
    """How fast a country's building costs are rising, and who says so."""

    per_year: float
    as_at: str
    source: str


# The unit of account is the protocol's own, worth about one US dollar. Rates
# read as "this much local currency to one unit". The euro rate is the ECB's
# own USD/EUR reference rate inverted; the yen and dollar rates are crossed
# through the euro from the same file, which is why they carry the same date.
FX: dict[str, Rate] = {
    "USD": Rate(1.0, "2026-09-23", "the unit of account"),
    "TRY": Rate(48.8377, "2026-09-23", "TCMB gosterge kuru (doviz satis), via e-Devlet"),
    "EUR": Rate(0.876347, "2026-09-23", "ECB euro reference rates, USD/EUR 1.1411"),
    "JPY": Rate(157.92, "2026-09-23", "ECB euro reference rates, EUR/JPY 180.20 crossed"),
    "NZD": Rate(1.7570, "2026-09-23", "ECB euro reference rates, EUR/NZD 2.0049 crossed"),
    "TWD": Rate(31.69, "2026-09-23",
                "commercial mid-market quote; the ECB's TWD series stops in 2020 and "
                "every official Taiwanese source was unreachable"),
    "MXN": Rate(17.218, "2026-09-23", "commercial mid-market quote; Banxico was unreachable"),
    "CLP": Rate(960.30, "2026-09-23", "commercial mid-market quote; Banco Central was unreachable"),
    # Chile prices building in unidades de fomento, not pesos, because the UF
    # is indexed daily to inflation. Carrying the Chilean schedule in UF is
    # what a Chilean insurer does, and it is why the Chilean figure does not
    # go stale between revisions the way the others do.
    "CLF": Rate(0.0235649, "2026-09-23", "the unidad de fomento, at about 40,750 CLP to the UF"),
    "PHP": Rate(62.516, "2026-09-23", "commercial mid-market quote; BSP was unreachable"),
    "IDR": Rate(17878.0, "2026-09-23", "commercial mid-market quote; Bank Indonesia was unreachable"),
}

# Building cost inflation, for carrying a figure forward from the day it was
# published. These are the indices the statistics offices publish instead of
# levels. A country missing from this table is one whose figure is used as it
# stands, with its date shown.
ESCALATION: dict[str, Index] = {
    "TR": Index(0.2837, "2026-07-31",
                "TUIK Insaat Maliyet Endeksi, bina insaati, year on year to July 2026"),
    "IT": Index(0.067, "2026-07-31",
                "derived from ISTAT's residential construction cost index, 116.8 in "
                "December 2025 to 121.3 in July 2026"),
    "GR": Index(0.040, "2026-06-30",
                "ELSTAT construction cost index for new residential buildings, "
                "year on year in the second quarter of 2026"),
    "MX": Index(0.0489, "2026-05-31",
                "INEGI INPP construccion residencial, year on year to May 2026"),
}

#: However stale a table becomes, a figure is not carried forward more than
#: this. Past it the number needs revisiting, not compounding.
MAX_ESCALATION_YEARS = 3.0

BUILDINGS = ("flat", "house", "shop")

# Rebuild cost per square metre, by country and building type. The figure for
# each country is the best evidenced one available in this order: a real
# rebuild cost, then an official scheme's own insurance value, then market
# evidence. Never a permit base -- those are recorded below in REFUSED, where
# they cannot be reached by accident.
#
# Where a country publishes nothing for a building type, FALLS_BACK says which
# figure stands in for it and why. A shop is built to the same standard as the
# flats above it, so the flat rate stands in for one wherever no commercial
# schedule is published.
REBUILD: dict[str, dict[str, Figure]] = {
    "TR": {
        "flat": Figure(21_050.0, "TRY", "2026-01-01",
                       "Cevre, Sehircilik ve Iklim Degisikligi Bakanligi, Yapi Yaklasik "
                       "Birim Maliyetleri 2026, class III-B (Resmi Gazete 3.2.2026, no. 33157)",
                       "rebuild",
                       "excludes VAT, land, infrastructure and site works; includes 15% "
                       "overhead and 10% contractor profit"),
        "house": Figure(21_050.0, "TRY", "2026-01-01",
                        "same schedule, class III-B, which covers a detached or semi-detached "
                        "villa under 200 m² as well as a block above three storeys",
                        "rebuild"),
        "shop": Figure(33_900.0, "TRY", "2026-01-01",
                       "same schedule, class IV-B (banks, exchanges, halls)", "rebuild"),
    },
    "IT": {
        "flat": Figure(1_800.0, "EUR", "2026-01-01",
                       "Italian insurance-trade guidance on the valore di ricostruzione "
                       "of a standard condominium, 1,600 to 2,000 EUR/m²",
                       "market",
                       "a trade assumption, labelled as one, because Italy publishes no "
                       "rebuild rate at all. Its regulator says so itself: IVASS reported "
                       "in June 2026, as in June 2024, that setting the sum insured is "
                       "still left to the insured and checked only when a claim arrives. "
                       "Its own mandatory catastrophe return has no floor area field, so "
                       "no rate per square metre could be computed from it either"),
    },
    "GR": {
        "flat": Figure(900.0, "EUR", "2026-01-14",
                       "AADE, i axia anakataskevis: the reconstruction value a dwelling "
                       "must be insured for to earn the ENFIA reduction, set for 2026 by "
                       "ministerial decision A.1005/2026",
                       "insurance",
                       "read as the State means it: a floor, not a valuation. A policy "
                       "qualifies at 900 x the main floor area and there is no upper "
                       "limit, so used as a ceiling it is deliberately conservative -- "
                       "about half of what building in Greece actually costs. It is flat "
                       "nationwide, it is per main floor area rather than total, and it "
                       "is reset each year by its own decision"),
    },
    "JP": {
        "flat": Figure(392_000.0, "JPY", "2025-12-31",
                       "Japan's building starts statistics, condominium for sale, "
                       "reinforced concrete, CY2025",
                       "rebuild", "the cost declared at the start of building"),
        "house": Figure(261_000.0, "JPY", "2025-12-31",
                        "Japan's building starts statistics, owner-built detached timber "
                        "house, CY2025",
                        "rebuild", "the cost declared at the start of building"),
    },
    "TW": {
        "flat": Figure(34_757.0, "TWD", "2025-01-01",
                       "Taiwan's 2025 residential building cost reference table for "
                       "insurance, Taipei City, 9 to 10 storeys, plus the table's own "
                       "lowest fit-out line",
                       "insurance",
                       "the table is published per ping and excludes interior fit-out, "
                       "which it adds back separately at 3,025 to 30,250 TWD/m²; the "
                       "lowest of those is included here"),
        "house": Figure(24_170.0, "TWD", "2025-01-01",
                        "the same table, Taipei City, single storey, plus its lowest "
                        "fit-out line",
                        "insurance", "add 16% for a steel frame"),
    },
    "NZ": {
        "flat": Figure(3_996.0, "NZD", "2026-07-31",
                       "Stats NZ building consents, apartments, year to July 2026, "
                       "grossed up by 15% GST",
                       "rebuild",
                       "a consent value excludes demolition and professional fees, so "
                       "this is a floor rather than a sum insured"),
        "house": Figure(3_737.0, "NZD", "2026-07-31",
                        "Stats NZ building consents, houses, year to July 2026, "
                        "grossed up by 15% GST",
                        "rebuild",
                        "a consent value excludes demolition and professional fees, so "
                        "this is a floor rather than a sum insured"),
    },
    "MX": {
        "house": Figure(6_743.0, "MXN", "2024-12-31",
                        "CMIC's own costed prototype, vivienda economica of 40 m², "
                        "direct cost, December 2024",
                        "rebuild",
                        "direct cost only at the cheapest standard built in Mexico: no "
                        "land, design, permits, overhead, financing or profit, which "
                        "together commonly add a third to a half. A floor, then. The "
                        "12,500 to 22,000 MXN/m² widely attributed to CMIC is not in "
                        "anything CMIC publishes and reads as market sale price with the "
                        "land in it; CMIC itself now publishes only an index"),
    },
    "CL": {
        "house": Figure(27.0, "CLF", "2026-01-01",
                        "Chilean architects' pricing for a house, 24 to 30 UF/m², 2026",
                        "market",
                        "MINVU's unit cost table is the right instrument but is a permit "
                        "fee base, five to eight times below what building costs"),
    },
    "PH": {
        "house": Figure(30_000.0, "PHP", "2026-01-01",
                        "Philippine contractor pricing for Metro Manila, "
                        "25,000 to 35,000 PHP/m², 2026",
                        "market",
                        "a Metro Manila figure; the PSA's own statistic is a declared "
                        "permit value and cannot be used"),
    },
    "ID": {
        "house": Figure(6_230_000.0, "IDR", "2025-07-31",
                        "Keputusan Gubernur DKI Jakarta 580/2025, harga satuan tertinggi "
                        "for building state housing, rumah negara type C to E, city areas",
                        "rebuild",
                        "issued under the building law rather than tax law, which is what "
                        "makes it a construction cost and not a fee base; it includes the "
                        "contractor's overhead, construction safety management and tax, "
                        "and excludes land. Read it as a ceiling rather than an average: "
                        "tertinggi means the most the city may pay. Jakarta's own market "
                        "priced model of the same class lands within one per cent of it"),
    },
}

# What stands in where a country publishes nothing for a building type, and
# the reason, which is shown to the buyer rather than hidden.
FALLS_BACK: dict[str, dict[str, tuple[str, str]]] = {
    "IT": {"house": ("flat", "no Italian source publishes a rebuild cost for a plain "
                     "detached house, so the condominium rate is used, which is a floor")},
    "MX": {"flat": ("house", "no Mexican source splits a flat from a house")},
    "PH": {"flat": ("house", "no Philippine source splits a flat from a house")},
    "CL": {"flat": ("house", "no Chilean source splits a flat from a house")},
    "GR": {"house": ("flat", "the Greek State's reconstruction value is one figure for "
                     "any dwelling")},
    "ID": {"flat": ("house", "no Indonesian source splits a flat from a house")},
}
# A shop is built to the same standard as the flats above it, and only Turkiye
# publishes a separate commercial class.
SHOP_FALLS_BACK = ("flat", "no commercial schedule is published here, so the rate for "
                           "a dwelling is used")

# Figures that exist, are official, and must never set a sum insured. They are
# written down so that nobody adds them later thinking they were overlooked.
REFUSED: dict[str, Figure] = {
    "IT": Figure(505.90, "EUR", "2026-01-01",
                 "Comune di Milano, costo di costruzione 2026",
                 "permit",
                 "the base for the building permit contribution, descended from a 1994 "
                 "figure by indexation; about a quarter of what rebuilding costs"),
    "CL": Figure(259_511.0, "CLP", "2026-01-01",
                 "MINVU resolucion exenta 2016 of 30 December 2025, tabla de costos "
                 "unitarios, category 3 class C, which is the ordinary Chilean house",
                 "permit",
                 "its own title says what it is for: fixing unit values to calculate "
                 "municipal permit duties, under the articles of the urbanism law that "
                 "set those duties. Escalated quarterly by consumer prices, not by "
                 "building costs. Even its single dearest cell, 541,253 for a steel "
                 "framed category 1, is half of what building costs; the cell an ordinary "
                 "house falls in is a quarter of it. Its class structure is worth copying, "
                 "its levels are not"),
    "MX": Figure(1_249.0, "MXN", "2022-02-01",
                 "IMSS costos de mano de obra por metro cuadrado para la obra privada, "
                 "casa habitacion tipo medio",
                 "permit",
                 "the likeliest ancestor of any official looking Mexican rate per square "
                 "metre, because it is the one official table that has both a number and "
                 "a house versus apartment split. It is labour only, and it is not even a "
                 "labour cost: it is the base on which social security contributions are "
                 "imputed to private building work, uprated each year by the inflation "
                 "unit rather than by building prices. About a tenth of what building "
                 "costs"),
    "ID": Figure(None, "IDR", "2025-06-30",
                 "Pergub DKI Jakarta 17/2025, standar harga satuan for 2026",
                 "budget",
                 "the rare instrument that disqualifies itself in its own text: article "
                 "2(4) says the standard cannot be used as the basis for preparing a cost "
                 "estimate. It is a ceiling on what the city budget may appropriate. Its "
                 "figures are not published in the decree at all, which is the second "
                 "reason it cannot be used"),
    "PH": Figure(7_059.35, "PHP", "2026-02-28",
                 "PSA construction statistics from approved building permits, single house",
                 "permit",
                 "the value applicants declare to a building officer, divided by floor "
                 "area; it puts a house at 113 USD/m²"),
    "GR": Figure(None, "EUR", "2007-02-27",
                 "Ypourgeio Oikonomikon, times ekkinisis elachistou kostous oikodomis, "
                 "POL. 1033/2007, used with forms K1 to K9 in the objective valuation "
                 "system",
                 "permit",
                 "the most tempting thing Greece publishes, because it is official, it "
                 "is per square metre and it is regional for dwellings. Its own framework "
                 "decision says what it is for: determining the taxable value of a "
                 "building on transfer. The same species as Italy's costo di costruzione, "
                 "and the edition in force still dates from 2007. Its values were not "
                 "obtained and are not wanted"),
    "TR": Figure(11_737.0, "TRY", "2026-09-01",
                 "DASK, sigorta bedeline esas metrekare bedeli, reinforced concrete",
                 "insurance",
                 "not refused as wrong, but as a different thing: the compulsory scheme's "
                 "own capped sum insured, about 56% of the Ministry's rebuild cost, and "
                 "itself capped at 2,488,318 TRY whatever the floor area"),
}

# How much more or less it costs to build in a region than in the country's
# base. Only three countries publish this, and a fourth can be computed from
# published statistics; the rest say nothing and are absent here on purpose.
# The factors are per building type, and a type not named takes 1.0.
REGIONS: dict[str, tuple[str, dict[str, dict[str, float]]]] = {
    "JP": ("Japan's building starts statistics give a cost per square metre for every "
           "prefecture. These are the prefecture against the national figure, CY2025.",
           {"Tokyo": {"house": 1.11, "flat": 1.25},
            "Kanagawa": {"house": 1.02, "flat": 1.06},
            "Aichi": {"house": 1.00, "flat": 0.84},
            "Osaka": {"house": 0.91, "flat": 0.99},
            "Hokkaido": {"house": 1.03, "flat": 1.10},
            "Nagano": {"house": 1.16, "flat": 0.88}}),
    "TW": ("Taiwan's insurance cost table publishes its own grid by city. These are the "
           "city against Taipei, which is the rate above.",
           {"Taipei": {},
            "New Taipei": {"house": 0.847, "flat": 0.847},
            "Taichung": {"house": 0.884, "flat": 0.884},
            "Yunlin": {"house": 0.884, "flat": 0.884}}),
    "ID": ("BPS publishes the Indeks Kemahalan Konstruksi for all 38 provinces and 514 "
           "districts, 2025, on Surabaya = 100. These are the province against Jakarta, "
           "which is the rate above; the islands off Jakarta come from the same decree "
           "as the rate itself. The spread is wider than anyone expects. BPS's own site "
           "refuses a machine and its interface needs a key, so Jakarta and the Papuan "
           "highlands are the two confirmed against the published table and the rest "
           "are as reported.",
           {"Jakarta": {},
            "Kepulauan Seribu": {"house": 1.090, "flat": 1.090},
            "Jakarta Pusat": {"house": 1.039, "flat": 1.039},
            "Jawa Timur": {"house": 0.871, "flat": 0.871},
            "Surabaya": {"house": 0.871, "flat": 0.871},
            "Papua": {"house": 1.176, "flat": 1.176},
            "Papua Barat": {"house": 1.086, "flat": 1.086},
            "Papua Selatan": {"house": 1.246, "flat": 1.246},
            "Papua Tengah": {"house": 1.823, "flat": 1.823},
            "Papua Pegunungan": {"house": 2.170, "flat": 2.170}}),
    "NZ": ("New Zealand publishes no multiplier, but Stats NZ's consent values by region "
           "give one for houses in the year to July 2026. The apartment samples outside "
           "Auckland are too small to use, so a flat takes the national rate.",
           {"Auckland": {"house": 1.01, "flat": 1.05},
            "Wellington": {"house": 1.05},
            "Waikato": {"house": 1.00},
            "Canterbury": {"house": 0.88},
            "Otago": {"house": 1.24},
            "Southland": {"house": 0.95}}),
}
#: Countries where the question was asked and the answer is that nothing is
#: published. Said out loud so it reads as a finding and not as an omission.
NO_REGIONS = {
    "TR": "no provincial figure is published: the Ministry's schedule is one national "
          "table, TUIK's index has no regional breakdown, and DASK's per square metre "
          "value is the same everywhere",
    "IT": "no regional rebuild cost is published. Every region does set its own permit "
          "fee base, so a search for building cost by Italian region returns twenty "
          "official numbers that look like a rebuild table and are not one; the regional "
          "price books price work items rather than a rate per square metre",
    "GR": "the State's reconstruction value is explicitly flat nationwide",
    "MX": "INEGI's series by city is a price change per city, not a cost level, so no "
          "ratio can be taken from it",
    "CL": "the national cost table has no regional variation",
    "PH": "the PSA publishes construction value by region but no cost per square metre",
}


@dataclass(frozen=True, slots=True)
class Harvest:
    """One hectare's revenue in a normal season, and where the number is from.

    Revenue is a yield times a producer price, and both belong to a year. A
    drought takes away a season's income, so a season's income is the cap.

    The exchange rate belongs to that year too, and carrying it here is not
    pedantry. A Turkish hectare of maize earned 76,748 lira in 2024, which was
    2,339 of the unit of account at the rate of that year; the same lira at
    today's rate would read 1,571, and the farmer would be under-covered by a
    third for no reason but arithmetic done on the wrong day.
    """

    revenue: float
    currency: str
    year: int
    per_unit: float
    source: str
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        out = {"revenue": self.revenue, "currency": self.currency, "year": self.year,
               "per_unit": self.per_unit, "source": self.source}
        if self.note:
            out["note"] = self.note
        return out


_FAO = "FAOSTAT production and producer prices, which take both from the national office"
_EUROSTAT = "Eurostat crop production and selling prices"
_TUIK = ("TUIK, Tahil ve diger bitkisel urun fiyatlari, prices received by farmers, "
         "2025")

# The exchange rate of the year a season was earned in. FAOSTAT's own annual
# averages, which agree with the ECB's daily rates over the same year to
# within 0.2%; the 2025 lira is the mean of the ECB's 255 published days of
# that year; 2026 is today's rate.
YEAR_FX = {
    (2024, "TRY"): 32.8059, (2025, "TRY"): 39.57, (2026, "TRY"): 48.8377,
    (2024, "EUR"): 0.923890, (2023, "EUR"): 0.923890,
    (2024, "MXN"): 18.3049,
    (2024, "CLP"): 943.5722, (2022, "CLP"): 873.5,
    (2024, "IDR"): 15855.45, (2024, "PHP"): 57.2907,
    (2024, "JPY"): 151.3663, (2024, "NZD"): 1.652308,
}


def _crop(revenue: float, currency: str, year: int, source: str, note: str = "") -> Harvest:
    return Harvest(revenue, currency, year, YEAR_FX[(year, currency)], source, note)


# Expected revenue of one hectare, by country and crop. A crop a country does
# not grow at scale is absent, and so is a crop whose producer price nobody
# publishes; in both cases the protocol says which crops it can cover there
# rather than guessing a number.
REVENUE: dict[str, dict[str, Harvest]] = {
    "TR": {
        # Wheat and barley are taken from the season's own intervention price
        # rather than a two year old average, because Turkish agricultural
        # prices have been rising by a third a year and a stale cap would be
        # a third short by the time it paid.
        "wheat": _crop(49_566.0, "TRY", 2026,
                       "TMO 2026 purchase price of 16,500 TRY/t at the 2024 yield of "
                       "3.004 t/ha",
                       "the intervention price of the season being covered, not a "
                       "historical average"),
        "barley": _crop(32_334.0, "TRY", 2026,
                        "TMO 2026 purchase price of 12,750 TRY/t at the 2024 yield of "
                        "2.536 t/ha"),
        # The rest are TUIK's own prices received by farmers, read from the
        # 2025 table, against the 2024 yield. The yield is deliberately the
        # older one: 2025 was a drought year in Turkiye, wheat down 14% and
        # barley down 26%, and a cover meant to replace a normal season's
        # income cannot be sized on the season it is insuring against.
        "maize": _crop(105_353.0, "TRY", 2025, _TUIK),
        "sunflower": _crop(58_587.0, "TRY", 2025, _TUIK, "the oilseed variety"),
        "cotton": _crop(124_742.0, "TRY", 2025, _TUIK,
                        "kutlu, the unginned crop as it is sold at the gin, not lint "
                        "and not the cottonseed that comes out of crushing it"),
        "chickpea": _crop(47_635.0, "TRY", 2025, _TUIK),
        "lentil": _crop(52_085.0, "TRY", 2025, _TUIK, "the red variety, which is most of the crop"),
        # Sugar beet is the one Turkish crop TUIK does not price, because the
        # price is contracted with the sugar company rather than surveyed at
        # the farm gate. FAOSTAT's 2024 figure stands until that contract
        # price is read from its own announcement.
        "sugar_beet": _crop(135_396.0, "TRY", 2024, _FAO,
                            "TUIK surveys no sugar beet price; this is a year older "
                            "than the rest of the Turkish table"),
    },
    "IT": {
        "wheat": _crop(1_131.0, "EUR", 2024, _FAO),
        "maize": _crop(2_292.0, "EUR", 2024, _FAO),
        # Italy files no barley, sunflower or sugar beet price to Eurostat and
        # FAOSTAT's Italian series for those died between 1999 and 2007.
    },
    "GR": {
        "wheat": _crop(814.0, "EUR", 2024, _FAO),
        "barley": _crop(536.0, "EUR", 2024, _FAO),
        "maize": _crop(2_535.0, "EUR", 2024, _FAO),
        "sunflower": _crop(1_008.0, "EUR", 2024, _FAO),
        "cotton": _crop(1_819.0, "EUR", 2023, _FAO,
                        "the last year with both a Greek yield and a price"),
        "lentil": _crop(2_952.0, "EUR", 2024, _EUROSTAT,
                        "a 2025 yield against a 2024 price"),
        # Greek chickpea is left out: Eurostat's first published yield for it,
        # 3.06 t/ha, is about double any plausible rainfed Mediterranean
        # figure and would put the cover at 9,300 a hectare.
    },
    "MX": {
        "wheat": _crop(36_099.0, "MXN", 2024, _FAO),
        "barley": _crop(16_732.0, "MXN", 2024, _FAO),
        "maize": _crop(21_058.0, "MXN", 2024, _FAO),
        "cotton": _crop(54_567.0, "MXN", 2024, _FAO),
        "chickpea": _crop(35_403.0, "MXN", 2024, _FAO),
        "lentil": _crop(13_303.0, "MXN", 2024, _FAO, "a marginal crop at 7,000 hectares"),
    },
    "CL": {
        "wheat": _crop(1_368_433.0, "CLP", 2024, _FAO),
        "maize": _crop(2_431_417.0, "CLP", 2024, _FAO),
        "barley": _crop(1_584_330.0, "CLP", 2022, _FAO,
                        "Chile's barley producer price series stops in 2022"),
        "sugar_beet": _crop(5_559_670.0, "CLP", 2022, _FAO,
                            "Chile's sugar beet producer price series stops in 2022"),
    },
    "ID": {"maize": _crop(35_101_608.0, "IDR", 2024, _FAO)},
    "PH": {"maize": _crop(56_452.0, "PHP", 2024, _FAO)},
    "JP": {
        "wheat": _crop(193_179.0, "JPY", 2024, _FAO,
                       "a Japanese cereal grower's income is mostly direct payments, "
                       "which are not in the producer price"),
        "barley": _crop(356_240.0, "JPY", 2024, _FAO,
                        "the barley price is administered at about three and a half "
                        "times the world level"),
        "sugar_beet": _crop(1_081_847.0, "JPY", 2024, _FAO),
    },
    "NZ": {
        "wheat": _crop(5_107.0, "NZD", 2024, _FAO),
        "barley": _crop(3_428.0, "NZD", 2024, _FAO),
        "maize": _crop(6_012.0, "NZD", 2024, _FAO),
    },
}

#: Every crop any country in the table grows, for the page's list of choices.
CROPS = ("wheat", "barley", "maize", "sunflower", "cotton", "chickpea", "lentil", "sugar_beet")

AREA_M2 = (15.0, 3000.0)
THIS_YEAR = time.gmtime().tm_year
BUILT = (1900, THIS_YEAR)
MODEL_YEAR = (1990, THIS_YEAR)


# How a building's age moves its ceiling and its price. The ceiling factor is
# the share of new rebuild cost a like for like rebuild is worth; the hazard
# factor multiplies expected loss, after the DASK tariff's treatment of
# pre 2000 construction and the observed performance of the 1975 and 1998
# codes in 1999 and 2023.
def home_age_factors(built: int, country: str) -> tuple[float, float]:
    age = max(0, THIS_YEAR - built)
    ceiling = max(0.55, 1.0 - 0.01 * age)
    if country == "TR":
        hazard = 1.0 if built >= 2019 else 1.15 if built >= 2000 else 1.6 if built >= 1976 else 2.0
    else:
        hazard = 1.0 if age <= 20 else 1.25 if age <= 45 else 1.5
    return ceiling, hazard


# Straight line to a floor: a car keeps about 85% a year of its value for the
# first years and levels off at a fifth of new.
def vehicle_age_factor(model_year: int) -> float:
    age = max(0, THIS_YEAR - model_year)
    return max(0.2, 0.85 ** age)

# The most a car of a given age can plausibly be worth, so a stated value
# cannot buy new car cover for an old one.
VEHICLE_NEW_CAP = 250_000.0
AREA_HA = (0.01, 5000.0)
TRIP = (50.0, 20000.0)
VEHICLE = (1000.0, 250000.0)


class ValuationError(ValueError):
    """A description that does not give a value. The message is safe to show."""


def fold(text: str) -> str:
    """A name reduced to what two spellings of it have in common."""
    return " ".join(str(text or "").replace("-", " ").replace("/", " ").split()).casefold()


def _years_since(as_at: str, now: float) -> float:
    try:
        day = dt.date.fromisoformat(as_at)
    except ValueError:
        return 0.0
    then = dt.datetime(day.year, day.month, day.day, tzinfo=dt.timezone.utc).timestamp()
    return max(0.0, (now - then) / (365.2425 * 86400.0))


def in_units(figure: Figure) -> float:
    """A published amount in the protocol's unit of account, at today's rate."""
    rate = FX.get(figure.currency)
    if rate is None:
        raise ValuationError("that currency has no rate in the protocol's unit of account")
    return figure.amount / rate.per_unit


def harvest_in_units(harvest: Harvest) -> float:
    """A season's revenue, at the rate of the season it was earned in."""
    return harvest.revenue / harvest.per_unit


def carried_forward(figure: Figure, country: str, now: float) -> tuple[float, str]:
    """The figure in units of account today, and what was done to get there.

    A level published in January is not a level in September, and the only
    thing the statistics offices publish that can close that gap is an index.
    """
    if figure.kind in NOT_A_RATE:
        raise ValuationError(
            f"the only figure published for this is {figure.source}, which is "
            f"{figure.note or 'not a measure of what building costs'}; "
            f"it cannot set a sum insured")
    base = in_units(figure)
    if figure.kind == "insurance":
        # An index carries a cost forward because a cost drifts. A scheme's
        # own figure does not drift: it is set by decision and reset on its
        # own timetable, so 900 euros stays 900 euros until the authority
        # says otherwise. Carrying it forward would invent a number nobody
        # published and no insurer would accept.
        return base, "as published; a scheme's own figure is reset by its author, not by an index"
    index = ESCALATION.get(country)
    if index is None or not index.per_year:
        return base, ""
    years = min(_years_since(figure.as_at, now), MAX_ESCALATION_YEARS)
    if years < 1 / 12:
        return base, ""
    grown = base * (1.0 + index.per_year) ** years
    return grown, (f"carried forward {years * 12:.0f} months at {index.per_year:.1%} a year, "
                   f"{index.source}")


def rate_for(country: str, building: str, *, region: str | None = None,
             now: float | None = None) -> tuple[float, dict[str, Any]]:
    """The rebuild cost per square metre to use, and how it was arrived at."""
    now = time.time() if now is None else now
    table = REBUILD.get(country)
    if not table:
        raise ValuationError("there is no rebuild cost schedule for this country yet")
    if building not in BUILDINGS:
        raise ValuationError("a home is a flat, a house or a shop")
    said: list[str] = []
    figure = table.get(building)
    seen = {building}
    wanted = building
    while figure is None:
        instead, why = (FALLS_BACK.get(country, {}).get(wanted)
                        or (SHOP_FALLS_BACK if wanted == "shop" else (None, "")))
        if not instead or instead in seen:
            raise ValuationError("there is no rebuild cost for this kind of building here yet")
        seen.add(instead)
        said.append(why)
        wanted = instead
        figure = table.get(instead)
    stood_in = "; ".join(w for w in said if w)
    amount, forward = carried_forward(figure, country, now)
    how: dict[str, Any] = {"figure": figure.to_dict(), "per_m2": round(amount, 2)}
    if stood_in:
        how["stands_in"] = stood_in
    if forward:
        how["carried_forward"] = forward
    # The region is read for the building whose figure was actually used:
    # a shop takes the flats' rate, so it takes the flats' region too.
    named, factor = region_factor(country, wanted, region)
    if factor != 1.0:
        amount *= factor
        how["region"] = {"name": named, "factor": factor, "basis": REGIONS[country][0]}
        how["per_m2"] = round(amount, 2)
    elif country in NO_REGIONS:
        how["region"] = {"name": None, "factor": 1.0, "basis": NO_REGIONS[country]}
    return amount, how


def region_factor(country: str, building: str, region: str | None) -> tuple[str | None, float]:
    """What a region costs against its country's base, where that is published."""
    known = REGIONS.get(country)
    if not known or not region:
        return None, 1.0
    wanted = fold(region)
    if not wanted:
        return None, 1.0
    # The name as given wins outright, because "Jakarta" is not "Jakarta
    # Pusat". Only then is the name looked for inside what the buyer wrote,
    # longest first, because "Papua Pegunungan" costs twice what "Papua" does
    # and the shorter name sits inside the longer one.
    names = sorted(known[1].items(), key=lambda pair: -len(pair[0]))
    for name, factors in names:
        if fold(name) == wanted:
            return name, float(factors.get(building, 1.0))
    for name, factors in names:
        if fold(name) in wanted:
            return name, float(factors.get(building, 1.0))
    return None, 1.0


def harvest_for(country: str, crop: str) -> Harvest:
    table = REVENUE.get(country)
    if not table:
        raise ValuationError("no crop cover is written in this country yet")
    found = table.get(crop)
    if found is None:
        grown = ", ".join(sorted(table))
        raise ValuationError(
            f"there is no published producer price for this crop here, so it cannot be "
            f"covered yet; what can be covered is {grown}")
    return found


@dataclass(frozen=True, slots=True)
class Valuation:
    value: float
    basis: str
    size: dict[str, Any]
    how: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out = {"value": round(self.value, 2), "basis": self.basis, "size": dict(self.size)}
        if self.how:
            out["how"] = self.how
        return out


def _number(size: dict[str, Any], key: str, bounds: tuple[float, float], what: str) -> float:
    try:
        value = float(size[key])
    except (KeyError, TypeError, ValueError) as error:
        raise ValuationError(f"give {what}") from error
    if value != value or not bounds[0] <= value <= bounds[1]:
        raise ValuationError(f"{what} must be between {bounds[0]:g} and {bounds[1]:g}")
    return value


def value_of(size: dict[str, Any], *, country: str | None = None,
             region: str | None = None, now: float | None = None) -> Valuation:
    """The value at risk this description supports."""
    kind = str(size.get("kind", ""))
    if kind == "home":
        code = (country or str(size.get("country", ""))).upper()
        building = str(size.get("building", "flat"))
        area = _number(size, "area_m2", AREA_M2, "the floor area in square metres")
        rate, how = rate_for(code, building, region=region or size.get("region"), now=now)
        built = int(_number(size, "built", BUILT, "the year it was built")) if "built" in size else None
        out = {"kind": "home", "building": building, "area_m2": area, "country": code}
        if built is None:
            return Valuation(area * rate, f"{area:g} m² x {rate:,.0f} per m² to rebuild", out, how)
        ceiling, hazard = home_age_factors(built, code)
        out["built"] = built
        out["hazard_factor"] = hazard
        return Valuation(area * rate * ceiling,
                         f"{area:g} m² x {rate:,.0f} per m² to rebuild, x {ceiling:.0%} for a building of {built}",
                         out, how)
    if kind == "field":
        code = (country or str(size.get("country", ""))).upper()
        crop = str(size.get("crop", ""))
        harvest = harvest_for(code, crop)
        area = _number(size, "area_ha", AREA_HA, "the area in hectares")
        rate = harvest_in_units(harvest)
        return Valuation(area * rate, f"{area:g} ha x {rate:,.0f} expected revenue per ha",
                         {"kind": "field", "crop": crop, "area_ha": area, "country": code},
                         {"harvest": harvest.to_dict(), "per_ha": round(rate, 2)})
    if kind == "vehicle":
        # A car's value is its market value, which the buyer knows and a size
        # cannot tell; stated, and bounded.
        value = _number(size, "value", VEHICLE, "what the vehicle is worth")
        if "model_year" not in size:
            return Valuation(value, "the vehicle's market value, as stated",
                             {"kind": "vehicle", "value": value})
        year = int(_number(size, "model_year", MODEL_YEAR, "the model year"))
        cap = VEHICLE_NEW_CAP * vehicle_age_factor(year)
        return Valuation(min(value, cap),
                         f"the stated value of {value:,.0f}, capped at {cap:,.0f} for a {year} model",
                         {"kind": "vehicle", "value": value, "model_year": year})
    if kind == "trip":
        value = _number(size, "value", TRIP, "what the trip cost")
        return Valuation(value, "the cost of the trip, as stated", {"kind": "trip", "value": value})
    raise ValuationError("describe what is at risk: a home, a field or a trip")


# Which description each peril needs.
KIND_FOR = {"earthquake": "home", "drought": "field", "flight_delay": "trip",
            "vehicle_flood": "vehicle", "storm": "home"}


def schedule(now: float | None = None) -> dict[str, Any]:
    """Every figure the page needs to show a buyer the ceiling as they type.

    The rates are given twice over: once as a plain number in the unit of
    account, which is what the arithmetic on the page needs, and once with the
    currency, date, source and kind behind it, which is what a buyer asking
    where the number came from deserves.
    """
    now = time.time() if now is None else now
    rebuild: dict[str, dict[str, float]] = {}
    behind: dict[str, dict[str, Any]] = {}
    for code in REBUILD:
        rebuild[code] = {}
        behind[code] = {}
        for building in BUILDINGS:
            try:
                amount, how = rate_for(code, building, now=now)
            except ValuationError:
                continue
            rebuild[code][building] = round(amount, 2)
            behind[code][building] = how
    revenue = {code: {crop: round(harvest_in_units(h), 2) for crop, h in crops.items()}
               for code, crops in REVENUE.items()}
    behind_crops = {code: {crop: h.to_dict() for crop, h in crops.items()}
                    for code, crops in REVENUE.items()}
    return {
        "rebuild_per_m2": rebuild, "revenue_per_ha": revenue,
        "rebuild_basis": behind, "revenue_basis": behind_crops,
        "buildings": list(BUILDINGS), "crops": list(CROPS),
        "area_m2": AREA_M2, "area_ha": AREA_HA, "trip": TRIP, "vehicle": VEHICLE,
        "built": BUILT, "model_year": MODEL_YEAR, "vehicle_new_cap": VEHICLE_NEW_CAP,
        "home_age": {"ceiling_per_year": 0.01, "ceiling_floor": 0.55,
                     "hazard": {"TR": [[2019, 1.0], [2000, 1.15], [1976, 1.6], [0, 2.0]],
                                "*": [[2006, 1.0], [1981, 1.25], [0, 1.5]]}},
        "vehicle_age": {"per_year": 0.85, "floor": 0.2},
        "fx": {code: {"per_unit": r.per_unit, "as_at": r.as_at, "source": r.source}
               for code, r in FX.items()},
        "escalation": {code: {"per_year": i.per_year, "as_at": i.as_at, "source": i.source}
                       for code, i in ESCALATION.items()},
        "refused": {code: f.to_dict() for code, f in REFUSED.items()},
        "no_regions": dict(NO_REGIONS),
        "note": ("indicative figures in the protocol's unit of account; the issuing "
                 "insurer replaces them with its own schedule"),
    }
