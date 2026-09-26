# The faces this site serves

Three families, carried here rather than fetched from a third party, so that
reading a page about your own insurance does not hand your address to anybody
and does not wait on two handshakes to somebody else's server before the first
word can be drawn in the right face.

| Family | Role | Licence |
|---|---|---|
| Archivo | headings | SIL Open Font License 1.1 — `LICENCE-Archivo.txt` |
| IBM Plex Sans | body and interface | SIL Open Font License 1.1 — `LICENCE-IBM-Plex.txt` |
| IBM Plex Mono | measurements, rules, identifiers | SIL Open Font License 1.1 — `LICENCE-IBM-Plex.txt` |

Both licences permit redistribution with the software, which is what carrying
the files here is, and both require the licence to travel with them. That is
what these two text files are for.

## Why the names look like that

`archivo-100to900-latin.woff2` is the variable face covering weights 100 to 900
for the Latin slice. Weights are carried as a range and not as separate faces
because the range is cheaper: Archivo's whole range is 34 KB of Latin, and IBM
Plex Sans's is 45 KB, while the four weights this page sets, fetched as four
static faces, cost 115 KB for Plex Sans alone. IBM Plex Mono has no variable
cut, so its two weights are two files.

Only the alphabets this site is written in are carried: Latin, its extension
for Turkish and the rest, and Cyrillic for Russian. Each face declares the
unicode range it covers, so a browser fetches only the slices the text on the
screen actually needs — a page in Russian pulls the Cyrillic ones, a page in
English never sees them.

## Japanese

Not here, on purpose. IBM Plex Sans JP is a CJK family that Google serves as a
hundred-odd slices keyed by unicode-range, so a Japanese page pulls only the
characters it sets. Carrying it here would mean shipping megabytes to everybody
for the readers of one language, so it is fetched on demand, after first paint,
by them alone. It is the single exception the build's test allows.

## Replacing or adding one

Fetch the woff2 files and their unicode ranges from the family's own
distribution, put them here, and declare each one in the `@font-face` block at
the top of `site/index.html`. `tests/test_site_build.py` checks that every face
the page declares is a file that exists, that nothing on the critical path is
fetched from a third party, and that the build publishes this directory.
