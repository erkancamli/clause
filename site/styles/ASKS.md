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

1. **The rule about overrides was stated as three examples and taken as three
   files.** That was badly put and it is the reviewer's fault, not yours. The
   rule: a selector should be written once per level in a file, so that reading
   the file top to bottom leaves the reader right. Counted at the top level of
   each file, ignoring media queries, which are a different thing. You cleared
   `10-header.css`, `20-controls.css` and `50-home.css`. Six files still carry
   it, and four of them worse than the three that were named:

        80-pool-and-the-rest.css      7 before,   34 now
        60-flow.css                   3 before,   28 now
        30-views.css                  4 before,   25 now
        40-happening-now.css          1 before,   12 now
        70-how.css                    1 before,   10 now
        00-tokens.css                 2 before,    8 now

   Ninety-nine repeats added in all. Fold each one into the rule it overrides,
   as you did for the first three.

2. **Two blocks were written into `60-flow.css` from the other side, which is
   against the rule above.** They are at the foot of the file, marked
   "the paying screen, in six parts" and the four lines after it. The paying
   screen was restructured from fifteen blocks in a row into six named parts,
   and new markup with no rules at all would have shipped unstyled, so the
   minimum was written rather than queued: `.part`, `.part + .part`,
   `.part-t`, `.part-n`, `.basis-cut`, `#basis-scale:empty`, `#pay-note:empty`,
   `.part-wait`, and one 640px query.

   They are yours now, not a fixed point. They were written to be correct
   rather than good: the numbered circle, the rule between parts, the quoted
   sentence for what the cover does not pay for, and the waiting shape are all
   worth a designer's eye. Nothing in the markup depends on the declarations,
   only on the class names, so they can be rewritten freely. The class names
   are in `tests/test_site_confirm_parts.py`, which also holds what each part
   is for.

   Counted after the two blocks: `60-flow.css` still needs the fold described
   in 1 above, and these blocks add no repeat of any selector already in it.
