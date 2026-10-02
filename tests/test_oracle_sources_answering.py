"""Telling a source that answered nothing apart from a source that failed.

All three findings here were measured on the live deployment, whose own
/api/health was reporting three of its sources as failing:

    "failing": {
      "EMSC":      "unreadable: JSONDecodeError: Expecting value: line 1 column 1",
      "ERA5":      "HTTPError: HTTP Error 403: Forbidden",
      "ERA5-Land": "HTTPError: HTTP Error 403: Forbidden"
    },
    "readings_written": 0,
    "openmeteo_subscription": true

1. EMSC was not failing. The portal answers 204 with an empty body when no
   event in the window matched, which is an answer: nothing happened. Read as
   JSON it raised, and a working agency was filed as unreadable on every quiet
   round.

2. The reanalyses were refused by the host the subscription pays for, not by
   Open-Meteo. The same query is public and keyless and answers 200; measured
   from this machine it returned fourteen days and a strongest wind of
   31.0 km/h for the window the live deployment was reading nothing for. With
   both models silent, storm and drought cover could not settle at all.

3. Because `trouble` was one dict for every source, either of the above left a
   key standing in it permanently, and the window-closing guard reads that
   dict: `if not self.trouble: reading.measured_through = now`. So no window
   ever closed for any reference of any peril, and a drought policy's silence
   was explained by naming an earthquake agency.
"""

from __future__ import annotations

import contextlib
import pathlib
import time
import urllib.error

import pytest

from clause.oracle import access, quake
from clause.oracle.feed import Feed

FEEDS = pathlib.Path(__file__).parent / "feeds"

EPICENTRE = (37.29, 37.04)
WINDOW = (1675640000.0, 1675690000.0)
MEASURED = ("earthquake.usgs.gov/fdsnws/event/1/query"
            "?lat=37.29&lon=37.04&radius_km=100")
RIZE = (41.01933, 40.442226)
WET_WINDOW = (1756684800.0, 1760054400.0)
WIND_REF = ("archive-api.open-meteo.com/v1/archive"
            "?index=wind&lat=41.0193&lon=40.4422")

ALL_THREE = {"earthquake.usgs.gov": "usgs_kahramanmaras.json",
             "seismicportal": "emsc_kahramanmaras.json",
             "afad": "afad_kahramanmaras.json"}


def canned(**by_host: str):
    """A fetch answering from recorded responses. "down" raises; "" answers
    with no body at all, which is what EMSC's 204 looks like to a reader."""
    def fetch(url: str) -> tuple[bytes, str]:
        for fragment, name in by_host.items():
            if fragment in url:
                if name == "down":
                    raise OSError("connection refused")
                if name == "":
                    return b"", url
                return (FEEDS / name).read_bytes(), url
        raise OSError(f"nothing recorded for {url}")
    return fetch


# -- a portal that answers "nothing happened" -------------------------------

@pytest.mark.parametrize("body", [b"", b"   ", b"\n", b"  \r\n  "])
def test_an_empty_body_from_the_portal_is_no_events(body: bytes) -> None:
    assert quake.read_emsc(body, "https://www.seismicportal.eu/x") == []


def test_a_quiet_emsc_is_not_a_failing_emsc() -> None:
    feed = Feed(fetch=canned(**{"earthquake.usgs.gov": "usgs_kahramanmaras.json",
                                "seismicportal": "", "afad": "afad_kahramanmaras.json"}))
    feed.earthquake(latitude=EPICENTRE[0], longitude=EPICENTRE[1],
                    radius_km=100.0, since=WINDOW[0], until=WINDOW[1])
    assert "EMSC" not in feed.trouble
    assert "EMSC" not in feed.last_trouble


def test_a_quiet_round_still_closes_its_window() -> None:
    """The consequence of the one above, and the reason it mattered: the
    window-closing guard reads the trouble dict."""
    chain = _chain(MEASURED)
    feed = Feed(fetch=canned(**{"earthquake.usgs.gov": "usgs_kahramanmaras.json",
                                "seismicportal": "", "afad": "afad_kahramanmaras.json"}))
    feed.poll(chain, now=WINDOW[1])
    assert chain.readings[MEASURED].measured_through == WINDOW[1]


# -- a subscription that refuses what the public host serves -----------------

def paid_refuses(code: int, *, public_body: bytes = b"{}",
                 public_code: int | None = None):
    """An opener that turns the subscription host away and serves the other."""
    asked: list[str] = []

    @contextlib.contextmanager
    def opener(request, timeout=0):
        asked.append(request.full_url)
        refusing = access.OPENMETEO_PAID in request.full_url
        status = code if refusing else public_code
        if status is not None:
            raise urllib.error.HTTPError(request.full_url, status, "refused",
                                         {}, None)  # type: ignore[arg-type]

        class Reply:
            def read(self, _n: int) -> bytes:
                return public_body

            def geturl(self) -> str:
                return request.full_url

        yield Reply()

    return opener, asked


@pytest.mark.parametrize("code", [400, 401, 402, 403, 429, 500])
def test_a_refused_paid_query_is_asked_again_without_the_key(
        monkeypatch, code: int) -> None:
    """Whatever status the subscription host chooses. A key it does not know
    answers 400, the live deployment's key answered 403, a spent quota 429, so
    no list of codes would have covered it."""
    public = "archive-api.open-meteo.com/v1/archive?latitude=41.0&daily=rain"
    monkeypatch.setenv(access.OPENMETEO_KEY, "s3cret")
    access.forget_refusal()
    opener, asked = paid_refuses(code, public_body=b'{"daily":{}}')
    monkeypatch.setattr(quake.urllib.request, "urlopen", opener)

    body, reference = quake.fetch(public)

    assert body == b'{"daily":{}}'
    assert len(asked) == 2
    assert access.OPENMETEO_PAID in asked[0] and "apikey=s3cret" in asked[0]
    assert access.OPENMETEO_PAID not in asked[1] and "apikey" not in asked[1]
    # What goes on the record is still the query anybody can repeat.
    assert reference == public
    assert access.refusal()["code"] == code


def test_the_refusal_is_said_but_the_key_is_not(monkeypatch) -> None:
    public = "archive-api.open-meteo.com/v1/archive?latitude=41.0&daily=rain"
    monkeypatch.setenv(access.OPENMETEO_KEY, "s3cret")
    access.forget_refusal()
    opener, _asked = paid_refuses(403)
    monkeypatch.setattr(quake.urllib.request, "urlopen", opener)
    quake.fetch(public)
    said = access.refusal()
    assert said["code"] == 403 and said["at"] > 0
    assert "s3cret" not in repr(said)


def test_a_query_the_public_host_also_refuses_is_raised(monkeypatch) -> None:
    """The fallback must not swallow a query that is genuinely wrong: the same
    query is asked publicly, so a malformed one refuses again and is raised."""
    public = "archive-api.open-meteo.com/v1/archive?latitude=not-a-number"
    monkeypatch.setenv(access.OPENMETEO_KEY, "s3cret")
    opener, asked = paid_refuses(400, public_code=400)
    monkeypatch.setattr(quake.urllib.request, "urlopen", opener)
    with pytest.raises(urllib.error.HTTPError):
        quake.fetch(public)
    assert len(asked) == 2


def test_without_a_subscription_nothing_is_asked_twice(monkeypatch) -> None:
    """A keyless deployment asks the public host once. A refusal there is the
    source refusing, and retrying it would only spend the same quota again."""
    public = "archive-api.open-meteo.com/v1/archive?latitude=41.0&daily=rain"
    monkeypatch.delenv(access.OPENMETEO_KEY, raising=False)
    access.forget_refusal()
    opener, asked = paid_refuses(403, public_code=403)
    monkeypatch.setattr(quake.urllib.request, "urlopen", opener)
    with pytest.raises(urllib.error.HTTPError):
        quake.fetch(public)
    assert len(asked) == 1
    assert access.refusal() == {}


# -- one source's outage is not another reference's silence ------------------

def _chain(reference: str, field: str = "max_magnitude"):
    import threading

    from clause.chain.world import EdgeReading

    class FakeChain:
        def __init__(self) -> None:
            self.lock = threading.RLock()
            self.readings = {reference: EdgeReading(
                reference=reference, fields={field: 0.0, "events": 0},
                attested_at=0.0, publisher="USGS", index_field=field)}
            self.written: list[tuple[str, str, float]] = []

        def attest(self, ref, name, value, *, final=True):
            self.written.append((ref, name, value))
            self.readings[ref].fields[name] = value
            return self.readings[ref]

    return FakeChain()


def test_a_reanalysis_that_is_down_does_not_freeze_an_earthquake_window() -> None:
    feed = Feed(fetch=canned(**{"archive-api": "down"}))
    # A weather read first, which is what puts ERA5 in the trouble dict.
    feed.weather(latitude=RIZE[0], longitude=RIZE[1], since=WET_WINDOW[0],
                 until=WET_WINDOW[1], index_field="wind_24h_kmh")
    assert "ERA5" in feed.trouble

    chain = _chain(MEASURED)
    feed.fetch = canned(**ALL_THREE)
    feed.poll(chain, now=WINDOW[1])
    assert chain.readings[MEASURED].measured_through == WINDOW[1], (
        "a reanalysis being down closed nothing for an earthquake reference")


def test_an_agency_that_is_down_does_not_freeze_a_weather_window() -> None:
    feed = Feed(fetch=canned(**{"earthquake.usgs.gov": "down",
                                "seismicportal": "down", "afad": "down"}))
    feed.earthquake(latitude=EPICENTRE[0], longitude=EPICENTRE[1],
                    radius_km=100.0, since=WINDOW[0], until=WINDOW[1])
    assert "USGS" in feed.trouble

    chain = _chain(WIND_REF, "wind_24h_kmh")
    feed.fetch = canned(**{"archive-api": "openmeteo_rize.json"})
    feed.poll(chain, now=WET_WINDOW[1])
    assert chain.readings[WIND_REF].measured_through == WET_WINDOW[1]


def test_a_silence_names_only_the_sources_that_were_asked() -> None:
    """A drought policy that has not moved was being explained by naming an
    earthquake agency that is not one of its sources."""
    feed = Feed(fetch=canned(**{"earthquake.usgs.gov": "down",
                                "seismicportal": "down", "afad": "down"}))
    feed.earthquake(latitude=EPICENTRE[0], longitude=EPICENTRE[1],
                    radius_km=100.0, since=WINDOW[0], until=WINDOW[1])

    feed.fetch = canned(**{"archive-api": "down"})
    quiet = feed.weather(latitude=RIZE[0], longitude=RIZE[1],
                         since=WET_WINDOW[0], until=WET_WINDOW[1],
                         index_field="wind_24h_kmh")
    assert "ERA5" in quiet.why
    for agency in ("USGS", "EMSC", "AFAD"):
        assert agency not in quiet.why


def test_the_loud_failure_stays_loud() -> None:
    """The one thing that must not change: an unreachable source is still not
    a reading of zero, and the window still does not close behind it."""
    chain = _chain(MEASURED)
    feed = Feed(fetch=canned(**{"earthquake.usgs.gov": "down",
                                "seismicportal": "down", "afad": "down"}))
    feed.poll(chain, now=WINDOW[1])
    assert chain.readings[MEASURED].measured_through == 0.0
    assert not chain.written

# -- and not paying for the same refusal twice a round ----------------------

def test_the_subscription_is_left_alone_after_it_refuses(monkeypatch) -> None:
    """Asked and refused is two requests for one reading. What the real host
    actually says is a fact about the plan rather than about the moment:

        403 {"error":true,"reason":"This API endpoint requires the API
             Professional or Enterprise plan"}

    so it will be true for every query until somebody changes the plan.
    """
    public = "archive-api.open-meteo.com/v1/archive?latitude=41.0&daily=rain"
    monkeypatch.setenv(access.OPENMETEO_KEY, "s3cret")
    access.forget_refusal()
    assert access.OPENMETEO_PAID in access.reaching(public)

    access.refused(403)
    assert access.reaching(public) == public, "it asked the paid host again"
    assert access.refusal()["resting"] is True


def test_it_tries_again_once_the_hour_is_up(monkeypatch) -> None:
    """So a plan that is upgraded is picked up without a restart.

    The offset is an hour written out, not REST_AFTER_A_REFUSAL + 1: asking
    the constant about itself passes whatever the constant is, and this file
    exists because of a different assertion that did exactly that.
    """
    assert access.REST_AFTER_A_REFUSAL == 3600.0, (
        "the rest is no longer an hour; this file says an hour in three places")
    public = "archive-api.open-meteo.com/v1/archive?latitude=41.0&daily=rain"
    monkeypatch.setenv(access.OPENMETEO_KEY, "s3cret")
    access.forget_refusal()
    access.refused(403, now=time.time() - 3601)
    assert access.OPENMETEO_PAID in access.reaching(public)
    assert access.refusal()["resting"] is False


def test_it_is_still_resting_just_before_the_hour(monkeypatch) -> None:
    public = "archive-api.open-meteo.com/v1/archive?latitude=41.0&daily=rain"
    monkeypatch.setenv(access.OPENMETEO_KEY, "s3cret")
    access.forget_refusal()
    access.refused(403, now=time.time() - 3500)
    assert access.reaching(public) == public


def test_only_one_request_is_made_while_it_rests(monkeypatch) -> None:
    """The point of it, measured as requests rather than as a flag."""
    public = "archive-api.open-meteo.com/v1/archive?latitude=41.0&daily=rain"
    monkeypatch.setenv(access.OPENMETEO_KEY, "s3cret")
    access.forget_refusal()
    opener, asked = paid_refuses(403, public_body=b'{"daily":{}}')
    monkeypatch.setattr(quake.urllib.request, "urlopen", opener)

    quake.fetch(public)
    assert len(asked) == 2, "the first read asks both hosts"
    quake.fetch(public)
    quake.fetch(public)
    assert len(asked) == 4, "every later read should ask the public host once"
    assert all(access.OPENMETEO_PAID not in one for one in asked[2:])


def test_a_deployment_with_no_key_is_untouched(monkeypatch) -> None:
    monkeypatch.delenv(access.OPENMETEO_KEY, raising=False)
    access.forget_refusal()
    public = "archive-api.open-meteo.com/v1/archive?latitude=41.0&daily=rain"
    assert access.reaching(public) == public
    access.refused(403)
    assert access.reaching(public) == public
