"""The palette, measured rather than trusted.

Colour is the one part of an interface that looks finished while being
wrong. A tertiary grey that reads beautifully on the canvas can fail
against the card it actually sits in; an input border chosen to be
discreet can stop saying that the input is an input. Both happened here,
and neither was visible by looking.

So the tokens are read out of the stylesheet and the ratios computed:
text against every surface of its own theme, not just the page; control
borders against every surface they can be drawn on; the lines the
diagrams are drawn with, which WCAG counts as graphical objects; and the
primary button's face at its lightest and darkest point, because it is a
gradient and the label has to hold across all of it.

WCAG 2.2: 1.4.3 asks 4.5:1 of text and 3:1 of large text; 1.4.11 asks 3:1
of anything needed to identify a control or to understand a graphic.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

INDEX = Path(__file__).resolve().parent.parent / "site" / "index.html"

BODY_TEXT = 4.5
LARGE_TEXT = 3.0
NON_TEXT = 3.0


def _channel(v: float) -> float:
    v /= 255.0
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def rgb(colour: str) -> tuple[float, float, float]:
    colour = colour.strip()
    if colour.startswith("#"):
        h = colour[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = re.match(r"rgba?\(([^)]*)\)", colour)
    if not m:
        raise ValueError(f"not a colour: {colour!r}")
    parts = [float(p) for p in m.group(1).replace("/", ",").split(",")]
    return tuple(parts[:3])


def alpha(colour: str) -> float:
    m = re.match(r"rgba\(([^)]*)\)", colour.strip())
    if not m:
        return 1.0
    parts = [float(p) for p in m.group(1).split(",")]
    return parts[3] if len(parts) > 3 else 1.0


def over(fg: str, bg: str) -> tuple[float, float, float]:
    """What a translucent colour becomes once it is painted on something."""
    a, f, b = alpha(fg), rgb(fg), rgb(bg)
    return tuple(f[i] * a + b[i] * (1 - a) for i in range(3))


def luminance(c) -> float:
    r, g, b = c
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def ratio(fg, bg) -> float:
    """Contrast, with the foreground composited if it is translucent."""
    background = rgb(bg) if isinstance(bg, str) else bg
    front = over(fg, bg) if isinstance(fg, str) and isinstance(bg, str) else (
        rgb(fg) if isinstance(fg, str) else fg)
    a, b = luminance(front), luminance(background)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def mix(a: str, b: str, share: float):
    """`color-mix(in srgb, a share%, b)`, as the stylesheet writes it."""
    x, y = rgb(a), rgb(b)
    return tuple(x[i] * share + y[i] * (1 - share) for i in range(3))


def themes() -> dict[str, dict[str, str]]:
    """The token blocks, read out of the stylesheet as the browser sees them."""
    text = INDEX.read_text(encoding="utf-8")
    style = text[text.index("<style>"):text.index("</style>")]
    blocks = {
        "dark": style[style.index(":root{"):style.index("@media (prefers-color-scheme:light)")],
        "light": style[style.index(':root[data-theme="light"]{'):style.index("*{box-sizing")],
    }
    out = {}
    for name, block in blocks.items():
        tokens = dict(re.findall(r"--([a-z0-9-]+)\s*:\s*([^;}]+)", block))
        out[name] = {k: v.strip() for k, v in tokens.items()}
    return out


THEMES = themes()
# Every surface a word can land on, per theme. The canvas is the easy case;
# the failures live on the lightest surface in the dark theme and the
# darkest one in the light theme, which is where cards and wells are.
SURFACES = ("ground", "panel", "raised", "sunk")


@pytest.fixture(scope="module")
def palette():
    assert set(THEMES) == {"dark", "light"}
    for name, tokens in THEMES.items():
        missing = [k for k in ("ground", "panel", "raised", "sunk", "ink", "ink-2",
                               "ink-3", "signal", "signal-2", "edge-ctl", "art-line",
                               "signal-fill", "signal-on-fill")
                   if k not in tokens]
        assert not missing, f"{name} theme is missing {missing}"
    return THEMES


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("ink", ["ink", "ink-2", "ink-3"])
def test_every_text_tone_is_legible_on_every_surface(palette, theme, ink):
    """Tertiary text is still text. It is measured where it is worst."""
    tokens = palette[theme]
    for surface in SURFACES:
        got = ratio(tokens[ink], tokens[surface])
        assert got >= BODY_TEXT, (
            f"{theme} --{ink} ({tokens[ink]}) on --{surface} ({tokens[surface]}) "
            f"is {got:.2f}:1, below {BODY_TEXT}")


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_a_control_border_says_the_control_is_there(palette, theme):
    """1.4.11: what identifies a control has to be seen against its neighbour."""
    tokens = palette[theme]
    for surface in SURFACES:
        got = ratio(tokens["edge-ctl"], tokens[surface])
        assert got >= NON_TEXT, (
            f"{theme} --edge-ctl on --{surface} is {got:.2f}:1, below {NON_TEXT}")


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_the_diagrams_are_drawn_in_a_line_that_can_be_seen(palette, theme):
    """The illustrations carry meaning, so they are graphical objects."""
    tokens = palette[theme]
    for surface in ("ground", "panel", "sunk"):
        got = ratio(tokens["art-line"], tokens[surface])
        assert got >= NON_TEXT, (
            f"{theme} --art-line on --{surface} is {got:.2f}:1, below {NON_TEXT}")


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_the_primary_button_holds_its_label(palette, theme):
    """One flat fill, one label, and the label is white.

    The face used to be a gradient and the label near-black, chosen because
    ink measured 5.84:1 on the brand orange against white's 3.33:1. Both
    figures are correct and the choice they justified was wrong: in APCA,
    which handles a saturated warm hue where WCAG 2's luminance formula does
    not, that ink reads Lc +43.8 at the label's own band of the gradient and
    the white reads Lc -65.3. Readable body text starts at Lc 75, so the one
    the standard preferred was the one a reader could not read.

    The fill is deepened until white clears both scales at once, and this
    test now holds the thing that matters: whatever fills a primary button,
    its label must pass on the fill itself, with no gradient to hide in."""
    tokens = palette[theme]
    fill, label = tokens["signal-fill"], tokens["signal-on-fill"]
    got = ratio(label, rgb(fill))
    assert got >= BODY_TEXT, (
        f"{theme} primary button label {label} on --signal-fill {fill} "
        f"is {got:.2f}:1, below {BODY_TEXT}")
    # And the fill has to be distinguishable from the page behind it, which
    # is 1.4.11's job: a button nobody can see the edge of is not a button.
    for surface in SURFACES:
        edge = ratio(fill, tokens[surface])
        assert edge >= NON_TEXT, (
            f"{theme} --signal-fill {fill} on --{surface} is {edge:.2f}:1, "
            f"below {NON_TEXT}")


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("tone", ["signal-ink", "settled", "hold", "crit"])
def test_a_status_colour_is_readable_as_the_word_it_colours(palette, theme, tone):
    """These tint status text, not just pips, so they answer to 1.4.3.

    The accent appears here as --signal-ink and not as --signal, because
    the two are different jobs. --signal is the fill of a button and the
    stroke of a chart, which 1.4.11 asks 3:1 of; --signal-ink is the
    accent used as a word, which 1.4.3 asks 4.5:1 of. One value cannot
    do both in a light theme, and the attempt is what produced the
    3.11:1 that this test used to fail on."""
    tokens = palette[theme]
    for surface in SURFACES:
        got = ratio(tokens[tone], tokens[surface])
        assert got >= BODY_TEXT, (
            f"{theme} --{tone} ({tokens[tone]}) on --{surface} is {got:.2f}:1, "
            f"below {BODY_TEXT}")


def test_the_two_border_tiers_have_not_been_collapsed(palette):
    """--edge is meant to be quiet and --edge-ctl is meant to be seen. If
    someone makes them equal, one of the two jobs is being done wrongly."""
    for theme, tokens in palette.items():
        quiet = ratio(tokens["edge"], tokens["ground"])
        loud = ratio(tokens["edge-ctl"], tokens["ground"])
        assert loud > quiet * 1.5, (
            f"{theme}: --edge is {quiet:.2f}:1 and --edge-ctl is {loud:.2f}:1; "
            "they are no longer two tiers")
