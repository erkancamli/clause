# What the stylesheet needs from the markup

The visual system is worked on here, in `site/styles/`, and the markup and the
script are worked on in `site/index.html` by someone else at the same time. Two
hands in one 13,000 line file is a day lost to conflicts, so nothing in this
directory edits that file.

When a design needs a markup change, write it here instead: a new element, a
class that does not exist, a section in a different order, an attribute for a
state. Number them, say what you need and what it is for, and carry on with
everything that does not depend on it.

Keep an entry until it has been applied, then delete it. This file is a queue,
not a record; the record is the diff.

## Open

_none_

## From the other side

Found while reviewing, measured, and left here rather than fixed, because these
files are yours.

1. **The decoration lands on the trust row now.** The four chips under the hero
   buttons moved down 134px when the hero's spacing grew; the decorative canvas
   behind them moved 21px. They are inside it now, and the orange dot grid
   draws over "Built on Rialo" and over "Price before you decide" as it
   animates. Measured at 1440x900: the chips were at y 436 and are at y 570,
   the `.readings` layer was at y 158 and is at y 179. Before the change
   nothing was drawn on them.

2. **Rules are being overridden rather than edited.** `.btn` is declared twice
   in `20-controls.css`, forty lines apart, and the second wins; the same in
   `10-header.css` and nine other places. Counted at the top level of each file,
   ignoring media queries, which are a different thing: `20-controls.css` went
   from 0 repeats to 9, `10-header.css` from 2 to 12, `50-home.css` from 1 to
   22. It works and it reads as a patch on a patch, which is the thing this
   codebase is trying not to accumulate. Fold each override into the rule it
   overrides.

3. **The light theme's two quiet tiers collapsed towards one.** Warming the ink
   took secondary to Lc 84.5 and tertiary to 79.3 on the sunk surface, a step of
   5.2 where the dark theme's is 8.6, and every test passed because each tier
   still cleared the floor on its own. Tertiary is `#55514B` now, which puts the
   step back at 8.3, and `tests/test_site_contrast.py` holds the step from now
   on rather than only the floor. Keep the hue if you want to move it; keep the
   step.
