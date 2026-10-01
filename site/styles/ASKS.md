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

The repeats are gone. Counted again on 1 October, at the top level of each
file, ignoring media queries: all nine are at zero. Nothing is owed on that.

1. **Two blocks in `60-flow.css` were written from the other side of the
   boundary**, at the foot of the file, marked "the paying screen, in six
   parts" and the four lines after it. The paying screen was restructured from
   fifteen blocks in a row into six named parts, and new markup with no rules
   at all would have shipped unstyled, so the minimum was written rather than
   queued: `.part`, `.part + .part`, `.part-t`, `.part-n`, `.basis-cut`,
   `#basis-scale:empty`, `#pay-note:empty`, `.part-wait`, and one 640px query.

   They were written to be correct, not to be good, and they are yours now.
   The numbered circle, the rule between parts, the quoted sentence for what
   the cover does not pay for, and the shape shown while the protocol answers
   are all worth a designer's eye. Nothing in the markup depends on the
   declarations, only on the class names, so they can be rewritten freely.
   `tests/test_site_confirm_parts.py` holds the class names and what each part
   is for.

2. **The paying screen is still long.** Measured at 390x844 with a real
   purchase driven to it: 5,231px, of which the company list is 1,293px and
   the documents part 1,255px, so those two are half the screen. The ladder
   and the curve were 948px between them and the curve is behind a disclosure
   now, which is where the last reduction came from. Whether the rest is a
   density problem or just a long document is a question about the design, and
   that is your side of the line, not a measurement.

3. **One number worth knowing.** A buyer's page is 553,125 B built and
   152,175 B on the wire, of which the stylesheet is 108,670 B built and
   21,709 B compressed. It is the second heaviest thing the page carries after
   the script.
