"""The national hazard models, as their own authorities publish them.

Our own model is a catalogue since 1973 and a global shaking equation with no
site term. Where a country publishes a probabilistic hazard model, that model
knows the ground, the basin and the faults our catalogue has not seen, and it
is the figure its own regulator prices against. These tests cover the reading
of a published curve and the one number it moves in our pricing.
"""

from __future__ import annotations

import json
import math

import pytest

from clause.hazard import published as pub
from clause.perils import shaking as sh

# Osaka, as J-SHIS publishes it: surface velocity at four exceedance
# probabilities in fifty years, turned into annual rates.
OSAKA = (34.6937, 135.5023)
OSAKA_PGV = ((42.6, 0.39), (71.7, 0.10), (91.6, 0.05), (130.8, 0.02))


def osaka_curve() -> tuple[tuple[float, float], ...]:
    return tuple(sorted((pub.mmi_from_pgv(pgv), -math.log(1.0 - p) / 50.0)
                        for pgv, p in OSAKA_PGV))


@pytest.fixture
def published(monkeypatch: pytest.MonkeyPatch):
    """One published point at Osaka, in place of whatever the build wrote."""
    def place(latitude: float, longitude: float, curve=None) -> tuple[dict, ...]:
        return ({"country": "JP", "name": "Osaka", "latitude": latitude,
                 "longitude": longitude, "curve": curve or osaka_curve(),
                 "publisher": "NIED J-SHIS", "reference": "https://www.j-shis.bosai.go.jp/",
                 "measure": "PGV, cm/s", "conversion": "Worden 2012", "version": "test"},)

    def install(latitude: float = OSAKA[0], longitude: float = OSAKA[1], curve=None) -> None:
        rows = place(latitude, longitude, curve)
        monkeypatch.setattr(pub, "curves", lambda: rows)
        pub.nearest.cache_clear()
        sh._mapping.cache_clear()

    install()
    yield install
    pub.nearest.cache_clear()
    sh._mapping.cache_clear()


def test_velocity_becomes_intensity_by_the_published_relation() -> None:
    # Worden, Gerstenberger, Rhoades and Wald (2012), as ShakeMap's own
    # implementation carries it: three straight pieces in log velocity.
    assert pub.mmi_from_pgv(1.0) == pytest.approx(3.78, abs=0.01)     # log10 v = 0
    assert pub.mmi_from_pgv(0.0) == 0.0
    # The pieces meet where the paper joins them, so the curve has no step in it.
    for log_joint in (-1.21, 0.53):
        joint = 10 ** log_joint
        below = pub.mmi_from_pgv(joint * 0.999)
        above = pub.mmi_from_pgv(joint * 1.001)
        assert below == pytest.approx(above, abs=0.02), f"a step at log v = {log_joint}"
    # And it agrees with the intensity ShakeMap prints for a recorded velocity:
    # 16 to 31 cm/s is VII, 31 to 60 is VIII, 60 to 116 is IX.
    assert 6.5 < pub.mmi_from_pgv(20.0) < 7.6
    assert 7.6 <= pub.mmi_from_pgv(42.6) < 8.5
    assert 8.5 <= pub.mmi_from_pgv(90.0) < 9.4


def test_the_curve_is_read_between_its_points_and_beyond_them() -> None:
    curve = ((6.0, 0.01), (7.0, 0.001))
    assert pub.rate_at(curve, 6.0) == pytest.approx(0.01)
    assert pub.rate_at(curve, 7.0) == pytest.approx(0.001)
    # Straight in log rate: halfway is the geometric mean, not the arithmetic one.
    assert pub.rate_at(curve, 6.5) == pytest.approx(math.sqrt(0.01 * 0.001))
    assert pub.rate_at(curve, 6.5) < 0.5 * (0.01 + 0.001)
    # Below the first point the curve does not invent hazard it does not show.
    assert pub.rate_at(curve, 4.0) == pytest.approx(0.01)
    # Above the last it carries on down the last slope.
    assert pub.rate_at(curve, 8.0) == pytest.approx(0.0001)
    assert pub.rate_at((), 7.0) == 0.0


def test_a_curve_describes_places_near_it_and_no_further(published) -> None:
    near = pub.nearest(*OSAKA)
    assert near is not None and near["name"] == "Osaka" and near["distance_km"] == 0.0
    # Kobe, about 30 km west, is described by it.
    assert pub.nearest(34.69, 135.20) is not None
    # Tokyo, four hundred kilometres away, is not.
    assert pub.nearest(35.68, 139.69) is None
    assert pub.NEAR_KM == 60.0


def test_the_map_makes_our_curve_the_published_one(published) -> None:
    """Inside the published points, our answer is their answer."""
    subject = {"latitude": OSAKA[0], "longitude": OSAKA[1]}
    term = sh.site_term(subject)
    assert term is not None
    assert term["place"] == "Osaka" and term["publisher"] == "NIED J-SHIS"
    assert not term["at_the_limit"]
    # Japan says Osaka shakes harder than a global equation with no site term
    # expects, and by more than the equation's own scatter.
    assert term["shift"] > sh.IPE_SIGMA
    # Not close: the same. A single shift left this a factor of 1.6 out.
    for level, rate in osaka_curve():
        ours = sh.rate_at_least(subject, level)
        assert ours == pytest.approx(rate, rel=0.05), f"MMI {level:.2f}"
    assert term["worst_ratio"] < 1.1


def test_the_map_moves_where_our_curve_is_read_and_nothing_else(published) -> None:
    subject = {"latitude": OSAKA[0], "longitude": OSAKA[1]}
    # rate_at_least is our own curve, read where the map says to read it.
    for level in (6.0, 6.5, 7.0, 7.5, 8.0):
        where = sh.ours_at(subject, level)
        assert where < level                     # Japan shakes harder than we said
        assert sh.rate_at_least(subject, level) == pytest.approx(
            sh.raw_rate_at_least(subject, where))
    # The raw curve is untouched: the same rates the catalogue model always gave.
    assert sh.raw_rate_at_least(subject, 7.0) > 0.0
    # And the map rises, so stronger shaking is never made more frequent.
    where = [sh.ours_at(subject, x / 10) for x in range(50, 101)]
    assert where == sorted(where)


def test_a_far_stronger_published_curve_is_not_followed_without_limit(published) -> None:
    # Violent shaking every other year: stronger than anything our model makes.
    published(curve=((9.0, 0.5), (9.9, 0.2)))
    subject = {"latitude": OSAKA[0], "longitude": OSAKA[1]}
    term = sh.site_term(subject)
    assert term is not None
    assert term["at_the_limit"] is True
    # The map is held at the bound, so the residual is left standing and said.
    assert term["worst_ratio"] > 2.0
    for level in (7.0, 8.0, 9.0):
        assert level - sh.ours_at(subject, level) <= sh.SHIFT_LIMIT + 1e-9


def test_an_address_no_published_model_covers_is_priced_as_before(published) -> None:
    somewhere = {"latitude": 35.68, "longitude": 139.69}
    assert sh.site_term(somewhere) is None
    assert sh.ours_at(somewhere, 7.0) == 7.0
    assert sh.theirs_at(somewhere, 7.0) == 7.0
    assert sh.rate_at_least(somewhere, 7.0) == pytest.approx(sh.raw_rate_at_least(somewhere, 7.0))


def test_the_events_drawn_for_capital_go_through_the_same_map(published) -> None:
    """The capital model draws events; they arrive on the published scale."""
    import random

    subject = {"latitude": OSAKA[0], "longitude": OSAKA[1]}
    mapped = sum(sum(sh.draw(random.Random(s), subject)) for s in range(40))
    monkey = sh.theirs_at
    try:
        sh.theirs_at = lambda subject, level: level   # type: ignore[assignment]
        plain = sum(sum(sh.draw(random.Random(s), subject)) for s in range(40))
    finally:
        sh.theirs_at = monkey                         # type: ignore[assignment]
    assert mapped > plain          # Japan shakes Osaka harder than we said
    # And the map is the inverse of the one the price is read through.
    for x in (6.0, 7.0, 8.0):
        assert sh.ours_at(subject, sh.theirs_at(subject, x)) == pytest.approx(x, abs=0.05)


def test_the_quote_says_whose_model_priced_it(published) -> None:
    """A buyer is told whose figure the frequencies are, not left to assume."""
    from fastapi.testclient import TestClient

    from clause.api.app import create_app

    client = TestClient(create_app(trials=200))
    reply = client.get("/api/hazard", params={"latitude": OSAKA[0], "longitude": OSAKA[1]}).json()
    said = reply["shaking"]["published"]
    assert said["publisher"] == "NIED J-SHIS" and said["place"] == "Osaka"
    assert said["distance_km"] == 0.0 and said["shift"] > 0

    # An address no published model covers says nothing rather than something.
    far = client.get("/api/hazard", params={"latitude": 35.68, "longitude": 139.69}).json()
    assert "published" not in far["shaking"]


def test_the_shipped_curves_are_hazard_curves() -> None:
    """The file the build wrote, read as the runtime reads it."""
    doc = pub.OUT
    assert doc.exists(), "the published models are part of the product, not a local build"
    countries = json.loads(doc.read_text(encoding="utf-8"))
    assert set(countries) <= set(pub.SOURCES)
    for code, country in countries.items():
        assert country["publisher"] and country["reference"].startswith("https://")
        # What the build could not read is named rather than passed over, so a
        # hole in the model cannot be mistaken for a place with no hazard.
        assert isinstance(country["missed"], list)
        assert len(country["missed"]) < 0.02 * len(country["points"])
        for point in country["points"]:
            curve = point["curve"]
            assert len(curve) >= 2, f"{code} {point['name']}"
            motion = [x for x, _ in curve]
            rates = [y for _, y in curve]
            assert motion == sorted(motion) and len(set(motion)) == len(motion)
            # The file holds what the publisher said, so it may carry the same
            # rate twice. It may never rise: stronger shaking is not more
            # frequent. The reader below is what makes it strict.
            assert all(a >= b for a, b in zip(rates, rates[1:])), f"{code} {point['name']}"
            assert all(y > 0 for y in rates)

    # Everything below comes from the one reading above. Comparing the runtime's
    # cached view against a second read of the path counts two moments, and a
    # build writing the file between them made this fail with nothing wrong,
    # which is the worst kind of test. So the reader is applied to the rows
    # already in hand instead.
    # Keyed on the coordinate, because a name is not a key: Japan offers two
    # cities called Sendai, one in Miyagi and one in Kagoshima, and twenty five
    # other repeated names. Keyed on the name, half of each pair silently
    # replaced the other and this compared one city's curve against the other's.
    read = {(row["country"], row["latitude"], row["longitude"]): row for row in pub.curves()}
    assert len(read) == sum(1 for c in countries.values() for p in c["points"]
                            if len(pub._read_curve(p["curve"])) >= 2)
    for code, country in countries.items():
        for point in country["points"]:
            want = pub._read_curve(point["curve"])
            if len(want) < 2:
                continue
            where = (code, point["latitude"], point["longitude"])
            assert where in read, where
            assert read[where]["curve"] == want, where
    for row in read.values():
        curve = row["curve"]
        # In intensity by the time the runtime sees it, weak end dropped, and
        # strictly increasing, because this is the axis the runtime reads along
        # and two points at one intensity with two frequencies is not a curve.
        levels = [level for level, _ in curve]
        assert levels[0] >= pub.LEAST_INTENSITY, row["name"]
        assert len(set(levels)) == len(levels), row["name"]
        assert levels == sorted(levels)
        # Strictly falling, because this is the axis the site term map is read
        # along and a flat step in it has no inverse.
        rates = [rate for _, rate in curve]
        assert all(a > b for a, b in zip(rates, rates[1:])), row["name"]
        # And it reaches the shaking a policy is written on.
        assert levels[-1] >= 6.0, row["name"]


def test_outside_the_published_points_the_shape_stays_ours(published) -> None:
    """A published curve read past its own ends says nothing, and is not asked.

    J-SHIS publishes a handful of points per place. Below the weakest of them a
    reading of the curve is flat by construction, and following that flatness
    would price intensity VI and intensity VIII at the same frequency, which is
    what the first version of this map did. Outside their range the correction
    is a constant and the shape is ours.
    """
    priced = osaka_curve()
    published(curve=priced)
    subject = {"latitude": OSAKA[0], "longitude": OSAKA[1]}
    weakest = priced[0][0]
    assert weakest > 6.5, "this test is about levels below the published points"
    below = [sh.rate_at_least(subject, x / 10) for x in range(50, int(weakest * 10))]
    # Strictly falling, not flat: our own shape, moved.
    assert all(a > b for a, b in zip(below, below[1:]))
    # And moved by the same amount everywhere below, which is the offset the
    # weakest published point implies.
    offset = weakest - sh.ours_at(subject, weakest)
    for x in range(50, int(weakest * 10)):
        assert x / 10 - sh.ours_at(subject, x / 10) == pytest.approx(offset, abs=0.01)


def test_an_options_value_is_not_a_country(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``--limit 250`` asks for 250 places, not for a country called 250.

    The model file is pointed somewhere else first. A test that runs the build
    writes whatever the build returns, and this one returns nothing; the first
    version of it emptied the shipped model of a country.
    """
    import io
    from contextlib import redirect_stderr

    monkeypatch.setattr(pub, "OUT", tmp_path / "published.json")

    def never(*args, **kwargs):
        raise AssertionError("a refused command line fetched something")

    monkeypatch.setattr(pub, "build", never)

    # A bad option is refused before any country runs, so nothing is fetched.
    # The stub above is what says so: reading the arguments in two passes made
    # "--nope" an empty list of countries, which meant every country.
    for argv in (["--nope"], ["--limit"]):
        said = io.StringIO()
        with redirect_stderr(said):
            assert pub.main(argv) == 2, argv
        assert said.getvalue().strip()

    asked: list[tuple[str, int | None]] = []

    def watch(code: str, *, limit=None, keep=None, save=None):
        asked.append((code, limit))
        return pub._record(code, [], [])

    monkeypatch.setattr(pub, "build", watch)
    assert pub.main(["JP", "--limit", "250"]) == 0
    assert asked == [("JP", 250)]
    # And with no country named, every country with a source wired.
    asked.clear()
    assert pub.main([]) == 0
    assert [code for code, _ in asked] == list(pub.SOURCES)


# ---------------------------------------------------------------------------
# Reading what J-SHIS actually publishes
# ---------------------------------------------------------------------------


def a_mesh(**over) -> dict[str, float]:
    """A J-SHIS mesh's properties, shaped like the real ones at Osaka."""
    said = {
        "T50_P39_SV": 42.6, "T50_P39_SI": 5.5,
        "T50_P10_SV": 71.7, "T50_P10_SI": 5.9,
        "T50_P05_SV": 91.6, "T50_P05_SI": 6.1,
        "T50_P02_SV": 130.8, "T50_P02_SI": 6.5,
        "T30_P06_SV": 75.9, "T30_P06_SI": 5.9,
        "T30_P03_SV": 95.0, "T30_P03_SI": 6.1,
        "T30_I45_PS": 0.894054, "T30_I50_PS": 0.732141,
        "T30_I55_PS": 0.304449, "T30_I60_PS": 0.051364,
    }
    said.update(over)
    return said


def read_mesh(said: dict[str, float], monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(pub, "_get", lambda url, **kw: {"features": [{"properties": said}]})
    return pub.jshis_curve(34.6937, 135.5023)


def test_the_frequent_end_of_the_japanese_curve_is_read_too(monkeypatch) -> None:
    """The velocities J-SHIS publishes are all rarer than a policy's triggers.

    At Osaka they begin at a return period of 101 years. Its intensity
    thresholds reach 13, which is where cover is actually written, so a curve
    built from the velocities alone left the whole priced band to our own shape
    extrapolated.
    """
    curve = read_mesh(a_mesh(), monkeypatch)
    assert curve is not None
    periods = sorted(round(1 / rate) for _, rate in curve)
    assert periods[0] <= 15, periods       # the frequent end is in
    assert max(periods) >= 2000            # and the rare end is still there
    levels = sorted(pub.mmi_from_pgv(v) for v, _ in curve)
    assert levels[0] < 6.5 and levels[-1] > 9.0

    # A curve falls: no stronger shaking is more frequent than a weaker one.
    ordered = sorted(curve)
    assert all(a[1] >= b[1] for a, b in zip(ordered, ordered[1:]))


def test_an_intensity_is_converted_by_the_sites_own_pairs(monkeypatch) -> None:
    """No general rule between the two scales is used, or needed.

    J-SHIS gives a velocity and a JMA intensity at each of its own probability
    levels, so those pairs are that mesh's relation between them. Moving the
    pairs moves where an intensity threshold lands, which is the whole point:
    the conversion is the publisher's, at the publisher's own mesh.
    """
    plain = read_mesh(a_mesh(), monkeypatch)
    # The same model, with every velocity doubled and the intensities unchanged.
    doubled = read_mesh(a_mesh(**{k: v * 2 for k, v in a_mesh().items()
                                  if k.endswith("_SV")}), monkeypatch)
    assert plain is not None and doubled is not None
    assert min(v for v, _ in doubled) == pytest.approx(2 * min(v for v, _ in plain), rel=0.02)


def test_one_intensity_with_two_velocities_is_one_point(monkeypatch) -> None:
    """Osaka answers 5.9 with both 71.7 and 75.9, and that is not two points.

    They come from a thirty year and a fifty year level of the same model. Kept
    apart they put a zero in the denominator of the conversion, which ended a
    two hour build at its 970th place.
    """
    curve = read_mesh(a_mesh(), monkeypatch)
    assert curve is not None                       # it used to raise here
    # And a mesh whose intensities are all the same value is refused, not divided by.
    flat = a_mesh(**{k: 5.5 for k in a_mesh() if k.endswith("_SI")})
    assert read_mesh(flat, monkeypatch) is not None       # the velocities still stand
    assert pub._velocity_of([(5.5, 40.0), (5.5, 50.0)], 4.5) is None


def test_one_bad_place_does_not_end_the_build(monkeypatch, tmp_path) -> None:
    """A publisher's answer is data, and data surprises."""
    monkeypatch.setattr(pub, "OUT", tmp_path / "published.json")
    seen: list[str] = []

    def fetch(latitude, longitude):
        seen.append(f"{latitude},{longitude}")
        if len(seen) == 2:
            raise ZeroDivisionError("float division by zero")
        return [[10.0, 0.05], [40.0, 0.005]]

    monkeypatch.setitem(pub.SOURCES["JP"], "fetch", fetch)
    monkeypatch.setitem(pub.SOURCES["JP"], "pause", 0.0)
    built = pub.build("JP", limit=4)
    assert len(seen) == 4                  # it kept going
    assert len(built["points"]) == 3
    assert len(built["missed"]) == 1       # and said which one it lost


def test_one_place_per_coordinate_is_fetched() -> None:
    """Two names at one point are one point, and one curve.

    Japan offers Choshi and Hasaki at the same coordinate, and Furano twice
    under two spellings. Without this the build asks J-SHIS for the same mesh
    twice and the model file carries the answer twice, which a search working in
    kilometres does not mind and a reader of the file reasonably does.
    """
    for code in pub.SOURCES:
        where = pub.places_of(code)
        seen = {(round(la, 4), round(lo, 4)) for _n, la, lo, _p in where}
        assert len(seen) == len(where), code
        # Largest first, so a limit takes the places most people live in.
        people = [p for *_r, p in where]
        assert people == sorted(people, reverse=True), code


def test_every_american_place_offered_has_a_model_that_covers_it() -> None:
    """The United States is three published models, not one.

    CONUS stops at the border of the lower forty eight. This build asked it
    about Anchorage and was told there is no curve there: a city four hundred
    kilometres from the 1964 rupture, for which the USGS has published a model
    since 2007. Honolulu, the largest American place after the CONUS two
    hundred, came back the same way, and so did forty six other Hawaiian
    places and four more Alaskan ones.

    The claim the build rests on is that every American place this product
    offers falls inside exactly one of the three footprints, so that asking the
    model whose box contains a point is the same as asking the model that
    covers it. That is a claim about a list of places, which is checked here
    rather than assumed in a comment.
    """
    counted: dict[str, int] = {}
    for name, latitude, longitude, _people in pub.places_of("US"):
        boxes = [model for model, _named, (s, n, w, e) in pub.USGS_MODELS
                 if s <= latitude <= n and w <= longitude <= e]
        assert len(boxes) == 1, f"{name} at {latitude},{longitude} is in {boxes}"
        counted[boxes[0]] = counted.get(boxes[0], 0) + 1
    # And all three are actually used, so a box that stopped matching anything
    # would be noticed rather than quietly carried.
    assert set(counted) == {model for model, *_ in pub.USGS_MODELS}, counted


def test_a_point_no_model_covers_is_not_asked_of_one(monkeypatch) -> None:
    """Outside all three, the answer is no curve, and no request is made.

    The alternative is asking the model of the lower forty eight about a point
    in the middle of the Pacific and taking whatever it says, which is how a
    place gets priced by a model that has never seen it.
    """
    def never(*_args, **_kwargs):
        raise AssertionError("a point outside every model was asked for anyway")

    monkeypatch.setattr(pub, "_get", never)
    assert pub.usgs_model(0.0, 0.0) is None
    assert pub.usgs_curve(0.0, 0.0) is None
    # Guam, which this product does not offer and which no box claims.
    assert pub.usgs_model(13.4443, 144.7937) is None


def test_a_curve_says_which_revision_drew_it() -> None:
    """A source line that names the family names the wrong model two ways.

    "USGS National Seismic Hazard Model" is true of Anchorage, Honolulu and
    Brooklyn alike and tells a buyer in any of them nothing. The country names
    the family and the point names the revision.
    """
    country = {"publisher": "USGS National Seismic Hazard Model"}
    assert pub._said(country, {"model": "Alaska 2023 R1"}) == (
        "USGS National Seismic Hazard Model, Alaska 2023 R1")
    # A point from before the build learned this still reads as the family.
    assert pub._said(country, {}) == "USGS National Seismic Hazard Model"
    assert pub._said({}, {"model": "Hawaii 2021 R1"}) == "Hawaii 2021 R1"
    assert pub._said({}, {}) == ""


def test_a_point_fetched_before_this_is_stamped_without_asking_again(monkeypatch, tmp_path) -> None:
    """Which model covers a place is arithmetic, not a request.

    The two hundred American curves already in the file were fetched before the
    build could name the model behind them. Refetching them to learn a fact
    that follows from their coordinates would cost an hour of a public service's
    time for nothing.
    """
    monkeypatch.setattr(pub, "OUT", tmp_path / "published.json")
    asked: list[str] = []

    def fetch(latitude, longitude):
        asked.append(f"{latitude},{longitude}")
        return [[10.0, 0.05], [40.0, 0.005]]

    monkeypatch.setitem(pub.SOURCES["US"], "fetch", fetch)
    monkeypatch.setitem(pub.SOURCES["US"], "pause", 0.0)
    kept = [{"name": name, "latitude": round(la, 4), "longitude": round(lo, 4),
             "curve": [[10.0, 0.05], [40.0, 0.005]]}
            for name, la, lo, _p in pub.places_of("US")[:3]]
    built = pub.build("US", limit=3, keep=kept)
    assert asked == [], "a stored point was fetched again to learn its model"
    assert all(row.get("model") for row in built["points"]), built["points"]


def test_a_refusal_carries_both_models_own_figures(published) -> None:
    """The residual is the right thing to gate on and not the whole story.

    A published curve our own events cannot be brought within a factor of two
    of is refused, and the sentence a buyer read named that factor alone:
    "disagree by a factor of 6". Six is what survived the correction, which is
    not what the two models say. At Anchorage the USGS Alaska model puts
    intensity VII at once in 87 years and our own events reach once in 11,119,
    a hundred and twenty eight times apart, and the residual after the map is
    clamped is six. Elsewhere the residual is the larger of the two numbers.
    Either way it answers a different question than the one a reader is asking.

    So both figures are carried, uncorrected, straight off the two curves.
    """
    published(curve=((9.0, 0.5), (9.9, 0.2)))
    subject = {"latitude": OSAKA[0], "longitude": OSAKA[1]}
    term = sh.site_term(subject)
    assert term is not None

    # Each is its own curve read at intensity VII, and nothing else.
    theirs = pub.rate_at(tuple(sh._mapping(round(OSAKA[0], 4), round(OSAKA[1], 4)) and
                               ((9.0, 0.5), (9.9, 0.2))), 7.0)
    assert term["theirs_one_in"] == round(1.0 / theirs)
    ours = sh.raw_rate_at_least(subject, 7.0)
    assert term["ours_one_in"] == round(1.0 / ours)
    # And the residual is a third number, not one of these two.
    assert term["worst_ratio"] not in (term["ours_one_in"], term["theirs_one_in"])


def test_the_refusal_a_buyer_reads_puts_the_two_figures_side_by_side(monkeypatch) -> None:
    """The sentence itself, from the code that builds it.

    Written out rather than paraphrased, because the number a buyer is given
    for their own address is the thing being fixed here.
    """
    from clause.perils import quake as qk

    peril = qk.Earthquake()
    monkeypatch.setattr(peril, "in_turkey", lambda *a, **k: False)
    monkeypatch.setattr(peril, "priced_at", lambda *a, **k: {"name": "Anchorage"})
    # quake.py imports shaking inside the function, so the patch goes on the
    # module it reaches for rather than on a name quake.py does not hold.
    monkeypatch.setattr(sh, "beyond_reconciling", lambda *a, **k: True)
    monkeypatch.setattr(sh, "site_term", lambda *a, **k: {
        "publisher": "USGS National Seismic Hazard Model, Alaska 2023 R1",
        "worst_ratio": 6.07, "theirs_one_in": 87, "ours_one_in": 11119,
        "place": "Anchorage", "distance_km": 0.0, "shift": 2.0, "at_the_limit": True})

    with pytest.raises(ValueError) as refused:
        peril.validate_subject({"latitude": 61.2181, "longitude": -149.9003,
                                "radius_km": 50, "index": "shaking"})
    said = str(refused.value)
    assert "Alaska 2023 R1" in said
    assert "once in 87 years" in said
    assert "once in 11119" in said
    # Plain digits. This sentence is translated by pattern, so an English
    # thousands separator would read as a decimal point to half its readers.
    assert "11,119" not in said
    assert "factor of 6" in said


def test_whose_country_and_which_grid_are_two_questions() -> None:
    """They came apart the moment a published curve reached past the catalogue.

    Honolulu is in the United States and outside the box the American
    catalogue was fitted on: CONUS, 24 to 50 north. Cover there was refused
    with "no tested earthquake model covers this location yet", which was true
    of our catalogue and not true of the ground, because the USGS has published
    a Hawaii model since 2021 and this build now holds its curve.

    The two answers have to differ. A grid asked about a point outside its own
    box sums zero cells and answers zero, which reads as "no earthquakes here"
    and means "this grid is not about here"; pricing Honolulu on that would
    have quoted no hazard at all rather than the background floor.
    """
    from clause.perils.quake import Earthquake

    peril = Earthquake()
    honolulu = {"latitude": 21.3069, "longitude": -157.8583, "radius_km": 50,
                "index": "shaking"}
    inland = {"latitude": 40.7128, "longitude": -74.0060, "radius_km": 50,
              "index": "shaking"}

    # In the country, out of the grid.
    assert peril.risk_country(honolulu) == "US"
    assert peril.grid_model(honolulu) is None
    # In both.
    assert peril.risk_country(inland) == "US"
    assert peril.grid_model(inland) is not None

    # And the grid, asked anyway, really does answer zero rather than a rate.
    grid = peril.grid_model(inland)
    assert grid is not None and not grid.in_box(21.3069, -157.8583)
    assert grid.rate_reference_within(21.3069, -157.8583, 50.0) == 0.0


def test_hawaii_is_priced_and_alaska_says_why_it_is_not() -> None:
    """The two outcomes this opened, both measured against the shipped file.

    Honolulu reconciles: the Hawaii model and our own events, corrected, agree
    across the fit band. Anchorage does not, and it is not close: the USGS puts
    intensity VII there at once in 87 years and our catalogue, which has no
    Alaskan events at all and answers with the global floor, reaches once in
    11,119. The existing guard refuses it, and the sentence now says both.
    """
    from clause.perils.quake import Earthquake

    peril = Earthquake()
    shipped = json.loads(pub.OUT.read_text(encoding="utf-8"))
    held = {row["name"] for row in shipped.get("US", {}).get("points", [])}
    if not {"Honolulu", "Anchorage"} <= held:
        pytest.skip("the published build has not reached Hawaii and Alaska yet")

    honolulu = {"latitude": 21.3069, "longitude": -157.8583, "radius_km": 50,
                "index": "shaking"}
    term = sh.site_term(honolulu)
    assert term is not None and "Hawaii 2021 R1" in term["publisher"]
    assert term["worst_ratio"] <= sh.MOST_DISAGREEMENT
    peril.validate_subject(dict(honolulu, place="Honolulu"))   # priced

    anchorage = {"latitude": 61.2181, "longitude": -149.9003, "radius_km": 50,
                 "index": "shaking"}
    term = sh.site_term(anchorage)
    assert term is not None and "Alaska 2023 R1" in term["publisher"]
    assert term["worst_ratio"] > sh.MOST_DISAGREEMENT
    with pytest.raises(ValueError) as refused:
        peril.validate_subject(dict(anchorage, place="Anchorage"))
    said = str(refused.value)
    assert "Alaska 2023 R1" in said and "once in 87 years" in said
