"""What a marketplace makes of a policy token.

The image was checked by looking at it. The metadata was not, and metadata is
what a wallet, an explorer and a marketplace actually read. Each test here
names a way the reading goes wrong: a value too long for the chip it is
printed in gets an ellipsis instead of an end, a number with no display type
is printed raw, a trait that differs for every token is noise in a rarity
count, and a token with no link back is a picture of a record nobody can
reach.
"""

from __future__ import annotations

import datetime as dt

import pytest

import clause.api.app as app_module
from clause.api.app import token_metadata
from clause.chain import Chain, ChainConfig
from clause.pricing import PricingEngine
from clause.protocol import Pool
import clause.perils  # noqa: F401  (registers the perils)

#: A trait is printed in a chip about this wide. The terms hash is the one
#: value that cannot be shortened without ceasing to be the hash.
CHIP = 42
LONG_BY_NATURE = {"Terms hash"}


def a_policy(peril_key: str, subject: dict, limit: float, term_days: float):
    pool = Pool(engine=PricingEngine(trials=200, seed=5))
    pool.deposit("lp", 500_000_000.0)
    chain = Chain(pool, ChainConfig(seed=5))
    policy = pool.write(peril_key=peril_key, subject=subject, limit=limit,
                        term_days=term_days, holder="holder")
    chain.register(policy)
    assert "token" in policy.metadata, "the chain did not mint the token"
    return policy


def every_peril():
    """One policy of each kind, since each draws its own subject line."""
    later = (dt.date.today() + dt.timedelta(days=20)).isoformat()
    return [
        a_policy("earthquake",
                 {"latitude": 40.99, "longitude": 29.03, "radius_km": 50.0}, 500_000, 365),
        a_policy("storm", {"latitude": 41.02, "longitude": 28.77, "place": "Silivri"},
                 100_000, 365),
        a_policy("drought", {"station": "TR-KONYA", "distance_km": 6, "hectares": 50},
                 25_000, 180),
        a_policy("flight_delay",
                 {"route": "TK-IST-AMS", "flight_number": "TK1979", "departure_date": later},
                 1_000, 1),
        a_policy("vehicle_flood",
                 {"latitude": 41.01, "longitude": 28.98, "place": "Beşiktaş", "value": 40000},
                 40_000, 365),
    ]


@pytest.fixture(scope="module")
def tokens():
    return [(policy, token_metadata(policy)) for policy in every_peril()]


def test_no_attribute_is_too_long_for_the_chip_it_is_printed_in(tokens) -> None:
    too_long = [
        (meta["name"], a["trait_type"], str(a["value"]))
        for _, meta in tokens for a in meta["attributes"]
        if a["trait_type"] not in LONG_BY_NATURE and len(str(a["value"])) > CHIP
    ]
    assert not too_long, f"these would be shown with an ellipsis instead of an end: {too_long}"


def test_every_number_and_date_says_which_it_is(tokens) -> None:
    """A viewer formats a number it was told is a number, and prints the rest
    as it arrived: a raw float and a raw epoch both read as a mistake."""
    for _, meta in tokens:
        for a in meta["attributes"]:
            if isinstance(a["value"], bool):
                continue
            if isinstance(a["value"], (int, float)):
                assert a.get("display_type") in {"number", "date"}, \
                    f"{a['trait_type']} is a bare number"
        dates = {a["trait_type"]: a for a in meta["attributes"]
                 if a.get("display_type") == "date"}
        assert set(dates) == {"Starts", "Ends"}
        for a in dates.values():
            assert isinstance(a["value"], int), f"{a['trait_type']} is not an epoch"
        assert dates["Ends"]["value"] > dates["Starts"]["value"]


def test_who_holds_it_is_nowhere_on_the_token(tokens) -> None:
    """It used to be here, under "token", and this test used to require it:
    "it is still on the token itself". That was the earlier audit's half
    measure. Nothing authenticates the route this is served from and
    ClausePolicy's tokenURI points a block explorer at it, beside the wallet
    that holds the token, so an address here is the link from a person to
    their cover that removing holder from the public book was for. Whose it
    is, is the chain's to answer."""
    import json

    for policy, meta in tokens:
        values = [str(a["value"]) for a in meta["attributes"]]
        assert policy.holder not in values
        assert not any(a["trait_type"] == "Held by" for a in meta["attributes"])
        assert "owner" not in meta["token"]
        assert "burned_from" not in meta["token"]
        assert policy.holder not in json.dumps(meta)


def test_the_payment_ladder_is_written_out_where_it_is_read_in_full(tokens) -> None:
    """It is the substance of the bargain and it is three clauses long, so it
    belongs in the description and not in a chip that would cut it short."""
    for policy, meta in tokens:
        # The curve in the units the index is read in, which for drought is
        # millimetres and not the shares of the station's normal season that
        # the structure is stored as. The token says what the reading will say.
        steps = policy.peril.reading_curve(policy.subject, policy.curve).describe(
            policy.peril.unit_for(policy.subject))
        for step in steps:
            assert step in meta["description"], f"{step!r} is not in the description"
        assert not any(a["trait_type"] == "Pays at" for a in meta["attributes"])


def test_the_peril_is_a_label_and_not_a_sentence(tokens) -> None:
    """It is what a reader filters a collection by, and nobody filters by a
    sentence that says how the index is measured."""
    for _, meta in tokens:
        peril = next(a["value"] for a in meta["attributes"] if a["trait_type"] == "Peril")
        assert "," not in peril and len(peril) <= 20, peril


def test_the_token_links_back_to_the_record_it_is_about(tokens, monkeypatch) -> None:
    policy, _ = tokens[0]
    monkeypatch.setattr(app_module, "_SITE_ORIGIN", "https://clause.insure")
    assert token_metadata(policy)["external_url"] == \
        f"https://clause.insure/#/proof/{policy.policy_id}"
    # Running the API on its own, there is no site to point at, and an invented
    # link would be worse than none.
    monkeypatch.setattr(app_module, "_SITE_ORIGIN", "")
    assert "external_url" not in token_metadata(policy)
