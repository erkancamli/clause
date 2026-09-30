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
