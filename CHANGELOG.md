# Changelog

## 1.15.3, 22 September 2026

- The home page tells the story rather than holding one frame of it. The
  illustration already carried the whole argument and a six second loop
  drawing the trace, but the three beats that give it meaning were
  missing. The trigger now answers when the trace crosses it, at 13.2% of
  the loop, measured off the path rather than guessed, because that
  crossing is the entire reason the money moves and nothing before it
  should suggest it has. The payout counts up as the card lands, eased so
  it arrives rather than stops, and in the page language, so a Turkish
  reader sees 25.000.
- The block number stops at settlement. It was drifting on a timer of its
  own under a line reading "settled in block", which is a plain statement
  about one block and cannot keep changing. The chain goes on advancing
  while the policy waits; once it settles, that number is the one it
  settled in and it holds until the loop begins again.
- Everything hangs off the card animation's own iteration rather than a
  second timer, which would drift apart from the CSS within a minute. A
  browser asking for less motion gets the still picture untouched, reading
  25,000 in block 412,388. No bytes were added to the page: it was already
  in the DOM.
- The chain clock is quiet where the picture is not drawn. Below 860px the
  illustration is not rendered at all, but the timer behind its block
  number went on waking every 1.3 seconds to count for nobody. It stops
  where there is nothing to say, and starts again by itself if the window
  is widened.

## 1.15.2, 21 September 2026

- The English says which of two things it means, in the places where six
  translators each had to guess. Reviewing all six languages turned up the
  same short list of source ambiguities every time, so the source is fixed
  rather than worked around once per language.
- `claim` meant both a demand for payment and an assertion. The assertion
  sense is now `statement`, and the refusal about an unrecognised
  credential says `attestation`, which is what it always was.
- `settle` meant both the insurance act and the payment rail. The rail now
  says `paid`: `Payout currency` rather than `Settles in`, `paid in
  {cash}` rather than `settling in {cash}`, and `Settlement assets
  permitted by that licence`, which is what that field lists.
- Two keys were doing two jobs. A country with no cover yet said `closed`,
  the word a finished complaint uses, which in Japanese read as "ended"
  and in French, Spanish and Russian carried a complaint's gender. It says
  `not open`. A licence no longer in force said `lapsed`, the word a
  policy that ran its term uses, which in Russian took a policy's
  masculine ending. It says `out of force`.
- `Edge reading, validator attested` used a word explained nowhere, so
  every language transliterated it. It reads `Read at the source, attested
  by validators`.
- `Sign and apply for {amount}` read as applying for that much cover, when
  the amount is the premium. It reads `Sign and apply, paying {amount}`.

## 1.15.1, 21 September 2026

- A checkpoint no longer loses a cycle to a book being written while it is
  read. The live journal carried `could not save the book: dictionary
  changed size during iteration`. Each book is copied before the
  checkpoint walks it, but the values in those books are the live objects,
  and a request thread recording a vetting check or stamping a policy's
  metadata holds no lock; the encoder was iterating such a dict directly.
  It now takes the items in one step, which no other thread can interrupt.
  Reproduced against the old encoder at thirty failures in three thousand
  tries, and at none with this one.
- The step being worked on is not a box clipped by the gutter. The band on
  the home page and the current step of the cover flow both carry the
  class name `now`, and the band's rule was written unscoped, so every
  step chip inherited its fill, its rules above and below and its vertical
  padding. At the last step that box ended flush against the right edge.
- A dialog and a menu sit a step above the card they came from. Both were
  painted in the card colour, so on a dark page the only thing saying they
  float was a black shadow, which against a near black page says almost
  nothing.
- A short page keeps its footer at the bottom of the window instead of
  leaving it halfway up with dark ground beneath it.
- The calculation rules heading is two lines rather than four. It was
  being held to the sixteen characters that suit a short headline.

## 1.15.0, 21 September 2026

- The palette answers to what it is seen against. Every colour this site
  ships was measured rather than trusted, and several were wrong: the
  tertiary ink failed the 4.5:1 minimum on every surface in both themes;
  the light signal, settled and hold tones failed both as text and as a
  button label; and the light primary button ran its sheen the wrong way,
  taking a white label on orange to 4.25:1. All corrected, and a test now
  reads the tokens out of the stylesheet and computes the ratios, so the
  next wrong value fails a test instead of shipping.
- Borders come in two tiers, because a divider and the edge of a text
  field are not the same obligation. The old single tier measured 1.10:1,
  which is right for a rule drawn between two rows and wrong for the only
  thing saying an input is an input. Controls now draw at 3:1 and panels
  keep the quiet line.
- Focus draws two rings, the inner one in the surface colour. A single
  ring around a signal-filled button was signal on signal, so the most
  important control on the page had no visible focus at all.
- The illustrations are drawn in a line that can be seen. They carried
  the divider tone at 1.57:1, which is why the picture explaining how the
  cover pays read as an empty panel next to the headline.
- The chooser at the first step is no longer squeezed into a reading
  measure. Five cards had 133px each, with their headings broken over two
  lines, while half the page stayed empty.
- Heading tracking follows size instead of one setting serving a 60px
  line and a 15px label alike, and the four claims under the hero are
  laid out two and two rather than three and one.
- Every string in all six languages was read against its English for
  meaning. Roughly 2,100 values changed. The errors were not stylistic:
  a Turkish contract clause that said "above all" where the English says
  "before anything happens"; a status that invented a cause, telling an
  insurer data had not arrived when the term had merely run out; a German
  capital rule that said a provider *is able to* withdraw where the
  English says *may*; a Spanish disclosure that named the reader's own
  country as the one a company is licensed in; a French payout called an
  assessed indemnity, which is the one thing this product does not pay; a
  Russian word doing duty for both settling a claim and settling a
  payment; and a Japanese page referred to under four different names by
  the twelve places that link to it. Terms of art were settled once per
  language and held across all of them.
- The FAQ quotes the message it says it quotes. It promises that a
  message on the page is quoted exactly so you can find it here, and in
  several languages it quoted a wording the page has never shown.
- Sentences that reach the translator through a table are translated too.
  The fault names and the seismic zone names are not written inside
  `t("...")` but read out of a table, so nothing checked them; a test now
  does, and it found one that had no translation in any language.
- The last step reads like a checkout rather than a scroll. It is the
  longest page in the product and it was a 720px column with half the
  window empty beside it: the summary, the sentence, the payout chart and
  table, the company, what is checked before issue, how to pay and the
  whole contract, one under the other. The summary now holds a column of
  its own and stays in view while the rest scrolls past it.
- Choosing a place puts the map beside the search rather than under it.
  Stacked in a reading column the map was 720px wide with 400px of empty
  page next to it, and the list of matches began below the fold.
- Where a company is licensed follows where it is domiciled. The two
  fields never moved together, so choosing Türkiye left "licensed in" on
  whatever it started at, and that is the field the register check is
  made against.
- Whatever takes focus stays where it can be seen. The window judges "in
  view" by its own edges and knows nothing of the header stuck to the top
  or the price bar stuck to the bottom: at 320px the country select
  landed two pixels under the bar and the file dropzone a hundred and
  twenty below it.
- Below 400px the brand drops its word for room and the mark beside it is
  hidden from assistive technology, so the link to the home page had no
  name at all. Hidden from the eye only now.
- The price bar says what you receive beside what you pay, and the
  signing button names the amount.

## 1.14.1, 21 September 2026

- The demonstration's older policies are forgotten too. The test in
  1.14.0 was the demonstration's marker or an address it derived, which
  left the several thousand written before the addresses changed shape:
  they carry neither. A policy is now also the demonstration's when
  nobody can reach it, meaning no device key is registered for its
  holder, no account signed in as it and no wallet is linked to it.
  Three things exempt a policy outright, whatever else is true: a record
  saying it is not the demonstration's, a partner behind it, or the
  contract its holder accepted stored on it, which only the application
  path writes.

## 1.14.0, 21 September 2026

- The demonstration's book is kept to a size. A simulated chain writes
  policies by the thousand and, once settled, they were kept for ever:
  twenty one thousand of them on the live protocol, nine thousand more a
  day, and everything that walks the book paid for every one. Settled
  demonstration policies past the most recent two thousand are now
  forgotten along with their settlements, and the chain keeps the counts
  and latencies they contributed, so every figure it publishes is exactly
  what it was. A policy a person bought is never touched: the test is the
  demonstration's own marker or an address it derived for itself, and a
  record that says outright it is not the demonstration's is believed.
  `CLAUSE_DEMO_KEEP`, 0 to keep everything.
- A log is written from where it left off. The whole settlement log was
  encoded on every checkpoint to write its last few entries. Only what is
  not on disk is encoded now, and a log that came back shorter, because
  something was forgotten on purpose, is written again from the start.
- Together with 1.13.1: a checkpoint that writes nothing fell from 1.2
  seconds to 0.09 on a book of twenty one thousand policies, and the
  chain's own page from two seconds to three milliseconds.

## 1.13.1, 21 September 2026

- Keeping the book costs less. The checkpoint encodes every document on
  every cycle to find the ones that changed, and asked the dataclasses
  module for the same field list each time; on a book of twenty one
  thousand policies that was a third of the work. The shape of a class is
  now worked out once and the common types are dispatched on directly.
  The text is byte for byte what it was, which a test pins, so nothing on
  disk is rewritten and nothing reads back differently.

## 1.13.0, 20 September 2026

- A price no longer makes a purchase wait. Every preview quote, the
  offers and the contract text priced the book while holding the money
  lock, seconds of simulation each, so a purchase arriving behind a few
  visitors' prices could wait past the page's patience and be reported
  as "the protocol could not be reached", though nothing was wrong with
  it. A quote now takes a snapshot of the book under the lock and prices
  it outside; the engine's caches are guarded so quotes can run side by
  side; the purchase itself still prices under the lock, against the book
  as it is then, and refuses if the price moved past what was agreed. The
  page waits ninety seconds for a purchase, and nginx two minutes.

## 1.12.2, 20 September 2026

- On the Proof page the signer's address is shown short, with the full
  one on the explorer, and a value never runs over the column beside it.

## 1.12.1, 20 September 2026

- The theme button has three positions, in a cycle: the device's own
  (nothing chosen; the page follows the system setting, and follows it
  when it changes), light, dark. The button shows the mode in force, a
  half disc for the device's own, and says which in its label, in the
  language chosen. A choice is kept on the device; the device's own is
  the absence of one.

## 1.12.0, 20 September 2026

- The site moves like something finished. The hero arrives in order,
  headline, sentence, buttons, marks, under a light that drifts slowly
  across it; the five perils sit in one row and lift toward the pointer
  with their art leaning in; cards, steps and columns rise into place as
  the page is scrolled, each a beat after the one before; the primary
  button has depth, a highlight and a lift, and presses down; the step
  line fills as a purchase advances and the current step breathes; the
  price counts to its new figure instead of jumping; every press that
  moves you on fires the trigger, rings spreading from the point pressed
  and a light crossing the button; dialogs arrive over
  a blurred page; a page still being read shows a shimmer, not a word.
  The insurers page opens with four figures. On a phone the state bar is
  one line. All of it is off for a browser that asks for less motion,
  where every element is simply there.

## 1.11.0, 20 September 2026

- Check your answers. The confirm step opens with what was chosen, line
  by line: the cover, the place, what is at risk and its declared value,
  the amount and term, the company, and the whole price with the fee and
  the instalments. Each line has its way back to the step that set it,
  and the company line opens the other offers. A purchase can be read
  over and corrected before it is made (WCAG 3.3.4).
- The API hardens every answer itself: `Cache-Control: no-store` under
  `/api`, `nosniff`, a referrer policy, a permissions policy with the
  device APIs off, `X-Frame-Options: DENY` and a content security policy
  of nothing. nginx says the same in front; now a deployment without it
  is no less careful. A refusal for haste carries `Retry-After`. The
  rate limits, both layers, are written down in the architecture note.
  The site's own headers gain a content security policy against plugins,
  a rewritten base URL and framing, and a permissions policy.
- Reachable by keyboard and at any size. A skip link to the content; the
  two dialogs are named by their headings; each page's sections sit one
  level under its heading; every control is at least 24 css px tall
  (the language menu, the note's close, the footer links, the file
  inputs, the map's attribution, the sign in links on the insurers page);
  at 320 css px, a phone or a desktop at 400% zoom, the header, the
  footer and the country menu fit without a sideways scroll.
- Linking a wallet on the profile page now shows the link the moment it
  is made. The page had been redrawing the wrong box, so the button sat
  greyed until a reload.
- One font weight fewer to fetch.

## 1.10.1, 20 September 2026

- The illustrations are alive. On the home page the trigger loop runs:
  the trace draws itself across the trigger line, the epicentre pulses
  and its rings ripple, the attestation runs along the arrow, the payout
  card lands with its tick, and the block the payout settled in keeps
  counting. On the five cards the weather moves: rings from the
  epicentre, a turning sun and rising heat over the field with the gauge
  breathing, the plane arriving as the delay bar grows, rain falling and
  water lapping at the car, wind and gusts streaming past the bending
  tree and the lifting tile. All of it is CSS on the SVGs, so it costs
  nothing to run, and none of it runs for a browser that asks for less
  motion: the still art stands, whole.

## 1.10.0, 20 September 2026

- Three bordereaux for the company's desk and its reinsurer, month by
  month: the risk bordereau (every policy bound, with its dates, limit,
  gross premium, the fronting fee and the platform's share paid to date,
  the net to the carrier), the claims bordereau (every payout with its
  date of loss and index, and every premium returned on cancellation),
  and the reconciliation against the fee ledger, which says whether they
  agree and by how much they do not. Field logic after Lloyd's
  Coverholder Reporting Standards; CSV in the shape a bordereau desk
  loads. On the Company page, and for the operator across every carrier.
  `clause/protocol/bordereaux.py`, `/api/company/bordereaux`,
  `/api/operator/bordereaux`.
- Storm and vehicle flood read the station first. The validators' source
  chain for wind and rain now starts at the national meteorological
  service's nearest station and falls back to NASA POWER and ERA5, in
  that order, as the rulebook says; the data source names the order and
  the quantile mapping the fallbacks get. The simulated chain still
  draws its readings; what changed is the order the record names and
  the contract states.

## 1.9.0, 20 September 2026

- The whole price from the first place chosen. The moment there is a
  place, the page asks the protocol for its offers and its premium and
  the price bar shows premium and company fee together, per term and
  about per month, before anything personal is asked; the page's own
  model fills the bar while it waits and whenever the cover moves, and
  the protocol's figure replaces it a moment later.
- The right to withdraw as the distance selling rules shape it. The
  fourteen days run from the day the contract reached the buyer, a year
  if it never did on a durable medium, and whatever comes back is due
  within thirty days of the notice (paid at once here, and recorded).
  "Your copy of the contract" on every policy saves the text the buyer
  accepted as a file, and the day it was taken is noted; a directly
  bought policy now keeps that text too, and its hash is part of what
  the buyer signs.
- Complaints on the policy. "Raise a complaint" under My cover opens a
  thread with the issuing company with its time to answer counted from
  that moment (fifteen days in Türkiye, eight weeks in the UK); the
  company answers on its own page, its first message stops the clock;
  when it does not answer in time, or the answer does not settle it, one
  click takes it to the ombudsman (the Sigorta Tahkim Komisyonu in
  Türkiye) with the file its form asks for: the policy, its contract
  hash, every reading and settlement, the whole thread, the links. The
  operator sees every complaint. `clause/protocol/complaints.py`.
- The calculation agent's rulebook. Peril by peril: the primary source
  and the ordered fallbacks, what counts as the final figure and when it
  is frozen, the tests a reading must pass, the chain's attestation rule,
  the silence deadline, a thirty day objection window, the successor
  source rule and the archive rule. Section 10 of every contract, the
  Calculation rules page, `GET /api/rulebook`. `docs/rulebook.md`.

## 1.8.0, 20 September 2026

- The token in the holder's own wallet, if they want it there. A buyer
  who has linked an Ethereum wallet on their profile (proved by its
  signature) gets the token minted to it from the start; one who links a
  wallet later presses "Mint it to my wallet" on the token: a mint not
  yet sent is pointed there, one already on the chain is burned and
  minted again to the wallet, the mint waiting for the burn to be mined,
  since the token cannot be transferred. The token dialog says who holds
  it. `POST /api/policies/{id}/anchor/claim`.

## 1.7.4, 20 September 2026

- A mint recorded before there was a signer carried the zero address as
  its recipient, and the contract refused it once a signer sent it. The
  recipient is now decided the moment the transaction is built, and a
  mint that already failed for that reason is queued again with one.

## 1.7.3, 20 September 2026

- `scripts/deploy_anchor.py --address` prints the signer's address without
  touching a node, so it can be funded first; a node that cannot be
  reached is one line, not a traceback. The anchor's variables are in
  `deploy/clause.env.example`, commented out.

## 1.7.2, 20 September 2026

- The backfill queues only open policies, and a book from before the
  demonstration's policies were marked recognises them by their holder
  having nobody behind it (no device key, no Privy account, no linked
  wallet, not bound by a partner). The live book had queued two thousand
  mints for the demonstration's own history; mints queued by an earlier
  build for such policies are dropped before they are ever sent.

## 1.7.1, 20 September 2026

- The anchor's first cycle runs on its own thread, not on the startup
  path: on the live book, hashing every policy into the first root took
  longer than the install's health window and 1.7.0 was declared down
  while it was still starting. Keccak is twice as fast (the permutation
  unrolled), a policy's leaf is hashed once and kept until the policy
  changes, the tree behind each recent root is kept so a proof is a
  lookup, and a cycle that finds the same leaves builds nothing.

## 1.7.0, 20 September 2026

- A public chain beside the protocol's own. Base Sepolia is told of each
  policy token minted (to the holder's linked Ethereum wallet, else held
  by the signer for them) and burned, of each settlement, and, on a
  timer, of the root of a Merkle tree over the whole book. Two small
  contracts: a policy token (ERC-721 with ERC-5192 locked, every transfer
  refused, the id the Keccak of the policy number) and a book (roots by
  epoch, settlements as events, and `verify(root, proof, leaf)`). The
  service signs its own EIP-1559 transactions (RFC 6979 nonces, checked
  against the EIP-155 example) and speaks plain JSON-RPC; no wallet
  library. Each thing to tell the chain is an intent in the book first,
  so nothing is lost to a restart or a node that is down, and a call
  that would revert is not paid for. The demonstration's own policies are
  in the root but get no transactions of their own.
- Without a key it still works: roots are built and intents recorded as
  not sent, so the proof page shows a policy's place in the book today
  and the day the signer is funded everything goes out in order.
- The Proof page shows the chain's state and, for a policy, its mint,
  burn and settlement with explorer links and its leaf, siblings and
  root, with a button that recomputes the proof in the browser
  (Keccak-256 in the page, no library). The token dialog says where the
  token is on the public chain. `/api/anchor`, `/api/policies/{id}/anchor`,
  `POST /api/operator/anchor/run`, `scripts/deploy_anchor.py`.

## 1.6.0, 20 September 2026

- Letting a company in has a shape. Each registration gets the operator's
  checklist by domicile and role: the legal entity (LEI or trade register;
  Türkiye: MERSİS and the trade registry gazette), control of the domain,
  the licence and the classes it must name (Türkiye: the branch each peril
  needs, and membership of Türkiye Sigorta Birliği), the signatory's
  authority, sanctions screening (UN, EU, OFAC, MASAK), live enforcement,
  and two recommended items (solvency, a data processing agreement). Every
  item links the register to read; the company's documents sit beside the
  item they support, by kind. The operator records each item with where
  they looked and what they saw; activation is refused until every
  required item is confirmed, and the review keeps the checklist as it
  stood. Checks fall due again a year on, and the operator's page lists
  what is due and which licences are about to lapse.
- The company sees the same checklist on its own page and can add the
  documents it asks for after registering, choosing what each one is
  (nine kinds now, from licence certificate to signature circular).
  Registration in Türkiye takes the MERSİS number and the tax number.
- A questions page, at /faq and from the footer: thirty-two questions in
  seven groups, from what the price is made of to what to do when a
  message appears, with each message the page can show quoted as it
  appears and what to do about it. In all six languages.

## 1.5.1, 20 September 2026

- The confirm step, shorter by a quarter on a phone. The chosen company is
  shown in full and the others sit behind "compare n other companies"; the
  legal ruling is one line with the law behind a click; the DASK
  comparison folds; and "read and accept the contract" is a live button
  that takes the buyer to the contract instead of a dead one.
- The interest step asks less. A home is named after its place ("A flat in
  Kadıköy"), which the buyer can change, and the place they chose is where
  it stands, so "inside the area" is confirmed by construction and left
  for the buyer to undo rather than to find.
- Rider is alive: a pulse runs its line, the figure rides it, and the panel
  carries a wave that quickens while Rider thinks.
- Readings behind the hero: small clusters of marks appear, drift and
  dissolve behind the home page's opening, more of them where the pointer
  goes and when Rider is reading; drawn on a canvas a dozen at a time,
  paused when unseen. All of the motion stops for anyone whose browser
  asks for less of it.

## 1.5.0, 20 September 2026

- The platform is paid, by the companies and not the buyers. One per cent
  of each premium comes out of the issuing company's fronting fee the
  moment the fee is paid, never more than the fee itself, in proportion
  when the fee arrives in instalments; the buyer's price stays the pool's
  price. A fee that goes back to a buyer takes the platform's share back
  with it. Every movement is an entry, and a company's month of entries is
  its statement: on its own page (month by month, CSV), and for the
  operator under a new "Platform and statements" tab with the platform's
  totals by month and every company's statement (`/api/company/statements`,
  `/api/operator/statements`).
- The company's desk works its book. Search by policy number, street, place
  or buyer (case and accent blind); filter by status, province and peril;
  the policies ending within thirty days, for renewal; open cover grouped
  by province; sort; CSV. The operator's "Buyers and policies" tab is the
  same desk over the whole book (`/api/company/policies`,
  `/api/operator/policies`).

## 1.4.1, 20 September 2026

- A cancelled policy's token leaves the wallet. It stayed on My cover among
  the policy tokens, marked cancelled, as if cover that was undone were
  still something held. The chain now burns the token when it withdraws
  the policy: no owner, the burn block and time on the token, "burned in
  block …" on the certificate, and the wallet view lists live tokens only.
  The cancelled policy itself stays in the list below, as the record it is.

## 1.4.0, 20 September 2026

- Documents for the company's check, sealed to it alone. The application
  path for a home or a vehicle asked the company to confirm ownership (a
  title deed, a lease, a registration) and gave the applicant nowhere to
  hand the paper over. The address step now takes up to four files; each
  is encrypted in the applicant's browser to the reading key of the party
  that will decide (the company's account, or the operator for a stand in),
  and the protocol keeps the ciphertext, which it cannot open, and a record
  it can: what was sent and who opened it, shown to the applicant on My
  cover. A reading key is an ECDH P-256 pair made non extractable in the
  deciding party's browser when it first sits at its desk; its public half
  is registered (`/api/auth/reading-key`, `/api/operator/reading-key`).
  The reviewer's card lists the documents and opens them in that browser;
  the applicant can take one back while the application is open; on the
  decision the sealed copies are deleted. Where no reading key exists yet
  the applicant is told the company will ask by other means, and nothing
  is sent. The envelope (ephemeral P-256, HKDF-SHA256, AES-256-GCM, the
  application id as additional data) is written out in
  `clause/protocol/documents.py` and reproduced in the tests with another
  library.

## 1.3.3, 20 September 2026

- An earthquake quote on shaking, the index the page chooses for a home,
  took twelve seconds on the live server against three for magnitude and
  storm, and the confirm step's three calls (offers, the price, the
  contract) ran past the page's patience one after another: the price bar
  stayed on "Pricing…" and the contract said the protocol could not be
  reached. Three causes, each fixed, no figure changed:
  the capital model walked the address's whole rate table on every one of
  its twelve thousand trials (now a cumulative table kept per address and
  a binary search; the same events, in the same order, from the same
  random numbers); the capacity checks after a quote simulated the whole
  book twice more with the candidate in it (now the cached book plus the
  candidate settled once and remembered); and the page asked for the
  contract before the price came, so the same policy was priced a third
  time for the text (now the contract waits for the price and carries its
  lock). The `diagnose` workflow probes the confirm step as the page
  sends it, one call at a time and all at once.

## 1.3.2, 20 September 2026

- The book on disk: a save that ran while a key was being registered or an
  account joined lost the whole save with "dictionary changed size during
  iteration", every half minute on a busy server. Each book is copied in one
  step before it is walked.
- A body a route cannot read (a 422) is logged with the fields at fault,
  and the page says "the protocol could not read what the page sent" with
  those fields, instead of "the protocol did not accept this".

## 1.3.1, 20 September 2026

- An error the code did not foresee is answered as JSON with a reference
  (`ERR-…`, with the traceback under it in the log) and, for an origin the
  operator named, with the CORS header; before, the answer was plain text
  from outside the CORS layer, which a browser on another origin was not
  allowed to read, so the page could only say "the protocol did not accept
  this". The page now also says when it could not read the answer at all.

## 1.3.0, 20 September 2026

- Storm cover steps one level rarer: the place's own 1 in 25, 1 in 50 and
  1 in 100 year wind day, paying 25, 60 and 100 per cent, instead of 1 in
  10, 25 and 50. A 1 in 10 year day is one most homes see within a decade
  and one that takes tiles rather than roofs; paying a quarter of the
  rebuild cost on it made a year of storm cover cost about twice an
  Istanbul earthquake policy. The expected loss falls from 4.7% to 2.1% of
  the limit and the premium roughly halves. Cover already written keeps
  the steps on its contract.

## 1.2.2, 19 September 2026

- A book saved by an earlier build carries the stand in companies with the
  perils that build knew, so storm cover was refused everywhere with "a
  company is registered here, but not for this risk". On restore the stand
  ins' licences and appetite are brought up to this build's; a real
  company's licence is left exactly as it registered it, and a suspended
  stand in stays suspended.

## 1.2.1, 19 September 2026

- `deploy/install.sh` on a server that already has a reverse proxy: with
  `/etc/caddy/Caddyfile` present nginx is neither installed nor tried; when
  something else holds port 80, nginx is stood down with "reverse proxy
  already present, nginx skipped" and the install goes on rather than
  failing. At the end the installer asks `127.0.0.1:8080/api/health` for
  the version it is running and fails, with the log to read, if it is not
  the version just installed.

## 1.2.0, 19 September 2026

### The policy pipeline
- An operator's refusal is now a rule in the path of money rather than a
  note somewhere. Two rules, run in order, the first to deny stopping it: a
  denylist (an address here, a wallet on another chain, a country, a payout
  destination) and a moratorium (no new cover on a peril, in a country or
  inside a circle, until a date or until lifted; cover in force is paid on
  its terms). Asked at every stage that moves value: a purchase by hand, by
  application, by a standing instruction, by a partner or by Rider; a payout
  before it leaves (refused, the premium comes back, as for a company that
  lost its licence); a cashout and the choice of a destination; a deposit
  announcement; a wallet being linked. A payout routed to a refused bank
  account stays at the address. Every entry carries a reason, who wrote it
  and when; lifting keeps it with who lifted it. Entries are in the book on
  disk; decisions are kept in memory for the operator to read back.
- `POST /api/policy/check`: the decision the real stage would take, without
  acting, in the shape Rider asks its Latch for one. A person hears about
  their own address; the operator and a partner about any; nobody anonymous
  about anyone. `GET /api/policy` describes the rules and lists every live
  moratorium, never a denylist entry. `GET /api/operator/policy`,
  `POST /api/operator/policy/deny`, `POST /api/operator/policy/pause`,
  `POST /api/operator/policy/{id}/lift` for whoever holds the operator token.

### Storm cover
- A fifth peril: a home against extreme wind where it stands. The index is
  the largest daily maximum wind speed at ten metres (NASA POWER, MERRA-2,
  in km/h) at the nearest provincial centre; the steps are that place's own
  1 in 10, 25 and 50 year levels, paying 25, 60 and 100 per cent. Pays on
  the wind, not on the roof; hail, lightning, snow load and flood are named
  as not covered. Applied for like any home, with the address, and the
  company decides. Priced against a shared front in the capital model, so a
  book along one coast settles together. `GET /api/storm` gives the levels
  at a place; the site has the card, the flow and the translations.
- The model is built offline, `python -m clause.hazard.wind_build`, with the
  method and the test the rain model uses (now shared in
  `clause/hazard/daily_extremes.py`). Until the file exists on a deployment,
  storm cover is priceable nowhere and the site says so; nothing is sold on
  a model that has not passed its test.

### Deployment
- A push to `main` is live. `.github/workflows/deploy.yml` installs the
  requirements, runs the tests and, only if they pass, connects to the
  server over SSH (`DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY` from the
  repository's secrets; no value in the file) and runs `deploy/install.sh`
  on a fresh clone of `main`, made with the server's own deploy key. Netlify
  publishes the site.
- `deploy/install.sh` builds `clause/hazard/models/wind_TR.json` from NASA
  POWER when the file is missing, once, as the service user; a build that
  cannot finish leaves storm cover off and the install goes on. The README
  has the secrets and the deploy key steps.

### Also
- Contracts and cancellation terms name wind alongside rain and flights as
  cover that runs to the end of its term once the weather can be seen.
- Rider knows the fifth peril; `clause quote storm` from the command line.

## 1.1.1, 19 September 2026

- My profile: a page of the person's own things, written down once. A home
  (building, floor area, year built, address, pinned on the map), a car
  (model year, make, plate, where it is kept) or a field (crop, area). On
  the "where" step of a purchase they appear as chips and fill the whole
  form: place, size, year, address, name; with two cars, the person picks
  which. After an application, "Save this home to my profile" writes it
  down from what was just entered. Kept behind the session, seen by the
  owner alone, removable at any time. `GET/POST /api/assets`,
  `POST /api/assets/{id}/remove`. The wallet and X links moved to this page
  from My cover.

## 1.1.0, 19 September 2026

### Standing instructions
- A person can sign a purchase in advance and let the protocol make it when
  its moment comes: "keep this policy in force" applies for the same cover
  again a day before the policy ends; "buy this from a date" or "when the
  home (or the car) reaches an age" buys on that day. Each carries the most
  one purchase may cost; a price over the cap, a short balance or a refusal
  is written on the instruction and tried again a day later. A home or a
  car is still applied for and the company still decides; the statements a
  purchase would ask for are asked when the instruction is signed and
  remembered by name. Listed on My cover with every attempt; cancellable at
  any time. `POST /api/instructions`, `GET /api/instructions`,
  `POST /api/instructions/{id}/cancel`.
- On a policy card: "Renew automatically". On the confirm step, under the
  contract: "Not now: buy it later, when a condition comes true".

### Money out
- Balance can be taken out to the destination chosen for payouts (a bank
  account, a mobile wallet, a Rialo, Solana or Ethereum wallet): capital
  taken back from the pool, its returns, a payout that landed at the
  address. The amount leaves the address at once; the operator makes the
  transfer and marks the order, and a failed one comes back.
  `POST /api/payouts/cashout`, signed over the amount.
- The operator's payout list shows, for a company's withdrawal, the
  registered company and whether the name on the bank account matches it.

### The profile
- Wallets on other chains are linked by proof: a Solana wallet signs a short
  text (Phantom's signMessage), an Ethereum wallet signs it with
  personal_sign, both checked here; a Rialo address is written down as
  stated until Rialo wallets can sign in a browser. A deposit from a linked
  Solana or Ethereum wallet is credited by the chain watcher with no
  reference and no announcement.
- An X account is linked through Privy (X's own sign in, inside the sign in
  window) and proved by Privy's identity token; the server keeps the handle
  and nothing else. Needs X and identity tokens turned on in the Privy
  dashboard; no app secret anywhere.
- `GET /api/profile`, `POST /api/profile/links/start`, `POST /api/profile/links`,
  `POST /api/profile/links/{id}/remove`, `POST /api/profile/x`.

### Live bands
- Flight delays worldwide from AirLabs (`CLAUSE_AIRLABS_KEY`; a free key,
  read once an hour): every departure 45 minutes late or more, grouped by
  airport, with the flights named. The world view uses it; the United
  States keeps the FAA feed.

### Fixes
- The 0x to Rialo address migration rewrote every string of that shape,
  including an Ethereum address somebody had chosen as a payout destination
  or given as a deposit's sender. It now rewrites only addresses that are
  accounts here.
- The Rialo mark next to "Rialo" on the home page, in the footer and on the
  wallet choices. The car cover reads "flooding" rather than "water damage"
  in Turkish.

## 1.0.2, 19 September 2026

- Accounts created by an earlier build with an Ethereum shaped address
  (`0x...`) are rewritten to Rialo's shape (32 bytes, base58) when the
  server starts; the account, its balance, policies and applications are
  kept. Signing in by e-mail now shows the same shape of address as the
  Rialo playground.
- The live bands colour readings by severity: an earthquake at M 4.5 or
  above is amber, at M 5.5 or with a tsunami notice red; heavy rain or
  strong gusts amber then red; 35 °C and above amber, 0 °C and below blue;
  a flight delay past an hour amber, past two hours or a closed airport
  red.
- The weather band lists cities worldwide when no country is chosen, and
  the forecast includes the day's minimum.
- The four cover cards carry new illustrations.
- Header and page spacing tightened; the page uses a wider column on large
  screens.

## 1.0.1, 19 September 2026

- The pool page and its "put capital behind the book" form are for capital
  providers, companies and the operator: a person signed in as a buyer no
  longer sees "The pool" in the header. Visitors reach it from the footer
  under "For capital providers".

## 1.0.0, 19 September 2026

The first release built as one piece rather than as a chain of patches. Every
module was audited for seams left by incremental changes; what follows is
what changed as a result, and what is new.

### Money and accounting
- The pool books premium as it is received. With an instalment plan the
  tranches are credited with the first instalment, then with each one as it
  arrives; what is still owed is written off when the policy ends. Before,
  the whole premium was booked at once and instalments were booked again.
- Instalment plans carry explicit parts (premium, issuing fee, financing
  surcharge) per instalment, cents exact, the last absorbing rounding. The
  fee is taken with each instalment, not all at once; the surcharge is
  income to the pool. Due dates run from approval.
- Approval of an application is atomic: the application is claimed before
  the escrow is released, a failure re-holds the money or closes the
  application with a note, and the refund of escrow can only happen once.
- Refunds (cancellation, expiry) return what was paid, less any commission,
  never the whole premium of a plan partly paid. Pro rata uses the policy's
  own start and end.
- A commission is paid once, only out of premium received.
- Income that accrued in a tranche with no shareholders stays with the pool.
- Rider's mandate counts premium and fee; the fee cannot exceed it.
- Buying a home or vehicle policy outright at `/api/policies` is off in a
  deployment (`CLAUSE_DIRECT_BUY=1` turns it on); the site always applies.

### Chain and settlement
- Cover a person bought runs on the clock: its term is real, its source moves
  at the clock's pace even when shared with the demonstration book, and a
  restart neither lapses it nor loses a triggered payout.
- The compliance rules run again before any payout leaves; a company
  suspended mid term stops the payout and the premium comes back.
- A source's running maximum starts again once nothing is armed on it, so a
  new policy is judged on its own term's events.
- A pool refusal, a refund it cannot fund, or a block failure no longer stops
  the chain silently; each is recorded and logged.
- The rainfall closing round retries instead of stranding the season.

### The book on disk
- Every record is written whenever any field changes (content addressed),
  and encoded under the protocol's locks, so nothing is lost or torn.
- A book written by a newer build is refused with a clear message.
- Policies wrongly lapsed by an earlier build's demonstration clock are put
  back in force on restart.

### Identity and companies
- Addresses are shown in Rialo's shape (32 bytes, base58). A device key
  registered under the older 0x form keeps its address and its account.
- Companies register with an LEI (checked at GLEIF), a domain (proof file
  fetched, no redirects, no private hosts), documents (kept for the
  reviewer) and links to the regulator's register; the reviewer records what
  was confirmed. Evidence is written only once the registration is accepted.
- On a demonstration any signed in account may take a stand in company's
  desk and decide its applications.

### Money in and out
- Adding balance: a bank transfer to the operator's account or a USDC
  deposit from a Rialo, Solana or Ethereum wallet, announced with a
  reference; the operator confirms what arrived, or a chain watcher does for
  Solana and Ethereum deposits when an RPC endpoint is set.
- Payouts can go to a Rialo, Solana or Ethereum wallet as well as a bank or
  mobile money.

### Site
- Flight cover asks for the flight number and departure date.
- A running price lock survives a language change and a redraw; a refusal
  from the protocol is shown and nothing is signed on a browser figure.
- The flow resets completely between purchases; "Renew" works; the done page
  survives a language change; the operator session is cleared on any sign
  out; the geolocation prompt waits for the button.
- Policy cards show the end date and offer renewal in the last thirty days.
- Published as a minified, obfuscated page (`site/build.py`); the readable
  source ships only in the server package.

### Deployment
- nginx: `http2` in the listen line (works on stock Ubuntu nginx), a larger
  body for `/api/carriers`, the pricing and buying routes in their zones,
  HTTP/1.1 to the upstream.
- The service unit limits restart storms and keeps the state directory
  private; the installer respects a commented out switch, excludes build
  trees, installs sqlite3.
- Licence: all rights reserved (see LICENSE).
