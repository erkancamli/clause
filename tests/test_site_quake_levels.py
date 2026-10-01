"""A quake policy's steps move with the building, and the ladder said they did not.

structure() shifts the quake curve by the age of what is insured, on both
indexes: a flat in Türkiye built in 2019 or later pays from magnitude 5.5, and
the same flat built in 1975 pays from 5.2. The shaking rows were given the
policy's own points when this was found there; the magnitude rows never were.
They named 5.5, 6.5 and 7.0 whatever the policy said, read the curve at those
levels for the amounts, and answered the chance column at them too.

Driven on the live site for a flat built in 1975, with the magnitude index
chosen: the ladder read "A magnitude 5.5 to 6.5, 8,574 USDC" while the summary
row above it read "M5.2 8,574" -- the same money at a different level, on the
same screen, and the summary was the one telling the truth. The first row was
worse than inconsistent: "Nothing above magnitude 5.5 happens, nothing" is
false when a 5.3 pays 8,574.

The magnitude index is not a corner: it is offered to every buyer of quake
cover as "Magnitude within a circle", beside "Shaking at my address", on the
step where the place is chosen.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from conftest import page_assembled

SITE = Path(__file__).resolve().parent.parent / "site"


def without_comments(src: str) -> str:
    """The code, with what is written about it taken out.

    The comments here quote the sentences they replaced, so a plain search
    finds them and the test fails for the wrong reason. It did.
    """
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(?<![:\w])//[^\n]*", "", src)


PAGE = without_comments(page_assembled())
FLOW = without_comments((SITE / "app" / "60-cover-flow.js").read_text(encoding="utf-8"))
PLACES = without_comments((SITE / "app" / "65-place-lookup.js").read_text(encoding="utf-8"))


def test_no_quake_row_names_a_level_of_its_own() -> None:
    for gone in ("Nothing above magnitude 5.5 happens", "A magnitude 5.5 to 6.5",
                 "A magnitude 6.5 to 7.0", "A magnitude 7.0 or more"):
        assert f't("{gone}"' not in PAGE, gone
        assert gone not in PAGE, gone


def test_the_magnitude_rows_read_the_policys_own_points() -> None:
    at = FLOW.index('} else if(flow.peril==="quake"){')
    branch = FLOW[at:FLOW.index('} else if(flow.peril==="car"){', at)]
    assert "var mp=c.pts;" in branch
    for literal in ("5.5", "6.5", "7.0"):
        assert literal not in branch, f"{literal} is still written into the rows"


def test_the_amounts_are_read_at_those_points_too() -> None:
    """Not only the labels. shareAt was called at 5.5 and 6.5 on a curve whose
    first two steps are 5.2 and 6.2 for an older building."""
    at = FLOW.index('} else if(flow.peril==="quake"){')
    branch = FLOW[at:FLOW.index('} else if(flow.peril==="car"){', at)]
    assert "shareAt(c,mp[0][0])" in branch
    assert "shareAt(c,mp[1][0])" in branch


def test_the_chance_column_is_answered_at_the_policys_levels() -> None:
    """The third item of each row is the level the exceedance curve is read
    at, and it was the written-in number."""
    at = FLOW.index('} else if(flow.peril==="quake"){')
    branch = FLOW[at:FLOW.index('} else if(flow.peril==="car"){', at)]
    assert re.search(r"\*l,mp\[0\]\[0\]\]", branch)
    assert re.search(r"\*l,mp\[1\]\[0\]\]", branch)
    assert re.search(r"l,mp\[2\]\[0\]\]", branch)


def test_both_indexes_name_their_trigger_from_the_policy() -> None:
    """triggerSaid computed it for rain, wind and drought and wrote it in for
    the two quake indexes, which are the two where it actually moves."""
    assert 'pays from shaking of intensity VI' not in PAGE
    assert 'pays from magnitude 5.5' not in PAGE
    # Sliced between its own start and the branch after it: a non-greedy
    # pattern stops at the first closing brace, which is the one inside
    # "{level}", and so reads none of the branch it is asking about.
    at = PLACES.index('if(flow.peril==="quake"){ pts=structure().pts;')
    branch = PLACES[at:PLACES.index('if(flow.peril==="car")', at)]
    # fLevel, not f1: a level is always written to one decimal, in the
    # reader's own decimal mark. f1 drops a trailing zero.
    assert branch.count("fLevel.format(pts[0][0])") == 2, branch


def test_the_curves_note_names_it_too() -> None:
    assert "The step at 5.5 is your trigger" not in PAGE
    assert "The step at {level} is your trigger. Nothing below it pays" in PAGE


def test_the_ladder_and_the_summary_read_the_same_source() -> None:
    """They disagreed on screen because they read different things: the
    summary went through rungWords to the policy's own points, and the ladder
    had the numbers written in."""
    assert "var mp=c.pts;" in FLOW
    assert "function rungWords(level)" in PLACES
    # Both start from structure().
    assert "c=structure()" in FLOW
    assert "var c=structure(), pts=c.pts" in PLACES


def test_every_new_sentence_is_translated_and_keeps_its_level() -> None:
    want = {"A magnitude below {level}": ["{level}"],
            "A magnitude {from} to {to}": ["{from}", "{to}"],
            "A magnitude {level} or more": ["{level}"],
            "pays from shaking of intensity {level}": ["{level}"],
            "pays from magnitude {level}": ["{level}"]}
    for lang in ("tr", "es", "fr", "de", "ru", "ja"):
        strings = json.loads((SITE / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))["strings"]
        for key, holes in want.items():
            assert key in strings, (lang, key)
            assert strings[key] != key, (lang, key, "left in English")
            for hole in holes:
                assert hole in strings[key], (lang, key, hole, "cannot carry the level")


# ------------------------------------------- the table under the price


def test_the_price_table_shows_the_policys_own_steps() -> None:
    """It sampled six magnitudes from 5.0 to 7.5 whichever index was chosen.

    Read on the live site for the default cover, which is shaking at the
    address with steps at 6.9, 7.9 and 8.9: four rows said "-", the two that
    paid both said 17,242, the two upper steps were past the end of the grid
    and never appeared, and every row was labelled M, which is how a magnitude
    is written and not an intensity. A table headed "how this price was worked
    out" showed one of the three amounts the price is made of.
    """
    at = FLOW.index("function hazardRows()")
    quake = FLOW[FLOW.index('if(flow.peril==="quake"){', at):
                 FLOW.index('} else if(flow.peril==="car"){', at)]
    assert "[5.0,5.5,6.0,6.5,7.0,7.5]" not in quake, "the written-in grid is back"
    assert "c.pts.forEach" in quake
    assert "rungWords(pt[0])" in quake, "the level is not written the way its index writes it"
    assert "money(pt[1]*flow.limit)" in quake, "the amount is not the step's own"


def test_the_quake_table_is_built_like_the_rain_and_wind_ones() -> None:
    """Those two always read the policy's points; this one now does too."""
    at = FLOW.index("function hazardRows()")
    body = FLOW[at:FLOW.index("\n}", FLOW.index("drought", at))]
    assert body.count("c.pts.forEach") == 3, body.count("c.pts.forEach")


def test_a_step_pays_at_the_step_and_not_just_above_it() -> None:
    """The rows now read the curve at the policy's own points, exactly.

    They used to read it at 5.5 and 6.5, which for an older building sit above
    the first two steps, so the question of what happens at the point itself
    never arose. It does now: if shareAt stopped including the step it stands
    on, the second row would read "nothing" for every quake policy.
    """
    model = (SITE / "app" / "10-model.js").read_text(encoding="utf-8")
    at = model.index("function shareAt(c,level)")
    step = model[at:model.index("function priceIt", at)]
    assert 'if(c.shape==="step"){for(i=0;i<p.length;i++)if(level>=p[i][0])sh=p[i][1];' in step, \
        "shareAt no longer includes the step it is asked at"
    # And the curve these rows are drawn from is a step curve.
    assert 'quake:{shape:"step"' in model
    assert 'shake:{shape:"step"' in model


def test_a_level_has_one_spelling_on_the_screen() -> None:
    """f1 drops a trailing zero, because most of its sixty-odd uses are
    ratios and percentages where 7 is the right answer. A level is not one of
    those: the magnitude ladder read "A magnitude 6.5 to 7" and "A magnitude 7
    or more" beside a summary row reading "M7.0", two spellings of one number,
    adjacent, on the screen where the money moves.
    """
    fmt = (SITE / "app" / "15-formatting.js").read_text(encoding="utf-8")
    assert "fLevel=new Intl.NumberFormat(locale,{minimumFractionDigits:1,maximumFractionDigits:1})" in fmt
    # Nowhere that writes a peril level still goes through the general one.
    for src in (FLOW, PLACES):
        for written in re.findall(r"\{(?:level|from|to):f1\.format\([^)]*\)", src):
            raise AssertionError(f"a level still written with f1: {written}")


def test_a_magnitude_is_written_in_the_readers_own_decimal_mark() -> None:
    """rungWords used toFixed(1), which keeps the zero and loses the mark: a
    Turkish reader was shown M5.2 where every other number on the page is
    written 5,2."""
    assert 'level.toFixed(1)' not in PLACES
    assert '"M"+fLevel.format(level)' in PLACES


def test_a_rain_threshold_is_not_rounded_away_in_the_summary() -> None:
    """Driven on the live site for rain cover at Kadıköy, one screen said all
    three of these:

        the sentence   "If 47.6 mm or more of rain falls ..."
        the ladder     "47.6 mm or more in a day, 2,500 USDC"
        the summary    "48 mm 2,500 . 56 mm 6,000 . 62 mm 10,000"

    48 and 47.6 are not the same threshold. A reader of the summary would
    think a 47.8 mm day pays nothing, and it pays 2,500.
    """
    at = PLACES.index("function rungWords(level)")
    body = PLACES[at:PLACES.index("function triggerSaid", at)]
    assert 'if(flow.peril==="car")return fLevel.format(level)+" mm";' in body
    # The season's levels are hundreds of millimetres and round everywhere.
    assert 'if(flow.peril==="drought")return f0.format(Math.round(level))+" mm";' in body
    assert 'if(flow.peril==="storm")return f0.format(Math.round(level))+" km/h";' in body


def test_the_running_summary_spells_a_level_the_way_the_rest_does() -> None:
    at = PLACES.index("function triggerSaid")
    # To the next declaration, not to a word that happens to sit above it.
    body = PLACES[at:PLACES.index("\nfunction ", at + 1)]
    assert "toFixed(0)" not in body, "a level is still written outside the reader's own convention"
    assert "fLevel.format(pts[0][0])" in body
