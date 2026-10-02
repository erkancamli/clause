# Changelog

## 1.50.5, 2 October 2026

- Nine of the test audit's findings: assertions that could not fail, and two
  paths with no assertion at all. No change to what the protocol does; what
  changes is what the suite would notice if it did.

- **The level of the price was pinned nowhere.** The premium test asked that
  the premium equal its three parts, which is how the engine computes it, so
  the assertion was that identity read back. Measured by mutating the engine:
  doubling the quoted capital charge passed, 1.5x passed, 1.25x passed, and
  setting the expense ratio to zero passed against the whole suite. The
  company's price was worse: both sides of all three assertions were
  loads_for on the same inputs, and that is the function a buyer is actually
  charged from, so doubling the capital charge there passed 146 tests across
  nine money files and dropping the term passed as well. The arithmetic is
  written out now, with the figures beside it, and all four mutations fail.

- A payout collects what is still owed on the premium, and nothing asked
  whether it does: removing the deduction paid the holder in full and let
  them keep the unpaid premium, with 95 tests silent. Cancellation, expiry
  and lapse each had a test; the one ending that collects rather than
  forgives had none.

- The contract's promises were asked of the whole document, which any copy
  of them anywhere satisfies: deleting the silence rule from section 3 left
  it in the rulebook's own line at the end, and deleting the sentence that
  says nothing can be cancelled once the index has reached its trigger left
  "cannot be cancelled" in the sentence beside it. Each is asked of its own
  section now, and a doubled ceiling, a deleted cancellation limit and a
  deleted silence rule all fail.

- Four smaller ones. A test asserted that one of its own string constants
  does not contain "MMI", which no change in the product could make fail. The
  payout ladder was guarded by a list of three spellings, so a fourth
  written-in level in any other spelling passed sixty seven tests. Papers was
  guarded by six forbidden method-name prefixes, so a rewrite() would have
  passed while the docstring says there is no way to edit one. And one
  assertion was written as two halves of an or that are the same string.

## 1.50.4, 2 October 2026

- Three of the audit's remaining findings, all of them about what a session
  is and what a deployment gives away.

- **Signing out ends the session.** A session token is a signed claim,
  checked without a lookup, which is what makes it cheap; the cost was that
  nothing could end one. Signing out dropped the token from the tab and left
  it valid for the rest of its thirty minutes, and DELETE
  /api/operator/session answered "signed out" to a buyer's token that then
  went on working. DELETE /api/auth/session ends this one, and with
  everywhere=true every session the address holds, including the ones the
  service has never seen. Two records do it, both bounded by the session's
  own length and both kept in the book, because the secret that signs
  sessions is kept there too and a restart would otherwise bring back what
  was ended.

  **A session open when this goes out is signed out once.** The token now
  carries a session id, without which two tabs signing in within one second
  held the same token: ending one ended the other, and signing out and
  straight back in handed back a token that had already been given up and
  was refused for the rest of its half hour. Tokens of the old shape no
  longer verify. The page signs in again by itself where it needs one.

- The two demonstration endpoints no longer announce themselves. A
  deployment with the switch off answers 404 to POST /api/chain/inject,
  which is why deploy/README.md says they are safe to have, but the query
  parameters were validated before the route ran, so an anonymous caller who
  left them out was told their names and types in a 422 instead. Nothing was
  reachable; what leaked was that the doors exist and what to send them.

- The book keeps its secret to the user that runs the service. clause.sqlite
  holds the secret behind every session and every price promise, and sqlite
  created it at whatever the umask allowed: measured at a default Debian
  umask, the book, its write ahead log and its shared memory file were all
  readable by every user on the machine. They are 600 now, said by the file
  itself rather than only by the installer, so a book copied elsewhere
  carries the same answer.

## 1.50.3, 2 October 2026

- Six more of the audit's findings on the buying flow, all of them states a
  buyer could be left in and none of them visible from reading the code
  alone. Every one was found by walking the flow and is fixed where it was
  found.

- Two dead ends on the way to the price.

  A flight's cover arrives at 1,000 from the card and the value slider's
  floor is 200, and the slider was the one place that did not bring the
  cover down with the value. Cover above the value at risk is refused as a
  wager rather than an indemnity, so dragging the slider to the bottom
  refused the policy: the sentence that says why is on the fifth step, the
  only control that lowers cover is on the fourth, and the third would not
  let the buyer past, with a button reading "Cannot be written" that pointed
  at no field. The only way out was to drag the slider back up, and nothing
  said so.

  And tapping the card that is already ticked now changes nothing.
  choosePeril cleared the subject, the radius, the floor area and the cover
  on every tap and cleared the place and the search box only when the answer
  had actually changed, so going back to the first question and tapping the
  same card left the buyer looking at their own address in the search box,
  an empty result list because the query equalled the place it had just
  deleted, no pin on the map, and a button reading "Choose a place".

- A search still running is not a search that failed. The place box asks the
  catalogue inside the page, which answers at once, and a geocoder over the
  network, which takes up to 18.9 seconds with its retry. The empty state
  fired on the first answer alone, so somebody typing their street read
  "Nothing matched" while the service that would have matched it was still
  in flight. It says it is still looking until there is an answer, and a
  lookup that is refused records that as the answer it is, so the waiting
  state always ends.

- "Check the pin, and drag it if it is not quite right" was said the moment
  the browser answered, which is before there is a pin: it is placed by the
  call that turns the coordinate into an address, up to eighteen seconds
  later. Said where the pin is put now, in both of that call's outcomes.

- Offline, the last screen said "You are covered. There is nothing else to
  do." under a green seal, and contradicted itself three lines below in the
  one paragraph it set: "Nothing was bought." The heading, the lamp and the
  seal are the markup's defaults and only the two paths that did buy
  something ever replaced them. That screen writes its own now.

- And the ten minute price hold says so when it ends. The contract is
  written on a held price, so when the hold ends the contract is drawn again
  and the acceptance is taken back. The contract is the longest text in the
  product, so a buyer reading it for more than ten minutes looked up to find
  the tick gone with nothing saying why. Said where the tick was, and only
  where the buyer did not cause it.

## 1.50.2, 2 October 2026

- Six of the audit's open findings, the three that cost a buyer money first.

  A full refund now returns the surcharge a plan charges for paying in
  parts. cancellation.py states its first rule as "Anything bought in the
  last hour can be cancelled for the whole premium, whatever it is and
  wherever the buyer lives", and measured end to end at Osaka on Japan's
  twelve monthly plan, the buyer paid 38.16 and was given 36.34 back. The
  surcharge had been booked as pool income and nothing gave it back. It
  comes back the way it went in, the ledger still replays to the balance,
  and a pro rata cancellation keeps it because the credit was used for the
  months that ran. The page now confirms what leaves the protocol rather
  than the premium part of it, which were not the same number.

  The most read sentence on the page where the signature is taken said
  "You pay N USDC now, and nothing else ever" whatever plan was chosen.
  Under twelve monthly instalments both halves of that are wrong: measured
  on a Tokyo policy it said 10,143.15 and nothing else ever for cover the
  contract priced at 10,948.52 in twelve instalments of 912.38. The plan
  box the buyer chose the plan in, the price row and the price bar all
  knew. The clause is one function now and says what the plan pays.

  And a policy appears in one month's statement rather than one per
  instalment. The money columns were always right; the policy count and
  the premium written were not, and they are the two figures a delegated
  authority desk reconciles first. Measured on one policy with a 1,000.00
  premium paid in twelve parts: twelve policies and 12,000.00 written
  against one and 1,000.00, which made the platform's published 1 per cent
  divide out as 0.083.

- The third question, which asks what is at risk, had three dead ends.

  The box showed one declaration while the contract was sent another: the
  field was written from the model before the model was filled, so a home,
  a field and a car showed a placeholder while the declaration already
  read "A flat in Istanbul, Kadikoy", and that is what /api/contract and
  /api/applications were sent.

  A buyer in the United States was told to check a correct number. US
  cities are offered because the USGS publishes the curves, and the third
  question then refused the floor area, because the rebuild cost schedule
  has ten countries and not that one. The real answer, that no carrier is
  registered there, was the last test in the branch and never reached.

  And nobody is refused before the licensing answer arrives. A flight
  buyer, three taps from the home page with every field filled, met a red
  "Nobody registered" panel and a dead button for as long as the health
  check and the compliance call took, then watched it clear itself.

- A wrong operator token is counted wherever it is tried. One of the
  twenty five routes taking that header was rate limited, and its own
  comment says why: "a token guessed at a thousand tries a second is not a
  token". Measured, 400 wrong tokens at one of the other twenty four
  answered 401 four hundred times at 705 attempts a second. Counted in one
  middleware now, so the twenty sixth route is covered too, and a short
  token is said to be short at startup.

- The API says not to come back unencrypted. deploy/nginx.conf has sent
  Strict-Transport-Security for as long as it has existed, and the
  deployment that is actually running answers through a different proxy,
  which does not: measured against the live service, every other header the
  hardening test asks for was there and this one was missing. The
  application says it itself now, on an encrypted connection only, so
  changing the edge cannot lose it.

- The two deployed contract addresses are written down, in docs/anchor.md.
  Nothing in the repository recorded one, so the operator's page could not
  tell a real deployment from a blank one. Read off the running service and
  confirmed against the chain, where owner() on both still answers the
  signing key.

## 1.50.1, 2 October 2026

- A session released money, and a token could be moved until the key ran dry.

  clause/protocol/auth.py says what a session is for in its own words: "a
  short lived token follows, for reads only", and "writes are not covered by
  the session". Every money-touching route held to that except one.
  POST /api/applications/{id}/withdraw released the escrow on a bare session,
  with no signature anywhere and no rate limit either. Measured against the
  running app: 4,925.39 USDC came back to the wallet on a session alone. A
  stolen session was a stolen view everywhere else and a stolen refund here.
  It is signed over the application now, so a signature for one does not
  release another and a spent nonce does not release it twice.

  The second costs the issuer rather than the buyer.
  POST /api/policies/{id}/anchor/claim puts a burn and a mint on the issuer's
  key, about 350,000 gas a pair, and the dedupe only compared against the
  wallet the token was at. A holder with two linked wallets could alternate
  between them: measured at the service, twelve alternations queued twelve
  pairs and about 8.4 million gas, with nothing on the route to slow it down.
  It is behind a limit now and the moves are counted and capped at three,
  because a limit per minute still adds up over a day. Asking for the wallet
  the token is already at still costs nothing.

  And the thing that made the first fix not work at first:
  ChallengeRequest.purpose was capped at sixteen characters, and
  /api/eligibility/demo reuses that model with claims as purposes, one of
  which is "identity_enhanced" at seventeen. So the enhanced statement could
  never be minted and a buyer above the enhanced threshold could not finish.

- A policy says where it is to about a kilometre, not to eleven metres.

  The one finding from the audit that was a decision rather than an
  oversight. A policy's coordinate is public twice over: it is in the book
  anybody can read, and it is inside the oracle reference that lets somebody
  who does not work here repeat the query and get the same answer. That is
  why redacting the view was not an answer; the reference would have stopped
  matching the query that was made.

  So the point is coarsened where the policy is written, and the record, the
  reference, the predicate and the page now carry the same one. The cost,
  measured rather than argued: across thirteen coordinates in Türkiye the
  point moves 61 to 511 m and not one premium changed, and at Osaka, where
  the hazard comes from a published national model, the distance to the
  publisher's own grid point goes from 0.0 to 0.5 km, the shift from 1.617 to
  1.624, and the premium on a 100,000 policy is 13,195.90 either way. It
  should not change: ShakeMap is published on a grid of about a kilometre,
  ERA5 on about twenty-five, ERA5-Land on about ten, and a magnitude policy
  is a circle fifty or a hundred kilometres across.

- The hot signing key owned both contracts, and nothing said so.

  The constructors set owner and issuer to the deploying key and deploy()
  left both there, with a docstring saying to hand the owner role over
  "afterwards" and no record of anybody doing it. The roles are not the same
  size: issuer mints and settles and is hot by nature, living in the
  environment of a public web process, while owner can change the issuer, and
  these contracts have no timelock, no guardian and nothing upgradeable. A
  stolen issuer can be replaced; a stolen owner cannot.

  The handover happens in the same run as the deployment now, from
  CLAUSE_ANCHOR_OWNER or --owner. Handing it to the deploying key is refused.
  Deploying without an owner still finishes, because a deployment that cannot
  be completed is worse, but it says in full what is then true. And the owner
  is read back off the chain and carried on the operator's page, which is the
  first caller Rpc.eth_call has ever had: one contract handed over and the
  other not, which is how doing it by hand fails, is said as plainly as
  neither.

  Still open: nothing in the repository records a deployed contract address,
  so the operator's page cannot tell a real deployment from a blank one. The
  script now says to write them down.

- Two of the corrections above are corrections to this session's own work,
  and both were caught by running the whole suite rather than the files that
  had been touched. Fixing the spliced sentence in section 10 was right for
  the whole sentences every peril supplies and wrong for the clause the
  rulebook's own signature also allows; both shapes are handled now. And the
  download header's parameter was named "fallback", which in this project is
  the name for a refusal message a reader sees, so two filenames were read as
  copy nobody had translated.

## 1.50.0, 2 October 2026

- An end-to-end audit, run by eight independent passes and verified by
  measurement rather than by reading. Every finding below was reproduced
  before it was fixed, and every fix has a test that was shown to fail
  without it.

- Storm and drought cover could not settle at all.

  The deployment's own health page had been saying so to anybody who asked:
  three sources failing, and no reading written in two hundred rounds. Two of
  the three were not failing. EMSC answers 204 with an empty body when nothing
  in the window matched, which is an answer, and read as JSON it raised. And
  the reanalyses were not refusing: the host the subscription pays for was.
  Asked without the key, the same query answers 200, with fourteen days and a
  strongest wind of 31.0 km/h for the window the deployment was reading
  nothing at all for.

  A refused paid query is now asked again on the public keyless host. Because
  it is the same query, one that is genuinely malformed refuses there too and
  is raised rather than hidden. Asked directly, the host says the archive
  endpoint is not in the plan, which is a fact about the plan and not about
  the moment, so after a refusal the paid host is left alone for an hour
  rather than being paid for twice on every reading. The operator's page says
  the status it refused with and whether it is resting, never the key.

  Both of those then did real damage through a third fault: trouble was one
  dict for every source, and the window-closing guard reads it. A quiet EMSC
  or an unsubscribed reanalysis left a key standing there permanently, so no
  window ever closed for any reference of any peril, and a drought policy's
  silence was explained by naming an earthquake agency that is not one of its
  sources.

- Every drought threshold the page showed was not the one the contract
  settles on.

  site/app/10-model.js carried a copy of the station table the build
  overwrites. The protocol prices and settles on the measured figures; nothing
  ever told the page. All 58 stations disagreed on the normal and 57 of 58 on
  the variability, by 0.6 to 58.4 per cent, and because the drought curve is
  shares of the normal the error went straight into every millimetre a buyer
  reads. At Samsun the page said "records less than 214.4 mm" where the
  contract says "at or below 135.36 mm". For 27 of the 58 stations the page
  named a trigger easier to reach than the predicate: a payout shown and then
  refused. The table is now written from the model, and the test runs the
  writer to check it has nothing left to write.

- The public book published the holder, the address hash and the street.

  Unauthenticated, from four places. The listing gave the holder's address in
  199 of 200 rows while the holder field read null, an unsalted fingerprint of
  the postal address, and the place in full: "222. Cadde, Atakent Mahallesi,
  Küçükçekmece, İstanbul". The policy token gave the same, and ClausePolicy's
  tokenURI points a block explorer at it, beside the wallet that holds it. The
  ledger gave the account, the policy and the premium to the cent on one row.
  And /api/pool gave every capital provider's address with their exact
  position.

  Removing the holder field was an earlier audit's finding, and this is what
  it missed. Fixing it the first time missed burned_from, which is the same
  address on a cancelled policy. So the list of keys to remove is gone and a
  list of what a stranger may read is in its place: a redaction that has been
  wrong twice should be wrong in the direction that does not publish an
  address. A holder still sees their own policy, their own ledger entries and
  their own capital in full, and the contract still carries the address, which
  is where it belongs.

- The confirm step named a price the buyer was not charged.

  "You pay 11,758.31 USDC now, and nothing else ever" while 12,087.54 left the
  address: the sentence passed the pool's premium and the price row beside it,
  the price bar and the server all add the issuing company's fee. Against the
  carrier charging nine per cent the gap is 1,061.36. Six sentences, one per
  peril, in seven languages.

- The earthquake wait was four days wrong, in four places.

  The protocol was changed from seven days to three deliberately; the page's
  table, the sentence under the start date, the FAQ answer and the rulebook
  page were not. Section 10 of every contract said three. Once a quote arrives
  the date comes from the server, so the confirm step printed the right date
  with "cover starts seven days after it is bought" directly beneath it.

- 106 of 254 earthquake curves on the page were not the contract's.

  Measured across every building year from 1900, both indices, inside Türkiye
  and out. A pre-1981 New York flat read 6.63 / 7.63 / 8.63 on the page and
  6.62 / 7.62 / 8.62 on the contract and in the chain's own predicate. The
  cause is where the rounding happens: the protocol rounds twice, the page
  rounded once. Turkish buildings agree either way, which is why it survived.
  With the rounding in the same places, 0 of 254 disagree.

  On the same screen, under "what the chain is actually asked to hold", the
  earthquake row had max_magnitude and 5.5 written into it for both indices
  where the chain is asked to hold mmi >= 6.25, and the topic named a
  .example host that deliberately does not resolve.

- Eleven bytes for a 500, and one stream client for the whole server.

  A body of {"a":1e999} returned 500 on every route that takes one: the
  failure happened inside the error handler, so the answer carried none of the
  hardening headers, nothing rate limited that path, and each request wrote a
  traceback to the log. And GET /api/stream ran the Monte Carlo on the event
  loop every four seconds, so one client held the server for 15,208 ms
  continuously, about three seconds in four. The front page opens that stream.
  /api/pool and /api/pool/risk did the same on an ordinary GET with no limit.

- A phone had no way back, and a second purchase in the same tab threw.

  At 390 x 844 on the "where do you live" step with nothing chosen, Back was
  0 px high and off screen and there was one button on the page: the bar that
  holds Back stands down when it has no figure, which on a phone meant
  display:none. The identical bug had been found and fixed for the desktop
  rail and left standing on the narrow one. And resetFlow set a map to null
  that every reader indexes, so the second purchase in a tab -- which the done
  screen's own "cover something else" leads to -- threw before anything was
  sent and reported that the protocol could not be reached.

- A Japanese buyer was told their trigger on the wrong intensity scale.

  Modified Mercalli intensity was written as bare 震度 in all seven live
  strings that carry a buyer's own trigger, and in Japanese that is the JMA
  shindo scale, the only one a Japanese reader has met. Shindo 6 collapses
  wooden houses; MMI VI is "strong, light damage" and sits around shindo 4. So
  the cover read as paying far more rarely than it does, and the top rung
  printed 震度 8.0, a level that cannot exist on the scale the reader believes
  is in use. Russian had lost two copulas to a dash sweep, leaving a sentence
  that no longer said which season was covered, and one Turkish sentence
  turned permission into obligation.

- Section 10 of every contract had two sentences spliced into one, a capital
  letter in the middle of it and a doubled full stop. The filename on every
  download was the caller's to choose, and a Turkish letter in it answered
  500. The Proof page had one contrast failure at 3.84:1 against a floor of
  4.5. And from 1 January 2027 the page and the protocol would have priced
  buildings a year apart, silently, because both counted ages from a literal
  2026.

- The suite's own honesty, which is the finding that matters most.

  An independent pass mutation-tested 55 assertions and proved sixteen could
  not fail. No test anywhere asserted what a policy costs: the two that look
  like they do are identities, so removing eight per cent from every premium
  the protocol quotes left 1302 of 1303 tests green, as did doubling the
  capital charge. Five policies and their four figures are now pinned. The
  operator console's rule that it never shows a buyer's whole address was
  asserted inside a loop that ran zero times; the document purge was asserted
  behind a guard that was never true, and reducing the purge to a no-op kept
  every applicant's sealed title deed on disk for ever while the record said
  purged and the API answered 410; the eligibility thresholds were asked
  against themselves, so raising one to a billion, meaning nobody is ever
  identity-checked, passed 73 tests; and the contract document's own text was
  never read, so printing twice the policy's ceiling passed 87.

  Each of those is closed, and each closure was shown to fail against exactly
  the mutation that escaped before.

## 1.49.3, 1 October 2026

- "Nothing matched" was said over a pin that was placed and a price that was
  worked out.

  Reported from the live site. The reader pressed "use my location", the
  browser answered, and the page resolved it to "222. Cadde, Atakent
  Mahallesi, Küçükçekmece, İstanbul, Türkiye", dropped the pin, priced the
  cover at 9,048 USDC and drew the payout ladder. Across from all of that, the
  results area said nothing matched, and then listed Türkiye among the
  countries this cover is written in.

  setPoint writes the resolved name into the search box, and renderStep writes
  it back when the reader returns to the question, so the string being
  searched is an address. The catalogue is provinces and districts and will
  never hold a street. setPoint's own comment already said there was nothing
  to search for, on the line above the one that searched.

  The rule now sits inside renderResults, where it covers the caller that was
  noticed and the one that was not. Driven against both builds with the same
  stubbed answer from the reverse geocoder: the published one says "Eşleşen
  bir şey yok", this one leaves the results area empty. A reader who types
  Brasil still gets the real empty state.

- Wind and the season were rounded away too, and 1.49.2 said they were not.

  That release carried the tenth into the rain threshold and left the wind and
  the season rounded, on the reasoning that every place that writes them
  already agreed. They did agree. They agreed with each other and not with the
  contract, which is the only agreement that counts.

  Driven for storm cover at Trabzon: the ladder, the sentence and the summary
  row all read "81 km/h", and the contract read "80.9 km/h". An 80.95 km/h day
  pays, and all three screens told the buyer it would not.

  The register says this is every policy rather than a corner. Of the 48 storm
  decisions it was holding, not one threshold is a whole number: they are 73.5
  and 80.9. A season's level is a share of a station's normal, so the one
  drought record on the same page reads 129.6 mm, and that is the shape of all
  of them.

  The rain one was caught first only because its two spellings landed on one
  screen, the summary saying 48 mm between a sentence and a ladder both saying
  47.6. Wind and the season hid behind their own consistency. The test written
  then asked whether the screens agree with each other, which is the question
  that let this through; it asks now whether a level is ever written through
  the whole number format, which is the question that finds it.

  Fourteen sites, across the sentence, the ladder, the running summary, the
  trigger line and the table under the price, for both perils.

## 1.49.2, 1 October 2026

- One level, one spelling, on the screen where the money moves.

  Found reading 1.49.1 back on the live site, which is what that release was
  for. The rain one is the worst, because the two spellings are two different
  thresholds. Driven for rain cover at Kadıköy, one screen said all three of
  these at once:

      the sentence   "If 47.6 mm or more of rain falls ..."
      the ladder     "47.6 mm or more in a day, 2,500 USDC"
      the summary    "48 mm 2,500 · 56 mm 6,000 · 62 mm 10,000"

  48 and 47.6 are not the same threshold. A reader of the summary row would
  think a 47.8 mm day pays nothing, and it pays 2,500. rungWords rounded,
  where the sentence and the ladder both carry the tenth, because a day's rain
  level is not a round number: this place's once in ten years level is 47.6 mm.

  The quake one is smaller and was the thread that led here. The ladder read
  "A magnitude 6.5 to 7" and "A magnitude 7 or more" beside a summary row
  reading "M7.0". f1 drops a trailing zero, which is right for most of its
  sixty-odd uses, because they are ratios and percentages where 7 is the
  answer. A level is not one of those, so it has a formatter of its own now.

  rungWords also wrote a magnitude with toFixed(1), which keeps the zero and
  loses the reader's decimal mark: a Turkish reader was shown M5.2 on a page
  where every other number is written 5,2. Three more levels were written with
  toFixed(0) in the running summary, for the same reason and with the same
  effect.

  The season's rainfall keeps its rounding, and so does the wind. Those are
  hundreds of millimetres and tens of kilometres an hour, where a tenth says
  nothing, and in both cases every place that writes them already agreed.

## 1.49.1, 1 October 2026

- The magnitude ladder named levels the policy does not pay at.

  A quake policy's steps move with the building: structure() shifts the curve
  by the age of what is insured, on both indexes, so a flat in Türkiye built
  in 2019 or later pays from magnitude 5.5 and the same flat built in 1975
  pays from 5.2. The shaking rows were given the policy's own points when this
  was found there. The magnitude rows never were.

  Driven on the live site for a flat built in 1975 with the magnitude index
  chosen, the screen contradicted itself. The ladder read "A magnitude 5.5 to
  6.5, 8,574 USDC". The summary row above it read "M5.2 8,574": the same money
  at a different level, on the same screen, and the summary was the one
  telling the truth. The first row was worse than inconsistent, because
  "Nothing above magnitude 5.5 happens, nothing" is false when a 5.3 pays
  8,574. Both buildings were also told the same "about 1 in 18 years", because
  the chance column was answered at 5.5 for a policy whose first step is 5.2.

  The magnitude index is offered to every buyer of quake cover, as "Magnitude
  within a circle" beside "Shaking at my address".

- The sentence beside the ladder named a level the policy does not use.

  "The step at intensity VI is your trigger" sat directly beneath a ladder
  reading "Intensity 6.9 or more". A roman numeral is a whole number and these
  steps are not. triggerSaid had the same fault in the one place it computed
  nothing: it worked the trigger out for rain, wind and drought, and wrote in
  VI and 5.5 for the two quake indexes, which are the two where it moves.

- "How this price was worked out" showed one of the three amounts it is made of.

  The table sampled six magnitudes from 5.0 to 7.5 whichever index the policy
  was written on. For the cover a buyer gets by default, which is shaking with
  steps at 6.9, 7.9 and 8.9, four rows read "-", the two that paid both read
  17,242, the two upper steps were past the end of the grid and never
  appeared, and every row was labelled M, which is how a magnitude is written
  and not an intensity.

- The pool screen was showing three figures it had made up.

  Block and Policies armed were a random walk that had never been asked of the
  protocol, and Capital in the pool was the string 3,500,000 written into the
  markup. The protocol's own answers are 15,307,897, ten, and 274,745,994.
  This site tells a reader on seven other screens that it will not show them a
  record it made up.

- A buyer stops downloading the desk an insurer runs its book on.

  The company view, the operator view and the register of insurers are a
  second page now, built from the same parts with nothing taken out. Measured:
  635,546 B to 553,125 B built, 174,183 B to 152,175 B on the wire, 12.6% of
  what a buyer downloads to carry three screens they cannot open. What is not
  shown is that it loads faster: sixteen interleaved cold loads of each page
  at a quarter speed put the medians 44 ms apart with the quartile ranges
  overlapping.

- The home page's live bands were living in the pool view, a file named for a
  screen they have nothing to do with. Split; the built page came out byte for
  byte identical.

## 1.49.0, 30 September 2026

- The paying screen reads as six named parts, and draws the payout once.

  It was fifteen blocks in a row with nothing between them but a 14px gap, so
  a reader could not tell where one subject ended and the next began, and the
  two they most needed to find, who issues this and what it does not cover,
  looked like everything else. It is six parts now, numbered and named: your
  cover, when Clause pays, what this does not cover, who issues the policy,
  documents, payment and acceptance.

  It also held two drawings of the same three amounts. The payout ladder and
  the exceedance curve are both read off the policy's own points, so the
  figures arrived twice and the second time taught nothing; together they were
  948px of a 4,675px step. The curve keeps what the ladder cannot carry, the
  shape between the steps and how far the trigger sits from an ordinary
  reading, so it is kept, behind a disclosure in the part it belongs to.

  Its caption carried two sentences the ladder never had. Why the payout steps
  now sits beside the ladder, which shows the steps and not the reason. That
  the millimetres are a fifty kilometre grid average, which is basis risk in
  one sentence, now sits in the part that names basis risk.

  What the cover does not pay for was the last row of the summary table, under
  a 10px uppercase label: the typography of a field name, for the one thing on
  the screen a buyer is most likely to be wrong about. It is a part of its own
  and reads as two sentences.

- While the protocol answers, the paying screen shows the document arriving.

  Six headings over six empty parts, each with a rule above it, reads as a
  page that failed to load rather than one that is working. Each part now
  carries a slot the shape of what will land in it, four steps of a ladder,
  three lines of a company card. Part one keeps its sentence, because a shape
  cannot say "working out your price".

  Not every part waits for the price, and two of them were the reason to do
  this carefully. The screening panel is drawn from who the buyer is and lands
  seconds before the protocol answers; basis risk is read off the policy's own
  structure and needs no price at all. A part that already has something to
  show never shows a shape instead, and a shape stops the moment its own
  content lands rather than when the price does.

  Whether a part is filled is asked of its contents, not its geometry. An
  empty ladder is 8px tall, because the ladder carries four pixels of padding
  either side, and a height test called it full: the payout part, alone of the
  six, then never showed what it was waiting for.

- A protocol that says nothing is not a protocol that said no.

  The page told a refusal from an answer still coming by whether the protocol
  had sent a reason, and an answer that never arrives carries none. A quote
  that timed out, a connection that dropped, or any error whose body has no
  detail left the refusal empty, and every one of the five places a price goes
  read that as "not answered yet".

  Measured in a browser, holding the quote unanswered: the paying screen read
  "Pricing…" for seventy-five seconds, which was as long as the measurement
  was willing to look. No error, no alert, no way forward. The instrument was
  checked first, because a held request could have been swallowing the abort
  rather than the page ignoring it: an abort fires at 2001ms under a held
  route, so the page's own twenty-five second timeout did fire and was thrown
  away.

  A refusal is the protocol's decision and it is final. A silence is not a
  decision at all. They are told apart now, said differently, and the silence
  is offered the one thing a decision cannot be offered: another go, with the
  sentence a buyer needs first when a purchase screen goes wrong. Nothing is
  charged and nothing is signed, and it says so. Pressing Try again against a
  working protocol draws the ladder and returns the button to "Read and accept
  the contract".

- The address a buyer types is not where the policy measures.

  The place is picked on one screen and the address is typed on the next, and
  nothing joined them. The list on the second step offers provinces, because
  the same list serves a drought policy that settles at a named station. Pick
  "Adana" and the point the policy measures is the middle of Adana. Type a
  street in Ceyhan on the screen after, forty-four kilometres east, and nothing
  moves: the address is kept as text and `flow.subject` stays where it was.
  Driven in a browser, that purchase reaches the signing step with the address
  reading Ceyhan and the measurement at Adana's centre.

  The two are not the same risk. The model puts intensity 7 at Adana's centre
  once in 581 years and at Ceyhan once in 305, and the expected loss on the
  same cover is 144.76 against 224.37, half as much again.

  It would be easy and wrong to call that underpaying, and the first version of
  this note did. The premium runs the other way, 456.74 against 380.24, because
  the middle of Adana is where the book is already concentrated and capital
  there costs more: the risk load is 300.39 against 137.92. The model is doing
  exactly what it should. What the interface was doing is measuring the policy
  forty-four kilometres from the building it is written on, so a shake that
  crosses the line over the building need not cross it where the policy is
  looking. That is basis risk, and it was made here rather than by the model.

  The address is looked up now and what came back is put in front of the buyer
  with the distance, and one press moves the measurement and reprices. It is
  never moved on its own, and that is not caution for its own sake: a geocoder
  answers a street that does not exist with a street that does. "Ceyhan Caddesi
  14, Ceyhan" comes back as an address in Ankara, 398 kilometres away, without
  hesitating. A policy moved there unasked would be a worse defect than the one
  this fixes. Under a kilometre nothing is said at all, because a buyer who
  searched their own street does not need telling about it.

  Measured on the way: the eight places offered before anything is typed are
  the first eight in the index, which is alphabetical, so the most valuable
  space on that screen holds Adana, Adıyaman and Afyonkarahisar. That is a
  separate thing and is not fixed here.

- Two companies answered to "Specimen Carrier B, Türkiye", on the paying screen.

  The eight stand ins written out by hand are all in one country and are
  lettered A, B, D, E, F, G. The three generated for every country are lettered
  nothing, B and C. So Türkiye held two Specimen Carrier B, `specimen-tr-two`
  and `specimen-tr-2`, and both of them appear in the list of who will issue
  the policy, at different prices, on the screen where somebody is about to
  pay. One collision in seven hundred and two, in the one country the
  demonstration is actually used in.

  The ids do not move: a saved book holds them and renumbering would rewrite
  the terms an older policy was bought on. Only the spoken name moves, to the
  first letter that country has not used, so Türkiye reads A to H with nothing
  missing. Held for every country by a test, because the next hand written
  company added anywhere would do the same thing and nothing would have said
  so.

  Measured while looking at the confirm step, which is 4,040px tall at
  1440x900 and 4,688px at 390x844: 687 words, 294 visible nodes and 25
  controls, nine of them companies. Where the weight is, by block: check your
  answers 689px, who will issue it 628px, the payout ladder 520px, the curve
  chart 428px, what has to be proved 408px. The ladder and the chart are 29 per
  cent of the screen between them and carry the same three amounts and the same
  levels. Nothing about that is fixed yet.

  Also measured, and it corrects an assumption worth correcting: the standing
  instruction, the thing that buys cover again later, is 54px of that screen
  and already folded shut. Moving it off the confirm step is still right, and
  it is not the reason the screen is long.

- The payout ladder is a staircase on a wide screen and a flat list at 390px.

  It is the thing a buyer is actually agreeing to. On a wide screen it was
  already drawn as one: four steps, each indented further than the one above,
  the highest payment at the top, each step saying the level, what that level
  means in words, how often it happens here and what it pays. At 390px the
  indent goes and the four rows sit flush left against one bar.

  The one thing that differs between the rows is the share of the limit each
  pays, and the indent was the only thing carrying it. Every row states its
  share now, as a number between 0 and 1, measured at the İstanbul quote as
  0.0000, 0.3500, 0.7500 and 1.0000, and holds an element for the step to be
  drawn in. How it is drawn is not decided here.

  "In the recorded earthquakes since 1973" was on every row, four times, and at
  390px it wrapped to two lines each time: twelve lines of the same six words
  on the screen where the buyer decides. It is said once, under the ladder.
  Measured, that is smaller than it sounds: 497px to 479px. Eighteen pixels,
  because the element the steps will be drawn with took most of it back.

- An empty search box offered eight places chosen by the alphabet.

  The place index is in alphabetical order and an empty box was answered with
  the first eight of it, so the most valuable space on the second step held
  Adana, Adıyaman, Afyonkarahisar, Ağrı, Aksaray, Amasya, Ankara and Antalya.
  Eighty-one provinces, and the three a buyer met first were the three whose
  names begin earliest.

  There is nothing to rank them by. The catalogue carries no population, and
  ranking by the demonstration book would be ranking by figures this repository
  makes up. So nothing is offered: the box says where cover can be priced and
  what it takes, and the whole catalogue is one press behind a disclosure,
  named for the country it is of rather than for how many rows it has, because
  cover is priced in seven countries and the list is one country's provinces
  and districts. It is built when it is opened: a hundred and three places is
  five hundred nodes on a step that already carries a map.

  Measured at 1440x900, before anything is typed: fourteen controls became six,
  the step went from 1,061px to 664px in a 900px window, and what is on it went
  from 8 places to none. Asked for, the list gives all 103. Typing "Kadıköy"
  answers with six, the first of them İstanbul, Kadıköy.

  The audit this came from said the second step was dominated by an 81 province
  wall. Measured today it was eight, not eighty-one, which is worth saying
  because the fix that followed from the wrong number would have been to shrink
  a list that was already short.

- The live bands had been stopped for every reader.

  Three bands under the home page carry the readings the protocol settles
  against: the earthquakes of the last day, today's weather, the delays at the
  airports. They scroll because there are more of them than fit, and the
  duplicate copy inside each is what makes the loop seamless. Four declarations
  appended to the stylesheet turned all of that off, under a note calling them
  ticker-tape decoration.

  The rule they were written against is about decoration behind the words.
  These are the words, and a register that has stopped looks like a register
  that is wrong. Stopping was already handled where stopping is what somebody
  asked for, forty lines above: a reader who sets prefers-reduced-motion gets
  no animation, no duplicate and a track they can scroll themselves, and hover
  or focus pauses it for everybody else. Turning it off for everybody left both
  of those as rules that could never apply.

  Measured with the movement back: 135.9px in two and a half seconds normally,
  0.0px in a context asking for less motion. A test holds both, and fails
  either when the band is stopped for everyone or when the pause under the
  pointer is taken away.

  The stylesheet here is the pass that stopped it putting it back, arrived at
  independently and better than the version that replaced it: the same movement
  restored, and the eleven declarations that had been appended folded into the
  rules they were overriding at the same time. That version is the one kept.

## 1.48.0, 30 September 2026

- "Nobody decides whether you get paid" was the largest line on How it works,
  and the page's own questions page said otherwise four screens away.

  A licensed company decides whether to issue the policy: the premium is held
  and not taken while it screens the buyer against sanctions lists, confirms
  who they are above a certain size, and confirms the thing is theirs.
  Validators decide what reading reaches the chain, and the page says in the
  same breath that disagreeing is possible and only expensive. Both are
  decisions, and both are somebody's.

  What nobody does is look at the damage afterwards and form an opinion about
  what it was worth. That is the thing the product actually removes and the
  thing worth saying, so the line is "A measurement decides what you are paid,
  not an assessor", in six languages. The paragraph under it already said as
  much and did not need changing.

- The line the three deferrable surfaces sit behind, drawn where it can hold.

  A company's desk with the operator's screens, the proof register with the
  chain beside it, and the profile: 193,502 bytes of script, and a buyer walking
  a whole purchase touches 9, 14 and 5 per cent of them. They are the three
  worth fetching only when somebody opens one.

  They could not be. Sixteen declarations written inside them were used outside
  them, and none of the sixteen was incidental: the cover flow reads the buyer's
  saved things through `loadAssets` and `ASSETS`, My cover draws its payout,
  mandate and funding panels from the profile's file, signing out clears the
  operator's session through `opSignOut`, and `downloadCsv` and `bindTokens` are
  simply general helpers that happened to be written in a desk. Moving those
  sixteen pulled sixteen more after them, and those settled after three rounds.

  Thirty-two declarations are in `site/app/44-always-loaded.js` now, on the side
  of the line that is always in the page. Nothing else changed: no line of the
  script was lost or written, only moved, which is checked by comparing the
  parts line for line before and after. Every one of the fifteen screens was
  opened in a browser afterwards and every one of them draws, with no error
  anywhere.

  The line itself is now a test rather than an intention. One new name declared
  on the wrong side is a file that can no longer be deferred, and until somebody
  tried it and measured, nothing would have said so.

  This does not defer anything yet. The three are still inside the one closure,
  and taking them out of it is the next step: they reach for 66 names the rest
  of the closure declares, of which 62 are never reassigned and can be handed
  over by value, and four, `link`, `t`, `LANG` and `identity`, are, so they have
  to be read through the thing that holds them rather than copied out of it.

- The script is twenty-three files, and site/index.html is no longer a page.

  598,208 bytes of it, 9,617 lines, in one block. It is `site/app/` now, cut at
  the headings the script had already written for itself, and the build joins
  the parts back where they were listed. The published page is byte for byte
  the one published before either split, 623,103 bytes, down to the build name.

  The first attempt was wrong and the browser said so in four words. The parts
  were linked as scripts for a browser to fetch, and the first one stopped it
  on "Unexpected end of input": the whole script is the inside of a single
  `(function(){ ... })()`, so a part cut out of it opens braces it never
  closes, and separate files cannot share a closure. Twenty-one of the
  twenty-three parts parse alone and two do not, which is exactly the way for
  an arrangement like this to look right and be broken.

  So the parts are listed and not fetched, under an attribute a browser does
  not act on, and `site/index.html` stopped being a page a browser can run.
  `python3 site/build.py --dev` assembles it into `site/dev.html`, beside it so
  every relative path still resolves, unminified so it can be read and stepped
  through. What is checked in a browser is now what is published rather than a
  second arrangement that drifts from it.

  Fifty-two tests were reading the script out of `site/index.html` and would
  have gone on passing while reading nothing at all. They read the page as a
  browser ends up with it, markup and styles and script together, through one
  helper.

  One of those tests was mine, written earlier the same day, and it had the
  fault it was written to prevent. It proved the rounding scenario was real by
  checking that 120 m² at 519.29 per m² falls between two whole numbers. The
  rate reached 519.33 and it does not any more, so the test went quiet rather
  than red. It now looks for an area that splits instead of naming one.

- Measured before deciding what to do about the weight, and the measurements
  cancelled the plan they were taken for.

  Splitting by route, which is what the weight was assumed to need, would move
  46 KB of 598 KB. Every screen runs about the same 145 KB and differs by a
  slice: proof 13,970 bytes, insurers 12,299, rules 7,578, and the rest under
  three thousand each.

  The plan was route-splitting because 76 per cent of the script never runs on
  a visit. It does not follow, and the second measurement says why. Walked
  through a whole purchase, from the home page to the signing step, a buyer
  runs 208,921 bytes of 598,203, and 389,282 bytes, 65 per cent, never run at
  all. What is heavy is not the screens; it is signing in, paying, and the
  desks a company and an operator work at.

  Attributed to the files the script is now cut into: a buyer touches 9 per
  cent of the 92,666 bytes of company and operator, 14 per cent of the 57,870
  of proof and chain, 5 per cent of the 42,966 of the profile. Emptying those
  three and building takes the published page from 623,725 bytes to 479,626,
  and the wire, brotli, from 137,548 to 107,531. That is the prize for
  deferring them, measured rather than guessed: 30 KB fewer to download and
  144 KB fewer to parse on a phone. They cannot be deferred while they are
  inside the one closure, and that is the next piece of work rather than this
  one.

- The stylesheet is nine files and the published page is unchanged.

  `site/index.html` is 897,113 bytes and 13,894 lines, and 156,879 of those
  bytes were a single style block inside it. Nothing could be worked on in
  there by two people at once, and nothing could be worked on in there by one
  person without reading past the other 740,000 bytes to find it.

  It is `site/styles/` now, cut at the headings the stylesheet already wrote
  for itself: tokens, header, controls, views, the live strip, home, the
  purchase flow, how it works, and the rest. The build concatenates them in
  the order the page links them, so what is published is one inlined block as
  before. It is byte for byte the page that was published before the split,
  623,103 bytes, which is the point: this changed nothing a reader can see.

  Two things had to be got right. Order is the cascade, and a stylesheet read
  out of order fails silently, so the numbers in the file names carry it and a
  test refuses a page that links them in another order or leaves one on disk
  unlinked. And a relative path in a stylesheet is read from where the
  stylesheet is: the fonts and the mark 404ed the moment they moved into
  `styles/`, so the parts say `../fonts/` and the build takes the `../` off
  when it puts them back in the page. Both are held by tests that fail when
  the rule is broken.

  Measured while doing it, because the figures this was planned against were
  three days old and two of them were wrong. The script, not the markup, is
  what a visitor pays for: 76 per cent of the page's 600,722 bytes of script
  never runs on a visit, where an earlier count said 27 per cent, and that
  count was reached by adding up function spans that contain one another. Of
  the fifteen screens the document holds, five hold fewer than twenty nodes
  each, so the operator, company and profile surfaces a reader never opens are
  already empty shells rather than the weight they were assumed to be. The one
  developer surface that is heavy is the chain page, at 222 nodes and 30,769
  bytes of markup.

## 1.47.0, 29 September 2026

- Two covers on one building felt the same earthquake as two different
  earthquakes, and splitting a policy made the risk smaller.

  The intensity equation says what shaking a magnitude produces at a distance,
  and the scatter around it is the difference between that prediction and what
  the ground actually does. The scatter was drawn from a stream seeded by the
  policy identifier. So the earthquake was shared, as it should be, and then
  each policy was told a different intensity for it: of the trials where either
  of two covers on one address was paid, one in four paid only one of them.

  The comment above the line said two houses on the same street feel the same
  earthquake a little differently, which is true and is what the scatter is
  for. It is a fact about the ground under an address, not about the contract
  written on it, and the seed did not know the difference.

  What followed is worse than a mispriced policy. Ten pieces of one cover
  settled as ten independent sites, so the book's own arithmetic stopped
  holding: a million of Kadıköy cover split ten ways measured less risk than
  the same million whole, and the pool's capital fell when a buyer split cover
  it had already agreed to carry. This was the real engine of the splitting
  arbitrage recorded in 1.46.0. The floor added there was a bound on the
  symptom; this is the cause.

  | a million of Kadıköy cover | was | now |
  |---|---:|---:|
  | in one policy | 108,249.23 | 112,134.92 |
  | ten bought one after another | 103,418.90 | 112,134.92 |
  | ten locked at the same moment | 107,460.44 | 112,134.92 |

  Seeded by the address, the three are the same figure to the cent, which is
  what marginal allocation requires and what it could never deliver while the
  pieces settled apart. A hundred thousand of Kadıköy cover moves from
  11,289.31 to 11,213.49 against a book of two hundred İstanbul policies, and
  New York is unchanged at 29.02.

  The same seed was thinning background events for a circle smaller than the
  reference catalogue's, so two covers on one address with one radius kept
  different events. That is now keyed to the address and the radius too.

  A change that makes co-located cover settle together raises the capital a
  book needs, and a pool whose requirement jumps past its own funds stops
  writing business, which is the failure a buyer sees as the site refusing to
  sell. Measured before shipping, on a book of two hundred policies across five
  Turkish locations carrying 20,502,714 of cover, the requirement moves from
  10,694,951.84 to 10,710,991.28. That is a seventh of one per cent. The book's
  worst half per cent is already dominated by ruptures that pay almost every
  policy in it at its top band, and the scatter this corrects was never what
  put them there; what it was distorting is the marginal reading of one more
  policy at an address the book already holds, which is a price rather than a
  solvency position.

  What this does not close is the last line of 1.46.0: quotes locked at the
  same moment, each priced against the book as it was. Where the floor sets the
  price that gap is nothing, because the floor is proportional to the limit;
  where the measured marginal is linear in the limit, as it is at an address
  the book already holds, it is also nothing, and the table above measures it
  at zero. It is real only in the band where the measured marginal is
  superlinear, and it is still open there.

- 2,859 of the 3,408 American places this product offers can be bought today.

  The count that was being reported was curves fetched, and it answers the wrong
  question. A place is sellable when a published curve sits within sixty
  kilometres of it, not when it has one of its own, so most of the places no
  build has reached are already priced from a neighbour's curve. What a buyer
  cares about is whether their address is one of them.

  | | places | share |
  |---|---:|---:|
  | sold today | 2,859 | 83.9% |
  | refused: our model and the published one disagree | 382 | 11.2% |
  | refused: nothing published within sixty kilometres | 167 | 4.9% |

  The 382 are the guard on that disagreement doing what the note beside it says
  it does: "about one place in nine is refused by this, in both countries."
  Measured here at 11.2%, which is that figure. So the guard is not news. Where
  it fires is.

  Three hundred and seventy one of them, 97%, lie between longitude -100 and
  -80: the central and eastern United States. Across that whole band our own
  model reads intensity VII at between once in 85,726 years and once in 164,848
  years, a spread under a factor of two over a thousand kilometres, while the
  published model runs from once in 477 years at Memphis to once in 7,357 at
  Jacksonville, a spread of fifteen. Ours is not disagreeing about the level. It
  has no spatial resolution there at all: it is reading a regional floor and
  calling it an answer.

  | | published | ours | factor left after the map |
  |---|---:|---:|---:|
  | Memphis | 1 in 477 | 1 in 129,275 | 39 |
  | Nashville | 1 in 1,375 | 1 in 146,520 | 5 |
  | St. Louis | 1 in 1,113 | 1 in 85,726 | 4 |
  | Atlanta | 1 in 3,274 | 1 in 155,063 | 4 |
  | Jacksonville | 1 in 7,357 | 1 in 164,848 | 2 |

  Memphis is the case that makes it plain. It is the most exposed large city in
  the eastern United States and our model cannot tell it from Jacksonville, six
  hundred miles away. Which sources the published model carries there is not
  measured here and is not guessed at; what is measured is that ours carries
  none of them.

  Three hundred and thirteen of the 382 sit within a factor of four of the line,
  155 of them at two and 61 at three, so moving the guard would open most of
  them. That is the wrong repair: it would sell a price two, three or four times
  light in the places our model understands least. The repair is the model.

  The 167 are the ones a deeper build closes, and they are the smaller half.
  Smaller than they look, too: the last fifty curves this release fetched moved
  the sold count by nothing at all. One place crossed over, and it crossed from
  one refusal to the other rather than into being sold, because a curve arriving
  near it only exposed that the two models disagree there. Depth buys precision
  at addresses already covered by a neighbour's curve; it does not buy reach.

  Behind that, the curve count went from 1,240 to 1,500: CONUS 1,486, Hawaii 13,
  Alaska 1. Of the 1,500 largest American places three are still without a curve
  of their own, Hot Springs, Glendale Heights and Butte, and each gap is named
  with its coordinate.

  The USGS hazard service was up and down throughout. One pass took the file
  from 1,240 to 1,318 and named 182 places it could not reach, a later one
  reached 1,410 with nothing missed, a pass over what was left returned a single
  curve out of eighty three, and the next morning it answered six probes out of
  six. A deeper run was then started and stopped rather than waited out: it was
  managing about one place a minute, with no open socket and flat CPU between
  fetches while three probes of the same service from the same container
  answered at once, so the remaining five hundred places were eight hours away
  and every figure written about the file went stale while it moved. A limit is
  a throttle on the asking and not a decision about what to keep, so every curve
  already fetched is still in the file, and the depth the model declares is
  settled against a run that finished.

  Anchorage and Hilo are sold. Fairbanks and Juneau are still refused, because
  nothing published sits within sixty kilometres of either; they open when the
  build reaches them.

  Puerto Rico is not covered, and it is worth saying why rather than leaving it
  as a gap somebody fills carelessly. The USGS does publish a model for it,
  `prvi-2025.R1`, NSHM Puerto Rico and U.S. Virgin Islands 2025, bounded
  15.0 to 21.2 north and -70.95 to -61.7 east. It publishes peak ground
  acceleration and twenty one spectral accelerations, and no peak ground
  velocity. Every curve this product holds is peak ground velocity turned into
  intensity by Worden, Gerstenberger, Rhoades and Wald (2012), and one country
  file carries one measure and one conversion. Opening Puerto Rico means a
  second conversion, from acceleration, with its own scatter, and a model file
  that can say which of the two a point was built with. That is a change to
  make deliberately, not a fourth line in a table of model names.

  Nothing prices there meanwhile: the box check refuses San Juan rather than
  asking the conterminous model, which answers for a point six hundred
  kilometres outside its own mesh with a status of success.

- A storm or a car quote says what it sits beside, as an earthquake quote does.

  Wind and rain settle on a station's reading, and both carry a shared factor
  across a region in the simulation: a front is hundreds of kilometres wide and
  one storm system floods several provinces in the same year. So cover on one
  station accumulates the way cover on one fault does, and the capital charge
  already reflected it.

  What the quote said about it was nothing. An earthquake quote named the
  policies near it and a drought quote named the ones on its station, while a
  storm or a vehicle quote explained its price with silence. That is the same
  price shown to one buyer with its reason and to another without. Both now
  count the cover already settling on their station and say what one bad day
  does to it, or say that nothing else settles there.

- A gap in the published coverage says which place it is.

  The list of places a build could not reach held bare names. Three hundred and
  eight American names repeat, covering seven hundred and sixty nine of the
  places this product offers, so a list holding "Warren" did not say which
  Warren had no curve. That is the same lesson the already-fetched set learned
  when keying it by name silently skipped the second of every pair, and the gap
  list was the one place it had not been applied.

  It cost a wrong answer while settling this release's declared depth: reading
  the gaps as though a name were a key put some of them at ranks past 1,500 in
  a run that only asked for the first 1,500. Each entry now carries its
  coordinate.

- Two passengers on one aeroplane were delayed by different amounts.

  The same seed, in the same place: a flight's delay came from a stream keyed
  to the policy, so every cover written on one aeroplane landed at a different
  time. The carrier's bad day was already shared across the book, which is the
  correlation between different flights of one airline and a weaker thing than
  this one. It is now keyed to the flight: the number, the date and the two
  airports. Covers on one flight are paid or not paid together, and covers on
  the next flight out are still their own.

- Every earthquake quote was told it deepened a concentration, wherever it was.

  The sentence a quote carries about its neighbours counted the policies the
  pool already holds "at this location" by comparing `subject["location"]`, the
  place code the buyer typed. The peril resolves that code to a latitude and a
  longitude and drops the key before the engine ever sees the subject, so the
  comparison was `None` against `None`: true for every pair of earthquake
  policies on earth.

  A New York quote was therefore told the pool already held two hundred
  policies at its location while every one of them was in İstanbul, on the same
  screen that priced it as diversifying. The two sentences contradicted each
  other and the wrong one was the confident one. The other branch, written for
  a policy that really does spread the book, could never be reached at all.

  Neighbours are now counted by distance: two policies are near enough that one
  earthquake can pay both exactly when their circles overlap, which is when the
  centres are no further apart than the two radii added together. Against a
  book of two hundred İstanbul policies, a Kadıköy quote now counts 88 of them
  and New York counts none, and each is told which.

  The price did not change. Only what the quote says about itself did, and it
  was saying something untrue.

- One quote, two amounts: 49,228 USDC on one screen and 49,227 on the next.

  What a home is worth to rebuild is a float. The line a buyer reads on the "at
  risk" step printed it through `money()`, which rounds to the nearest whole
  number above a thousand. The same float became the cover ceiling, the top
  preset and the figure in the contract through `Math.floor`. A 120 m² İstanbul
  flat built in 2005 lands between two whole numbers, so the buyer was shown one
  amount, agreed to it, and then saw a different one on every screen after it,
  on the desktop and on the phone, in one uninterrupted session.

  Neither number was wrong by much and that is what made it bad: nothing looked
  broken, so nothing would have been reported. The value is rounded down once
  now, where it is worked out, and everything downstream carries that same whole
  number.

- The button said three steps and the flow has five.

  "Get cover in three steps" is the most clicked thing on the site, and it was
  wrong about the only thing it promises. The stepper names its own steps, What,
  Where, At risk, How much, Confirm, and the routes run from `#/cover` to
  `#/cover/5`. The test reads the count off the stepper, so the button and the
  flow cannot drift apart again.

- The showcase policy on the home page was written on two measurements at once.

  "if shaking ≥ M5.5 within 50 km" names a magnitude threshold and calls it
  shaking. Magnitude is the size of the earthquake at its source, one number for
  the whole event; shaking is what arrives at an address and is different at
  every address. Both are real products here, and the picture was of neither.
  The beat below it settles the rule with an M7.2 reading, which is a magnitude
  reading, so the rule is the magnitude one now, all the way through, in all six
  languages.

## 1.46.0, 29 September 2026

- A risk the book never feels was written for nothing.

  A buyer asked why New York costs 13.81 and Türkiye 7,000, and the answer is
  worse than the question. The two addresses differ by 129 times in expected
  loss, which is the hazard and is right: intensity VII once in 78 years
  against once in 5,952. They differ by 718 times in premium. All of the
  difference beyond the hazard is a risk load New York does not pay.

  New York's marginal capital was exactly zero. The book is concentrated in
  Türkiye, so its worst half per cent is Turkish earthquakes, and a policy that
  pays once in three thousand seven hundred years is never in it. The marginal
  reading of that is zero and the reading is correct; the pricing rule built on
  it is not. The policy was sold for its expected loss plus expenses, 13.79
  against an expected loss of 12.77, which is ninety three per cent of the
  premium expected to be paid straight back out. Miami was the same at ninety
  two.

  Two things followed and neither is acceptable. A concentration could be built
  for nothing one policy at a time, because the hundred thousandth New York
  policy is priced against a book that does not contain the other ninety nine
  thousand. And the charge was not proportional to the cover: a million of New
  York cover in one policy measured 8,845 of capital and cost 1,198.55, while
  the same million split into ten policies measured zero and cost 137.90. The
  same risk, split ten ways, for a ninth of the price; anyone wanting a million
  simply bought ten.

  A policy is charged for at least a twentieth of the capital it would need
  standing alone, however well it sits against today's book, because today's
  book is not tomorrow's. Ninety five per cent diversification credit is
  generous by any capital model's standard, so this is a floor rather than a
  charge: it binds only where the measured marginal was near zero, and every
  price with a real marginal charge is untouched.

  Standalone capital is proportional to the limit, so wherever the floor is
  what sets the price, splitting cannot get under it: ten policies of a hundred
  thousand cost exactly what one of a million costs. That is not the whole of
  the splitting question and it should not be read as though it were. Above the
  floor the measured marginal takes over and it is superlinear: on the live
  book the floor sets New York's price up to about 200,000 of cover, and beyond
  that the same cover costs 29.02 per hundred thousand split and up to 135.28
  whole. What stops that being free is that binding a policy puts it in the
  book and re-prices the next one. What does not stop it is a set of quotes
  locked at the same moment, each holding its price for ten minutes against the
  book as it was. That gap is open, and it is written here rather than left to
  be discovered.

  | | was | now | loss ratio |
  |---|---:|---:|---|
  | New York | 13.79 | 29.02 | 0.93 → 0.44 |
  | Miami | 1.31 | 2.75 | 0.92 → 0.44 |
  | Los Angeles | 883.37 | 883.37 | unchanged |
  | Kadıköy | 10,010.33 | 10,010.33 | unchanged |

- Three answers to "what does this pay, and how often", on one policy.

  An older building is damaged by less shaking, and the policy carries that: in
  İstanbul the steps are 6.25, 7.25 and 8.25, in New York 6.62, 7.62 and 8.62,
  and they pay 35, 75 and 100 per cent of the limit. Neither table on the page
  said so, and they did not agree with each other either.

  | | first step | second | third |
  |---|---|---|---|
  | the contract | 35% at 6.25 | 75% at 7.25 | 100% at 8.25 |
  | the page, step two | 25% at VI | 60% at VII | 100% at VIII |
  | the page, confirm step | 0% at VI | 35% at VII | 100% at VIII |

  The table on the second step had all three levels and all three shares
  written down by hand, and read the hazard at those round numbers: a New York
  policy looked as though it paid once in 1,788 years, when it pays once in
  about 3,100, because 6.62 is a level that happens half as often as 6.0. The
  table on the confirm step read the policy's own curve, which is right, at VI,
  VII and VIII, which is not: at 6.0 an İstanbul policy pays nothing, so its
  first row said zero and its second showed the first step's share under the
  second step's name.

  Both are built from the curve's own points now, which is what the car and
  storm rows beside them have always done.

  The sentence above them had the same three facts written into it by hand:
  "you receive a quarter, rising to the full amount at intensity VIII". The
  cover pays 35 per cent at its first step, not 25. The magnitude sentence
  beside it named 5.5 and 7 the same way, and those move with the building too.
  All four sentences read their levels and their first payment from the policy
  now.

  The price bar had the same fault in one line: it named each rung by rounding
  its level to the nearest roman numeral, so New York's 6.62 was printed as
  VII. A numeral is a whole number and these steps are not. It is kept where
  the step really is one, which is a building of the current code, and the
  number itself is printed otherwise.

- The American model says what it covers, which is the 720 largest places.

  It holds 1,240 curves in all: the 720 largest American places, complete but
  for six, and 520 more that came with them. Six is what the publisher would
  not answer for, and they are named in the file rather than passed over:
  Lauderhill, Rock Hill, Silver Spring, West Gulfport, Flower Mound, Mira Mesa.

  The scope is what the publisher could actually be asked for today. The USGS
  hazard service answered about one request in six through most of this,
  failing with its own backend's error, and a run scoped to fifteen hundred
  places ended with three hundred of them unread. A model file that claims
  fifteen hundred and holds twelve hundred is not honest about itself, and the
  test that holds the unread list under a fiftieth of the curves is what said
  so. The scope moves down to what was delivered rather than the test moving
  up, and it rises again as the service allows, without refetching anything.

- A rare risk knows its own capital without drawing for it.

  The floor rests on standalone capital, so that had to be a number the
  simulation can produce, and for a rare risk it cannot: in twenty thousand
  trials New York pays five times, and in a third of four thousand trial runs it
  pays none at all, for a standalone requirement of exactly zero and a floor of
  five per cent of nothing.

  It does not have to be drawn for. Below the solvency tail the answer is exact.
  If a policy pays less often than one time in two hundred, every outcome in
  which it pays is inside the worst half per cent, so the tail average is the
  expected loss divided by that half per cent and the capital is 199 times the
  expected loss. The same number however many trials are run.

- Anchorage can be priced.

  Our own model answered Anchorage, Fairbanks, Juneau, Honolulu and Hilo with
  the same number: once in 11,119 years at intensity VII. Not a measurement, a
  default, at an address four hundred kilometres from the largest earthquake
  ever recorded in North America. The USGS puts intensity VII there at once in
  87 years.

  The catalogue stopped at the lower forty eight because one box cannot hold
  all three. That reasoning is right, and it is about the fit rather than the
  country. Over its own box Alaska gives a b value of 0.829, a largest event of
  8.7 and 20.9 magnitude five earthquakes a year, against the lower forty
  eight's 0.745, 7.8 and 7.2. Fitted together, each would be described by the
  other.

  So a region is the extent a catalogue can be fitted over as a unit, and a
  country is whose law and licence the policy is under. Those were one field.
  Alaska and Hawaii are regions of the United States now, with catalogues of
  their own, and the quantile map has something to map:

  | | ours, was | ours, now | the publisher |
  |---|---:|---:|---:|
  | Anchorage | 1 in 11,119 | 1 in 41 | 1 in 87 |
  | Hilo | 1 in 11,119 | 1 in 108 | 1 in 105 |
  | Honolulu | 1 in 11,119 | 1 in 15,398 | 1 in 3,406 |

  Anchorage, Hilo and Honolulu reconcile at a residual of 1.00 and price. Los
  Angeles and New York are unchanged. Anchorage comes out dearer than Los
  Angeles because it is nearly twice as likely to reach intensity VII, 1.75%
  against 0.96% over a year.

  Neither new region passes its own backtest, as the lower forty eight does
  not. The publisher's curves entitle all three; our catalogue supplies the
  events the capital model draws, and those are Alaskan events now rather than
  a floor.

- The model card a buyer opens is the model that priced them.

  The page linked the card by the country the grid reported, which was the same
  thing as the model until the United States became three of them. A buyer in
  Anchorage following that link would read a model fitted on ground three
  thousand kilometres away, with a different b value and a largest event nearly
  a whole unit smaller, and would have no way to tell.

- Eight Springfields, five Columbuses, and one curve between them.

  The published build kept the places it had already fetched as a set of names,
  so the second Springfield was counted as done before it was ever asked for.
  The United States offers eight of them, five Columbuses -- Ohio at nine
  hundred thousand and Mississippi at twenty three -- and three hundred and
  eight repeated names in all, covering seven hundred and sixty nine of the
  places this product offers. Japan has forty three, among them the two Sendais
  this repository already found once, in a test, and fixed there rather than
  here.

  The cost is not a wrong price: the runtime searches by coordinate and will
  not find a Missouri curve near Massachusetts. It is a place that is never
  fetched and never reported as missing, which is worse, because nothing in the
  file says it is not there. It showed up as 745 names matching 656 points.

- A limit is a throttle on the asking, not a decision about what to keep.

  It decided both, so one run with a smaller limit silently deleted every curve
  past it: four hundred American curves, fetched over hours from a public
  service, thrown away by an argument that reads like a patience setting. A
  curve is dropped only when its place is no longer offered at all.

- Four interrupted builds in a row shipped a model that named no gaps.

  The partial save carried the missed list as it stood when the run began, not
  as it stood when the save was written, so a build killed half way wrote a
  file saying nothing was missing while its own log showed a hundred refusals.
  The first pass that ran to the end is what exposed it: a thousand and twelve
  misses appearing at once, none of them new. The test that holds the missed
  list under a fiftieth of the points had had nothing to see.

## 1.45.0, 29 September 2026

- Honolulu is open, and Anchorage says why it is not.

  The build asked the USGS about Anchorage and was told there is no curve
  there. Anchorage: four hundred kilometres from the 1964 rupture, the largest
  earthquake ever recorded in North America. Honolulu, the largest American
  place after the two hundred already held, came back the same way. So would
  the other forty six Hawaiian and four Alaskan places this product offers,
  which sit further down the list by population and will be fetched as the
  build works through it.

  Nothing was wrong with the publisher. The United States is three national
  models, not one, and this build knew only the first. CONUS 2023 stops at the
  border of the lower forty eight; Alaska has had its own model since 2007 and
  Hawaii since 2021. Each is asked about the ground it covers now, and each
  curve carries the name of the model that drew it, because "the USGS national
  model" is true of Anchorage, Honolulu and Brooklyn alike and tells a reader
  in any of them nothing. The two hundred and sixty curves already held were
  stamped from their own coordinates rather than fetched again: which model
  covers a place is arithmetic, not a request. All fifty two American places
  outside the lower forty eight fall inside exactly one of the three
  footprints, which is checked in the tests rather than assumed in a comment.

  Honolulu prices. Its ladder reads once in 854 years at intensity VI, once in
  3,405 at VII, once in 17,543 at VIII, which sits between New York and Los
  Angeles, and a year of 100,000 in cover comes to 59.34 on the live book.

  That figure was first written here as 444.90, which is what the same policy
  costs as the only policy in an empty book: it carries the whole capital
  requirement on its own. Against a book of a hundred thousand others it adds
  far less, and the protocol charges what it adds. The two numbers are the
  standalone and marginal capital of 1.44.4, eight times apart at this address,
  and the live one is the one a buyer pays.

  Anchorage does not, and the existing guard is what stops it. Our own
  catalogue has no Alaskan events at all and answers with the global
  background floor, once in 11,119 years at intensity VII, against the USGS's
  once in 87. The quantile map closes what it can and is held at its two
  intensity bound; a factor of six is left, past the factor of two this
  protocol will write on, and the address is refused.

- Whose country it is and which grid prices it are two questions.

  They were one function, and they came apart the moment a published curve
  reached ground the catalogue was not fitted on. Honolulu is in the United
  States and outside the box the American catalogue was built from, so cover
  there was refused with "no tested earthquake model covers this location yet",
  which was true of our catalogue and not true of the ground.

  Asked which country, the published curve now answers: it records who
  published it, and that is whose law and licences apply. Asked which grid, a
  model whose box does not reach the address answers with itself no longer. A
  grid asked about a point outside its own box sums zero cells and returns
  zero, which reads as "no earthquakes here" and means "this grid is not about
  here" -- Honolulu would have been priced at no hazard at all rather than at
  the background floor.

- A refusal quotes what the two models say, not only what is left between them.

  "This address cannot be priced: the national model and our own earthquake
  model disagree by a factor of 6." Six is the residual after the map has done
  what it can, which answers a different question than the one a reader is
  asking, and it can be smaller than the gap or larger. At Anchorage the two
  models are 128 times apart and the residual is six.

  Both figures are carried now, straight off the two curves: "puts shaking of
  intensity VII here at about once in 87 years and our own events reach once in
  11119". Plain digits, no thousands separator, because this sentence is
  translated by pattern and an English separator reads as a decimal point to
  half of the people who see it.

- A distance that is not about this site is no longer quoted.

  "No mapped system dominates this site: the nearest trace is about 19253 km
  away." The trace database is Türkiye's, so for a point in Hawaii it answers
  with the distance to Anatolia. The sentence contradicted itself in its own
  second clause. It was unreachable outside Türkiye while every such address
  was refused; opening Hawaii made it a sentence a buyer reads. Where a trace
  is near enough to bear on the site it is still named, and Ankara's is 96 km
  off.

- Forty more American places from the USGS, 220 to 260. The publisher's own
  backend failed for an hour in the middle of the run, which the build reports
  as missed places rather than as curves.

## 1.44.4, 29 September 2026

- The price on the screen is the price that will be charged, from the first
  moment there is one.

  It was not. A buyer saw 4,003 USDC, captioned "before the company's fee", and
  two seconds later saw 6,827, captioned "all in". Seventy per cent apart. Both
  captions were true and neither helps someone who reads the first figure and
  presses Continue.

  The page had a model of its own so it could answer the slider instantly, and
  the first figure was that model. It could not agree with the protocol, for
  two reasons that are worth naming:

  The page capped its risk load at twice the expected loss, taking the lesser
  of the cost of capital and a reinsurer's price at three times expected loss.
  Every catastrophe took the second branch, so every premium came out at 3.08
  times expected loss whatever the hazard. The protocol stopped doing that some
  time ago, and for a plain reason: no treaty exists, nothing here cedes
  anything, so there is no cheaper branch to take. This page went on taking it.

  And the capital is not the same capital. The page can only compute what one
  policy needs standing on its own; the protocol charges what the policy *adds*
  to the book it is joining. For one address in Kadıköy, 100,000 of cover for a
  year, the protocol answers today with a standalone capital of 80,792.88 and a
  marginal capital of 67,729.04, and the second is the one in the price. A
  browser cannot compute it, because it does not have the book, and it moves as
  the book moves.

  So the bar and the summary rail now show an em dash and "working out your
  price" until the protocol has answered for this exact selection *and* the
  company's fee is in, and then show one figure, once. The captions that
  existed to excuse a provisional figure went with it.

  The cap is gone from the page's model too, so the one place it is still shown
  -- not connected, where the banner at the top says everything below is
  computed in the browser and nothing here is real -- is the same mathematics
  as the protocol rather than a capped version of it.

- The step a buyer signs on is drawn from the protocol's answer or not drawn.

  Fixing the bar was not enough, because arriving at the confirm step threw the
  protocol's answer away and asked for a fresh one. For as long as that round
  trip took, the last screen before the money moves drew its sentence, its cost
  breakdown, its payout table and its summary row from the browser's model: the
  figure that had just been kept off the bar for being the wrong one, printed
  four times over.

  The answer already in hand is kept now while a replacement is asked for --
  priced() checks that an answer belongs to what is on the screen before it
  uses it, so keeping it cannot show anything stale -- and where there is no
  answer for this exact policy, the panel is not drawn at all. It says it is
  working out the price, the Continue button says the same, and the whole panel
  appears at once when the answer lands.

- A bar that stood down does not count back from the old price.

  The figure animates into place, counting from whatever the bar said last,
  which it keeps in a data attribute. With the bar now standing down to an em
  dash between selections, that attribute held the price of a policy nobody is
  buying any more, so the new figure arrived by sweeping down from it: 1,283 to
  517 over four hundred milliseconds, measured in a browser walking the flow
  against a local protocol. To anyone glancing at the bar that is the price
  changing while they watch. Standing down forgets the figure now as well as
  erasing it, and the same walk shows one step: em dash, then 517.26.

- The quote is filed under the company it was struck with, so it is not stale
  on arrival.

  The cache key was taken before the offers came back, which meant it carried
  no company. The offers then named one, the key moved, and the answer that
  arrived a moment later did not match the question any more. Nothing was wrong
  with the number; it simply did not count, so the page asked again and the
  buyer waited through two round trips for one figure. The key is now taken
  once the company is known, and a refusal from the previous attempt is cleared
  when a new one starts rather than left to caption the next price.

## 1.44.3, 29 September 2026

- The ceiling now says what it leaves out.

  A buyer whose flat is worth a hundred million and who is offered cover of two
  asks one question, and it is a fair one. The answer is that the cover is the
  building and the flat's worth is mostly the land under it, which an earthquake
  does not take: "This is the building, not the land and not what it would sell
  for. An earthquake takes the building down; the land is still yours."

  The rebuild schedule says the same thing in its own words, "excludes VAT,
  land, infrastructure and site works", and the page has been carrying that note
  in its payload and keeping it to itself. It is printed now, beside the source.

  What the ceiling does vary by was already shown and is worth restating: floor
  area, and the year the building went up. A 120 m² flat built in 2010 carries
  52,299 and the same flat built in 1975 carries 34,244.

  What it does not vary by, in Türkiye, is the district, and that is a fact
  about Türkiye rather than a gap here: the Ministry publishes one national
  table, TÜİK's index has no regional breakdown, and DASK's per square metre
  value is the same everywhere. The page says that too, in the source line.

  What it should vary by and does not is the building's class. The Ministry's
  schedule has classes and we use III-B for every flat, so a high specification
  building is valued as a standard one. That is a real gap and it is blocked on
  the table: every Turkish government domain answers 000 from where this build
  runs, so the class figures have to be pasted in rather than fetched.

- A name is not a key, and neither was a coordinate.

  The test that checks the published hazard file compared each stored curve
  against what the runtime reads back, keyed on the place's name. Japan offers
  two cities called Sendai, one in Miyagi and one in Kagoshima, and twenty five
  other repeated names, so half of each pair silently replaced the other and the
  test compared one city's curve against the other's. Keyed on the coordinate it
  found two more: Choshi and Hasaki share a point, and Furano is offered twice
  under two spellings, so the build asked J-SHIS for the same mesh twice and the
  file carried the answer twice. One place per coordinate now, in the build and
  in the file.

  That test also read the file twice, once through the runtime's cached view and
  once from the path, and compared the two. A build writing between them made it
  fail with nothing wrong, which is the worst kind of test. It reads once.

  Fifty more American places from the USGS, 140 to 190.

## 1.44.2, 29 September 2026

- Why three countries are not sold rain cover, measured rather than shrugged at.

  Indonesia, Japan and the Philippines fail both rainfall tests. Each model file
  now carries an `in_sample` figure, which is not a test and nothing is gated on
  it: how often the years the fit was made on beat that same fit, which should be
  a fifth of them. It is the one number that says which kind of failure a reader
  is looking at.

  | | in sample | fixed | rolling |
  | --- | --- | --- | --- |
  | Indonesia, rain | 18.8% | 43.2% | 36.5% |
  | Japan, rain | 21.1% | 36.2% | 32.0% |
  | Philippines, rain | 18.7% | 60.5% | 47.3% |
  | Italy, rain | 20.8% | 25.8% | 26.9% |

  All three sit at a fifth in sample, so the Gumbel describes the years it was
  fitted on and the distribution is not what fails. The years since are not the
  years before.

- Two explanations, both written down before being measured, both wrong.

  **Not the tail.** A Gumbel has a thin upper tail and monsoon rain is supposed to
  be heavy tailed, so fitting a GEV should have exposed the three. The shape
  parameter says otherwise and says it clearly: Italy at -0.448 and Greece at
  -0.373 are far heavier tailed than Japan at -0.022 or the Philippines at +0.015,
  and Italy and Greece pass. Fitting what the rain is would not have changed who
  is sold.

  **Not a straight trend.** Carrying a slope and extrapolating it one year ahead
  helps where there is a slope: Japan's rolling exceedance falls from 32.0% to
  23.8%, the Philippines' from 47.3% to 31.0%. It also breaks Italy, 26.9% to
  34.4%, and New Zealand, 29.4% to 32.8%, whose slopes are noise near zero.
  Gating the slope on the ordinary two sigma test does not rescue it: Italy and
  New Zealand still fail while only Japan opens, two lost for one gained. The
  rule for that was fixed before the measurement and it says abandon the trend,
  so the trend is abandoned and nothing was shipped from it.

  Both are recorded in the method note, because the next person to look at this
  will have both ideas within five minutes and they are both dead ends.

## 1.44.1, 29 September 2026

- A second test, because the first one was not asking about this model.

  Five countries failed the backtest in 1.44.0, and four of them failed by
  under-predicting, which says the climate moved rather than that the
  distribution is wrong. And the model this product publishes is not the failing
  fit: the levels are fitted on the most recent thirty years and used to price
  the year ahead. Nobody is sold a fit on 1981 to 2010. So the question that
  matches the product had not been asked.

  The rolling test asks it. For each place and each year from 2011 on, fit on the
  years before it, at most thirty and at least twenty five, take that fit's 1 in
  5 year level, and count whether that year beat it. Every year is out of sample.
  The judgement is the same negative binomial with the dispersion the fixed test
  already measured on the 1981 to 2010 years, because a spread fitted to the
  answer is not a test.

  It was written down before it was run, and the reason to trust it is that it
  does not open everything:

  | | fixed | rolling | |
  | --- | --- | --- | --- |
  | Chile, rain | fail | pass | opens |
  | United States, rain | fail | pass | opens |
  | Greece, wind | fail | pass | opens |
  | Indonesia, wind | fail | pass | opens |
  | Indonesia, rain | fail | **fail** | stays shut |
  | Japan, rain | fail | **fail** | stays shut |
  | Philippines, rain | fail | **fail** | stays shut |

  Those last three beat even a fit on the most recent thirty years by 1.8 to 2.4
  times. Extreme daily rain in the monsoon tropics is not described by a Gumbel
  on thirty years, or it is moving faster than thirty years can follow. Either
  way rain cover is not written there, and now that has been asked two ways.

  Storm cover: eleven countries of eleven. Car flood: eight of eleven.

  A country carried by the second test is not a country that passed. It is sold
  on a model that tracks a moving climate rather than on one that was always
  right, and that is a different claim, so the file makes it: `sold_on` names
  which test carried the country and `failed` still lists the one that did not.
  Too few years of record is not negotiable by either.

## 1.44.0, 29 September 2026

- Rain and wind were never Turkish. The build was.

  The car cover pays on the largest day of rain and the storm cover on the
  largest day of wind, and both were written only in Türkiye. Not because the
  method is Turkish: NASA POWER is a global reanalysis and the method was global
  all along. The build only ever fetched Türkiye's 81 provincial centres.

  It fits any country now, at the places the interface offers in it, every place
  above 200,000 people and at least 24 whatever their size. One file, one
  backtest and one verdict per country, and which countries are sold is read off
  those verdicts exactly as the earthquake models are gated.

  Storm cover: nine of eleven countries pass. Türkiye, Chile, Italy, Japan,
  Mexico, New Zealand, the Philippines, Taiwan and the United States.
  Car flood: six of eleven. Türkiye, Greece, Italy, Mexico, New Zealand and
  Taiwan.

  The two lists differ, and that is the point of asking each country separately.
  Chile's wind model passes and its rainfall model fails; Greece is the other way
  round. Neither list is the earthquake list either, and the place search was
  answering all three with the earthquake one, so a buyer typing Rome for a car
  cover was told it could not be priced while Italy's rainfall model passes.

- The failures, and which way they point.

  Chile observed 29 extreme rain days against 72 expected: a fit on 1981 to 2010
  over-predicting a country in drought since about 2010, which overcharges the
  buyer. Indonesia observed 531 against 246, Japan 734 against 405, the
  Philippines 653 against 216 and the United States failed the same way, which is
  the same fit under-predicting by two to three times and underfunds the pool.
  Either way the country is not sold, and the file says which test failed and by
  how much rather than the country simply being missing.

  A place from a country whose model failed is never a fallback for an address
  near its border. The search runs over the countries that passed and no others:
  a near miss from a model known to be wrong is not a near miss.

- What the page assumed about Türkiye, and stopped assuming.

  Dropping a pin outside a Türkiye shaped box was refused outright for the two
  daily covers, so a buyer standing at their own address in Rome could not place
  it. A typed coordinate was refused the same way. A search with nothing to go on
  biased towards the middle of Türkiye, which put a buyer in Rome at the far end
  of every result list. The three sentences naming Türkiye as the only country
  are lists now, read from what the protocol says it can price.

  Drought still asks for a named station, so a typed coordinate is still not a
  subject for it, and its stations are still Turkish because those are the
  seasons that have been measured.

## 1.43.1, 29 September 2026

- Three companies in a country, one price. Again, and this time where the
  buyers are.

  1.41.0 gave companies their own cost of capital and expense ratio so that a
  market of nine would stop being one price with nine names. It reached the
  eight companies written out by hand and not the three hundred generated one
  per country, so it was fixed everywhere except where most buyers are: a buyer
  in New York or Osaka saw three companies quoting the same premium to the penny
  and differing only in the fee on top.

  The three stand ins in each country now differ on the two numbers that move
  the premium itself. B is the patient one, cheapest capital and dearest to run,
  and it pays in five days; C is the opposite and pays the next day. On a New
  York flat that is 5,378.06 against 5,882.13, a nine per cent spread, and the
  cheapest total is no longer the cheapest risk, so the buyer has a trade to
  make rather than an order to read off.

  A saved book keeps its stand ins, and refreshing them only brought their
  licences up to the build's. Their terms come up too now, or a running
  deployment would have gone on charging the old single price.

- The map is applied to the largest, not to each.

  The map from our intensities to a published model's rises, so the largest of
  the mapped values is the map of the largest. Settling a trial applied it to
  every event and then took the maximum; it takes the maximum and applies it
  once.

  That change came out of chasing a regression that was not there, and the
  correction matters more than the change. Settling a ten thousand trial world
  looked seven times dearer with the map than without. Measured properly, that
  reading was a cold cache: the first call at an address builds a 181 point
  curve of our own rates, about 60 ms, and the run without the map had it built
  already. The map itself costs under a microsecond, and a first quote at an
  untouched address is 1.04 seconds end to end against 0.05 warm. The comment
  claiming the sevenfold is gone, because a false measurement in the source is
  worse than none.

- Thirty more American places from the USGS, 80 to 110.

## 1.43.0, 28 September 2026

- A number could not follow their curve, so it is a map now.

  1.42.0 carried the gap between a published national hazard model and ours as
  one number, a shift in intensity units. That works where the two curves have
  the same shape. Across the twenty points the USGS publishes per curve, ours
  had the wrong slope rather than only the wrong level, and a single shift left
  the New York quote a median factor of four out. The release said so and
  printed the factor, which is not the same as being right.

  The gap is a mapping now: the intensity our model would have called x becomes
  the intensity at which the published curve has the same annual rate. It is
  built from the two curves and nothing else, and inside the published points it
  is exact. Every residual is 1.00 or 1.01, against 1.6 at Osaka and 4.6 in New
  York before. The events stay ours, because the map is applied to each event
  rather than to the curve wholesale.

- J-SHIS publishes the frequent end too, and that is the end policies live at.

  Its four velocity levels start at a return period of 101 years and run to
  2,475, which is above the whole band a policy is written at, so everything
  below was our own shape extrapolated. It also publishes the probability in
  thirty years of reaching each JMA intensity, and at Osaka those reach 13
  years.

  Converting a JMA intensity used to be the step I could not settle, and got
  backwards once. It does not need settling: J-SHIS gives both a velocity and a
  JMA intensity at each of its own probability levels, so those pairs are that
  mesh's own relation between the two scales. Where the two families of its
  figures overlap they agree to within 20%, 83 years against 101 at Osaka, which
  is the check. Japan's curve now spans intensity VI to X at every place instead
  of VIII to X.

  The bound on how far the map may move one intensity went from 1.5 units to 2,
  measured rather than chosen: at 1.5 it binds on Japan and leaves the quote a
  third under what J-SHIS publishes, which is the dangerous direction, and
  nothing above 2 changes any answer.

  What the two together do to the figures that started this, at intensity VII:

  | Place | Before today | Now | Their own figure |
  | --- | --- | --- | --- |
  | Osaka | once in 210 years | once in 21 | once in 21 |
  | Tokyo | once in 23 | once in 8 | once in 8 |
  | Fukuoka | once in 550 | once in 113 | once in 113 |
  | Niigata | once in 224 | once in 73 | once in 73 |
  | Los Angeles | once in 143 | once in 148 | once in 148 |
  | New York | once in 5,024 | once in 5,787 | once in 5,788 |

- Niigata was not in Japan.

  A city of eight hundred thousand that this product offers, and our own outline
  did not contain it, so no Japanese rates applied and a fallback answered
  instead: intensity VII once in eleven thousand years, in a city an earthquake
  destroyed in 1964. The cause was in the containment test rather than the
  outline. It measured how far a point is from the outline's corners, and these
  outlines are simplified, so two corners can sit a long way apart along a
  straight stretch of coast and a city a kilometre outside the middle of that
  stretch is far from both. It measures the distance to the coast now, and
  Niigata prices at Japan's own figure, once in 73 years. Brownsville was
  outside the United States for the same reason.

  Nobody's neighbour came in with them: Seoul, Vladivostok, Shanghai and Taipei
  are still not Japan, Monterrey, Vancouver and Havana are still not the United
  States, and Lesbos, Nicosia and Aleppo are still not Türkiye. There is a test
  for each, and removing the clamp that keeps the measurement on the coastline
  puts Lesbos in Türkiye, which is how I know the test works.

- An address the two models cannot agree on is not priced at all.

  The map is exact between a publisher's points unless the bound holds it back,
  and where it does the gap is not a detail to print in small type. So where the
  published curve and our own events cannot be brought within a factor of two of
  each other across the band a policy is written at, the address is refused and
  the refusal says which two figures disagree and by how much. It costs about
  one place in fourteen in Japan and one in nine in the United States. A premium
  from the smaller of two figures a factor of seven apart is not cover, and
  disclosing the factor is not the same as being right.

- Half the hazard was skipping the correction. That was a bug in 1.42.0.

  Shaking at an address comes from two places: large events drawn once per
  country and shared by every policy in it, and small local ones drawn per
  address. Only the local half went through the correction. So the price and the
  capital model answered different questions wherever the correction did
  anything, and a Tokyo policy settled at a tenth where its own price assumed a
  fifth.

  It was invisible in 1.42.0 because the one place this invariant is measured is
  Tokyo, whose shift was exactly zero. The map made it non-zero and the test
  failed immediately, which is what that test is for. Osaka is measured now too.

- The United States is written, on the USGS's figure rather than on ours.

  Cover used to be written only where our own catalogue model passed its
  backtest. Our American model fails it badly: around 296 American cities it
  expected 27.5 earthquakes of magnitude 5.5 and 10 happened, so its level
  cannot price a policy. But the level is not what it is needed for any more.
  Where the USGS publishes the hazard at an address, the level is theirs and our
  model supplies only the events, which is a better basis than our own failed
  backtest rather than a worse one.

  So a country is written on either ground, and a buyer in New York can buy.
  Being open does not open every address: outside 60 km of a published curve the
  refusal now says which of the two is missing, instead of handing back a list
  of countries with the buyer's own country in it. The page no longer claims a
  tested model exists everywhere cover is written, because for one country it
  does not.

## 1.42.0, 28 September 2026

- Where a country publishes its own earthquake hazard, that is the figure.

  A buyer in Osaka was told the ground under their address reaches intensity
  VIII about once in 1,035 years. Japan's own national model, NIED's J-SHIS,
  says once in 101. Everything behind our figure was ours: a catalogue since
  1973, which has not seen the Nankai megathrust, and a global shaking equation
  with no site term, which cannot know the basin Osaka stands in.

  `clause.hazard.published` now fetches the curves Japan and the United States
  publish, offline, the same way the catalogue build fetches the catalogue, and
  converts ground velocity to intensity with the relation ShakeMap itself uses
  in the other direction. The gap between their curve and ours at an address is
  carried as one number, a site term in intensity units, so the events keep
  their magnitudes and distances and the neighbours they shake at the same
  moment, and only the ground under the address changes. At Osaka that number
  is 1.22 and the answer becomes once in 160 years, with the three stronger
  levels J-SHIS publishes matched inside 30%.

  What one number cannot follow is published with it rather than averaged away.
  The quote now names whose model priced it and by what factor ours follows
  theirs: 1.6 at Osaka, 1.9 at Tokyo, 4.6 in New York. That last one is not a
  detail. Across the United States the median is 4.2, because USGS publishes
  twenty points per curve where Japan publishes four and our curve has the wrong
  shape against them rather than only the wrong level. A single shift cannot
  follow a slope. It still moves the price the right way and it is still better
  than no term, and the honest thing is that the buyer reads the factor.

  Coverage: 1,295 Japanese places and 80 American ones. The American number is
  low because the USGS service refused most of the build's requests on the day
  it ran. The build keeps what it got, names what it missed, and writes the
  file in one step so a reader never catches it half written, so further passes
  fill the gap instead of starting again. An address no curve reaches is priced
  as it was, and names no publisher.

  This also corrects an earlier answer that pointed the wrong way. Our
  intensities were compared against J-SHIS's Japanese intensities by eye, the
  conclusion was that this model overstated the hazard, and it had to be
  withdrawn: the whole comparison turned on a scale conversion that neither
  side could settle. Taking the publisher's own curve removes the argument
  rather than winning it.

- The drought stations had never been measured.

  Drought cover is priced on two numbers per station, the normal seasonal
  rainfall and how much it varies. They were typed into the source, under a
  comment that said a live deployment would read them from the meteorological
  service. The cover was on sale.

  `clause.hazard.season_build` measures them from the same NASA POWER daily
  record the car and storm covers already settle on, by totalling each station's
  own window year by year since 1981. A season the build has not measured is no
  longer offered.

  The normals were about right on average and wrong one by one: the median moved
  1%, the largest 67%. The variability was the expensive one, a median of 0.39
  typed against 0.303 measured, and a higher variability is a fatter dry tail
  and a higher premium. Across the 58 stations the typed figures implied a
  season below 60% of normal a median of 1.8 times as often as the record does,
  4.5 times at one station and 0.54 at another.

  The test fixed before the first run failed, and it is written down as a
  failure: 80 of 870 test seasons fell below the fitted one in five year low
  where 174 were expected. The distribution is not what failed, since the same
  gamma describes the seasons it was fitted on. The rain changed. A season since
  2011 has averaged about a tenth above its station's long run mean against
  about a tenth below in the 1980s, so the published normals are fitted on the
  most recent 30 seasons and a price from the old window would have been about
  twice what the measured seasons support.

- What is measured and what is not, said one by one.

  The method note and the site both carried a single sentence putting station
  normals, route statistics and zone seismicity in the same illustrative box.
  Three of those four are measured now. The list says which, names the build
  that measured each, and leaves flight route statistics where they belong.

## 1.41.0, 28 September 2026

- One company, named once, all the way through.

  Making companies price for themselves turned up three places that had each
  been choosing one on their own: the contract named the company with the
  smallest fronting fee, the application held a price computed for another,
  and the policy was written for a third. While every company charged the same
  premium that was invisible. It is not invisible now, and the first thing it
  did was tell a buyer their contract had changed when nothing about it had.

  The default is the cheapest by what the buyer pays, which is no longer the
  same as the smallest fee: on one Istanbul flat the lowest fee sat on a price
  of 6,132.39 and the lowest total was 3,793.19, so the buyer who named no
  company was being put on the dearest paper by a rule written when there was
  only one price.

- The Continue banner that says nothing always says something now.

  Reading a reply's body can fail on its own, after the headers have arrived,
  and a connection cut part way through left a rejection with no status and no
  payload. That fell through every branch of the buy banner to the one
  sentence that names no reason, with no technical line under it, which is
  exactly the screenshot a buyer sends when they cannot buy. It is named now,
  it is marked as a silence rather than a refusal so the page asks the same
  question again, and any error that reaches that banner without a kind of its
  own carries its name instead of nothing.

- Why this much at this level, said where the ladder is read.

  The payout steps carried amounts and no reason. The page knew the reason all
  along: how often the level in each row happens at this place, from the same
  exceedance curve the price is made of. It was in a table folded inside "show
  how this price was worked out", closed, which is the one place a buyer
  deciding will not look. Each step says it now.


- Nine companies quoted one price to the penny, and it was the pool's.

  The offers endpoint said so in its own words: the pool's premium is the same
  whoever issues it, the risk is the risk. What differed between nine
  companies was the fee each added on top, two per cent to six. Measured live
  on a Kadıköy flat, all nine read 2,633.21 and the totals spanned seven per
  cent, so a market of nine looked like one price with nine names.

  A price has three parts and only one of them is the risk. The expected loss
  is the model's answer and every company reads the same one; no insurer
  disputes an exceedance curve, they dispute what to charge for it. What the
  capital a policy ties up must earn, and what it costs to run the business
  holding it, were a single figure inside the pricing engine. They belong to
  whoever is writing, and they are the company's now: a large, well
  capitalised one needs less return on the capital and costs more to run; a
  small lean one is the other way round.

  Five Turkish companies on the same earthquake now read 4,134.58 to 6,255.05,
  a spread of fifty one per cent, and the largest single policy each will
  write runs from 150,000 to 500,000. A keener price on a smaller line is a
  different offer rather than a better one, so the offer carries both.

  One simulation, many prices: the expected loss and the capital a policy ties
  up are facts about the risk and are measured once. The arithmetic that turns
  them into a price is in one function, so an offer, a price lock and the
  policy finally bound cannot answer differently. What the buyer is shown is
  what the buyer is charged, and there is a test that buys to prove it.

- The price lock holds the risk, not the money. It always did; it was only
  invisible while every company charged the same. A quote measures what a
  cover is expected to cost and how much capital it ties up, and promises that
  those will not move for ten minutes. What is paid is that measurement priced
  by whoever issues the policy.

- The United States is modelled, and does not pass.

  The models were always built from the USGS global catalogue -- Gardner and
  Knopoff declustering, an Aki and Utsu b value, rates since 1973 because that
  is when the global record became complete at magnitude five. Nothing in the
  method is particular to a country. The United States had no model because no
  one had added it to the list of regions, not because the data was missing.

  It is on the list now, the lower forty eight, and it was built. Three of the
  four tests pass: 279 mainshocks in the fitted years against the thirty
  required, 106 observed against 115 forecast, and a positive information gain
  on where they landed. The fourth is the one that tests the figure a premium
  is made of, and it fails: around 296 American cities, in circles of fifty
  kilometres, the model expected 27.5 events of magnitude 5.5 or more in the
  test years and 10 happened. Publishing it would have overcharged a buyer in
  an American city by about two and a half times.

  So the card says that, with the numbers, exactly as Greece, Italy, Indonesia
  and the Philippines do. Alaska and Hawaii are not in the box and the file
  says why: one box cannot hold the Aleutians, which cross the antimeridian,
  and stretching it over the Pacific would sweep the whole rim's seismicity
  into the rate for California. The country's national network is USGS itself,
  so it has three independent publishers rather than four, and the source list
  no longer counts the same body twice.

## 1.40.0, 28 September 2026

- The one thing a flight buyer still had to confirm was that their flight is
  inside their flight.

  "It is inside the area measured" is a real question for a home, a car or a
  field, and the page already answers it by construction for three of the
  five perils: the place the buyer chose is where the home stands. For a
  flight the area measured is the flight -- the page says so in those words,
  "the flight itself" -- so the tick box asked nothing. Measured at 390px it
  was the only thing left blocking Continue on that step, with every other
  field already answered.

  Drought still asks, and should. The field can be kilometres from the
  station that settles it, the sentence on screen names that distance, and
  basis risk lives in it.

- Drought was also the one peril that offered no name for the thing at risk.
  A flat in Kadıköy, a house, my car, one flight and what missing it costs:
  four perils filled that box and the fifth left it empty and required. It is
  named after the crop already chosen and the place already chosen, like the
  rest, and the words stay the buyer's to change.

  The crop words are written for a dropdown, Wheat and Sugar beet, and a
  capital in the middle of a sentence is wrong in English, Turkish, Spanish,
  French and Russian, right in German where every noun carries one, and
  absent in Japanese. So the languages that lowercase are named rather than
  assumed, and the lowercasing is done in the language, because of the
  Turkish i.

- Not done, and worth writing down because the research said to do it: the
  address block cannot move off that step. It is not the issuing company's
  paperwork, it is the property's identity. property_of() keys on it and
  may_write() uses that key to stop one flat carrying more cover than it is
  worth; the key needs street and city at the least, and the flat number is
  what takes it from a building down to a home. Moving it would take away the
  thing that separates insurance from a wager. What could be deferred, the
  documents and the sign-in, already is.

## 1.39.0, 28 September 2026

- The Continue button told a buyer to wait for something that had already
  arrived.

  Storm and vehicle cover are written only within 60 km of a Turkish
  provincial centre, where the wind and rainfall models are tested. Outside
  that the protocol answers 400 with a sentence saying exactly so, and the
  page prints it under the map. The button went on saying "Still reading the
  place" -- at four seconds, at twelve, at thirty, and for as long as anybody
  cared to watch, because one sentence covered the wait and the refusal alike
  and only the wait ends by itself. A refusal is a state of its own now and
  the button names the way out of it.

- That refusal was also reaching every non-English reader in English, and it
  was not alone.

  The guard that holds a refusal to having a translation reads Refused(...)
  calls, and said in its own words that internal ValueError text does not
  reach a browser because it is logged and replaced by a fallback. That is
  true almost everywhere and false exactly where it matters: a peril reading
  what the buyer typed raises ValueError and the API forwards it word for
  word, and the valuation's ValuationError becomes a 422 carrying its own
  sentence. Sixteen sentences sat in that gap, thirteen of them with no entry
  in any language: the two 60 km ones, every complaint a flight subject can
  raise, and four about what a home or a field can be valued as.

  They are translated, and the guard reads them now, so the next one fails a
  test instead of shipping.

- The three that already had a translation took a second one when these were
  added, so the same key sat in the dictionary twice. json.loads keeps
  whichever came last and says nothing about the other, which is a coin toss
  dressed up as a dictionary. The duplicates are gone, the wording the site
  was reviewed against stayed, and a test now refuses a dictionary that holds
  one sentence twice.

  Found by reading a refusal in a browser and not recognising the wording.

## 1.38.0, 28 September 2026

- Three answers were cheaper to withhold than to give.

  Found by asking the protocol the same question twice, once with the answer
  and once without it. A home described with no year built was valued at the
  full rebuild cost of a new building: 110 m² in Istanbul came to 57,041 with
  no year against 31,372 said as 1968, eighty two per cent more cover for
  saying less, because the ceiling factor that scales rebuild cost down for an
  old building was never applied. A vehicle with no model year lost its age
  cap altogether: a 2005 car declared at 240,000 is held to 50,000 when the
  year is said and carried the whole 240,000 when it was not, which is the one
  thing that cap is written to prevent. Both are refused now. Every home has a
  year and every car has a model year, and the page has always asked for both,
  so nobody who could answer was being helped by the silence.

- And the same shape in the price. An earthquake subject with no year was
  priced as a building of the current code, the cheapest of the four bands:
  706.29 against 770.98 for the same cover on a pre 1976 building. So the
  first figure a buyer saw was one no honest answer could improve on, and
  every honest answer made it dearer.

  A subject with no year cannot be refused the way a valuation can, because
  that is the price bar before the buyer has described anything. It is priced
  as the oldest building instead: the first figure is the dearest the building
  could be, and answering only brings it down. The page's own model, which
  fills the bar while a quote is in flight, takes the same floor from the same
  schedule, so the two cannot drift.

- The size says what a building can carry and the subject says what it is
  priced on, and nothing held the two together. A buyer could describe a 1968
  building, take the lower ceiling that comes with it, and leave the year out
  of the subject to be priced as though it met the current code: the low price
  and the high cover at once. A field's area has been cross checked against
  the cover it is written on for as long as drought has existed; the year now
  gets the same check.

## 1.37.0, 28 September 2026

- Two airports chosen one at a time do not name an airline, and the flight
  cover filled the flight number box as though they did.

  A route key names its airline first and the two ends after it, TK-IST-LHR.
  Choosing the ends separately makes the subject SAW-ESB, and the page took
  the first part either way: the box came out SAW1979, which no flight number
  can be. The Continue button then asked for a flight number over a field
  that already looked answered, and said nothing about what was wrong with
  it. A buyer picking their own two airports could not get past the second
  step. The number is only offered now where the subject really names an
  airline, and where it does not the box is left empty with the shape of the
  thing to type in its placeholder.

- The protocol was asked three times for a price it always refuses.

  A flight without its number came back "that cover cannot be priced" every
  time -- the right answer to the wrong question, because the page already
  knew the subject was incomplete. The same four checks are what its Continue
  button reads to say what is missing. It consults them before it asks now,
  and the page's own figure stays on the screen until there is a whole
  subject to send.

  Both were found by driving the purchase in a browser rather than reading
  it: all five perils, answered step by step through their own controls, with
  the Continue button as the instrument, since a blocked one names what it is
  waiting for.

- The same walk reported the map tiles overflowing the phone at 390px. That
  was the instrument and not the page: it asked each element whether its
  right edge passed the viewport's, and a tile's does, because a tiled map
  draws past its own frame on purpose. Measured properly the page does not
  scroll sideways -- scrollWidth is 390 and scrollX stays 0 -- because the
  map's frame clips them. Nothing to fix, so what holds it is named instead:
  take overflow:hidden off that frame and the phone scrolls into empty map.

## 1.36.0, 28 September 2026

- The Proof page printed the protocol's own settlement rule in English to
  every reader, and had for as long as that band existed. Three of four
  validators, the median, five per cent: the sentence that decides whether a
  policy pays. It has a translation in all six languages and the page never
  asked for it -- esc() where the line above it used t() -- so a Turkish
  reader got the heading in Turkish and the rule under it in English, on the
  one page whose whole job is to be worth trusting.

  The guard written a release ago could not see this. That one holds that a
  sentence *has* a translation; this is about whether the page bothers to use
  it. The new one follows the value: it finds what the page stores a prose
  field of the protocol's into, follows it through the hands it passes, and
  requires every esc() of it to translate first.

- Half the site was reading past a comfortable line length, and the cause was
  a unit.

  CSS ch is the width of the digit zero. In this face that is 1.364 times the
  average character of a sentence, measured in a browser rather than assumed,
  so every max-width written in ch was holding a line about a third longer
  than its number said: 62ch meant eighty five characters and not sixty two.
  Measured properly -- a paragraph's own length divided by the lines it
  actually took -- the privacy page ran at 105 characters to a line, the
  questions page at 102, Rialo at 95, and for insurers had one at 145.

  There is one token for it now, and it is applied to the prose that had a
  loose measure and to the prose that had none at all: a plain paragraph in a
  section, the line beside a pull quote, the small print under a form field.
  Every tab now sits inside the band at both its median and its worst line:

  | tab | before | after |
  |---|---|---|
  | privacy | 105 / 136 | 73 / 82 |
  | questions | 102 / 129 | 73 / 87 |
  | Rialo | 95 / 121 | 73 / 90 |
  | for insurers | 91 / 145 | 83 / 88 |
  | proof | 85 / 131 | 75 / 81 |
  | the pool | 90 / 106 | 71 / 82 |

- Two of my own instruments were wrong, and both had to be fixed before the
  page could be. The first counted a character as the average lowercase
  letter, which is not what a line of prose is made of; the second guessed
  that a paragraph's last line is half full, which is a swing of thirty
  characters on a two line paragraph and invented a 106 character line on the
  pool page that was really 79. It takes paragraphs of three lines or more
  now, where the guess is small enough not to decide the answer.

- The verdict banner on the Proof page was exempted from the reading measure
  in 1.32.3 on the grounds that a single line has no next line for an eye to
  find. True, and it was two sentences and twenty three words across 154
  characters, which is not a banner. The first half of that rule was applied
  without measuring the second.

## 1.35.0, 28 September 2026

- Ask a source. The protocol settles policies by pointing a condition at a
  primary source and reading what it says, and until now the only way to watch
  that happen was to buy cover and wait for the weather. Now anybody can write
  down a question, and the same reading happens with nothing on it: an
  earthquake inside a radius, today's wind or rain at a place, an airport's
  late departures. Back comes the figure, the record it was read from, the
  line it was compared against and the three clocks -- when the world did the
  thing, when the source first said so, when we asked. Confusing those three
  is how a question gets answered against the wrong one.

  It reads the same cached feeds the live bands read, so asking costs the
  sources nothing beyond what the site already fetches.

- **It is not a prediction market and will not become one.** That was the
  obvious thing to build here and it is the one thing this must not be: what
  separates insurance from a wager is that the buyer has something actually at
  risk, and this protocol's own contract refuses cover to anyone who does not.
  A question with money on it has nothing behind it at all. The useful half of
  a prediction market is here -- the answer is settled by reading a primary
  source rather than by counting opinions, which is the same thing that makes
  a parametric policy work -- and the stake is not. Two tests hold it there,
  one over the protocol module and one over the page's script, and both had to
  learn that a name is written in camelCase before they caught a "stakeTotal".

- The question says how far back it looked. Asked at the epicentre of a real
  M5.3 and told no, because the feed being read covered one day and the event
  was four days old, and nothing in the answer said so. It reads the week now,
  which holds the day, and the window is part of the question: "no earthquake
  near you" is not a fact about the place, it is a fact about the last few
  days of it, and the source only ever knew the latter.

- Two smaller things the sources taught, rather than the design:

  The form offers only what can be answered, and the places come from the
  source rather than from a list, so a place the weather feed stops publishing
  disappears from the form instead of sitting there refusing. It listed a
  "flight" shape for one afternoon after the flight question became a question
  about an airport's departures; that feed reports airports with late
  departures and carries a few flight numbers under each, so it cannot say
  whether one named flight left on time, and a chip that refuses every
  question is worse than one never drawn.

  A figure the source did not publish is refused rather than answered as zero.
  A place with no gust figure is not a place where the wind did not blow, and
  saying no there would be wrong in exactly the direction that costs somebody
  a payout.

- Both of this page's state-carrying classes were built by pasting strings
  together, and the guard written in 1.33.0 found nothing wearing either of
  them, which is the point: a class attribute assembled at runtime cannot be
  read back by anything. The verdict rides an attribute now and the field
  classes are written out whole.

## 1.34.0, 27 September 2026

- The rulebook is readable in six languages. It was not, and the page around
  it was, which is the worst version of this fault because it looks finished:
  a Turkish reader got the labels, the headings and the layout in Turkish, and
  the rules themselves -- which source is read, which stands in when it is
  silent, when the figure is frozen, why the wait exists -- in English.

  Fifty of the fifty-four sentences had no entry in any dictionary. All fifty
  are translated now, in Turkish, German, French, Spanish, Russian and
  Japanese, with the terms the rest of the site already uses.

- And the English is one click away, because it is the binding text and this
  is the wording that decides money. Once per peril, not once per sentence:
  written the second way first, it put eleven toggles in one panel and added
  1,500px to the page. A reader who wants the binding wording wants all of it.

  Both readings come out of one function that is handed a way to say a
  sentence, translated or as the protocol wrote it. Two functions would drift,
  and the one that drifted would be the one nobody reads until it matters.
  An English reader is offered no toggle, since it would open onto a copy of
  what is already on the screen.

- Two guards, because this text decides money.

  The first reads the protocol rather than a list, so a peril added or a rule
  reworded fails instead of shipping untranslated. The first thing it found
  was a sentence this work had missed: the earthquake rule for a policy
  written on shaking rather than magnitude. The rulebook the API answers with
  names one of those two, so measuring from one live answer could not see the
  other. Reading the source could.

  The second holds the figures and the sources through translation. A
  translation that writes 48 where the protocol wrote 24, or drops GFZ GEOFON
  from the list of who is read, has not mistranslated a sentence but rewritten
  a term, and nobody reading only the translation could tell. Units are the
  one thing allowed to change: km/h is written km/sa in Turkish and км/ч in
  Russian, which is the unit arriving in the reader's own alphabet rather than
  a figure going missing.

## 1.33.0, 27 September 2026

- The calculation rules page, which was the rulebook printed five times.

  Five of its eleven rows carry the same text for every peril: how a reading
  is attested, how long you have to object, what happens if a publisher stops
  publishing, what is archived, and which version of the rulebook this is.
  Measured rather than guessed at, from the protocol's own answer: five of
  fifteen fields identical across all five perils. They are said once now, in
  a panel above, and what actually differs between perils is what is left in
  the panels below. Which rows those are is decided by reading the answer and
  not by a list written into the page, so the day a peril is given an archive
  rule of its own, that row moves down to it and nobody has to remember this.

  The page is shorter for it even with the six stations, three new panels and
  an index of the perils added.

- What the page's title asks, set out. Six stations from what a source
  publishes to what is settled and archived, and under them the three places
  the sequence stops rather than guesses: nothing published, a test failed,
  the readings disagreeing. That last is the difference between this and an
  oracle that must always answer, and it was in the eleventh row of the fifth
  panel where nobody would read it.

  Both are type rather than a picture, and for the same reason. Drawn, the six
  sat in a 760 unit figure that a 390px phone scales to 342px, which put the
  legend at four and a half pixels. And the stops, cut into hand placed rows,
  made "That reading is not used. The" a translatable string of its own: a
  line placed inside a drawing is broken where English happens to end, and no
  other language can re-break it. As boxes and paragraphs they reflow to one
  column on a phone and keep their size.

- The rulebook rows were set in as many 150px columns as the shared grid could
  fit, which is right for a name beside an amount and wrong for a paragraph:
  thirty six columns twenty two characters wide, four words to a line. The
  page has a modifier of its own rather than bending a class thirteen other
  places wear, and a label now sits beside its paragraph the way a
  specification is read.

- Two holes in the translation tests, found by falling into one of them.

  Both of the tests that require a sentence to be translated excuse a line set
  entirely in capitals, which is right for a unit and wrong for the labels on
  this site's drawings. Every existing label was in fact translated, so the
  exemption was never a decision; a new figure could have shipped its whole
  legend in English through it. And nothing at all was checking the
  descriptions a drawing gives a screen reader: four of them had been reaching
  every non-English reader in English, since the releases that drew them.
  Both are held now, and the four are translated.

- The skip link took you off the page you were on, and had since it was added.

  A hash router and an anchor inside the page want the same character. Routes
  here are written "#/rules" and an anchor is written "#main"; the router read
  what followed the hash, found no screen of that name, and fell through to
  the home page. So "Skip to content", which exists so that somebody on a
  keyboard can reach the content of the page they are on, moved them to a
  different page instead. Found while building the rulebook's index of perils,
  which was about to do the same thing.

  In-page anchors are scrolled to and focused now without the hash changing.
  Anything beginning with a slash is still the router's.

- The guard written in 1.32.3 against a class reaching another screen was
  Rialo's alone. It reads the markers now, so it covers every page that grows
  styles of its own, and it caught this release borrowing the Rialo page's
  figure frame onto the rules page before that page was finished.

  It also had to learn the difference between a class and a compound. A bare
  `.said` reaches every .said there is, which is what went wrong; `.kvs.rulebook`
  reaches only what wears both, and leaves the thirteen plain .kvs alone. Written the first way it would have refused this release's own fix.

  And written the first way it missed the first rule of every marked region.
  The marker sits inside a comment, so the region begins mid-comment with a
  closing `*/` that has no opener, and the prose ran on into the rule after
  it. Found by breaking each rule in turn and noticing one break the test did
  not report.

## 1.32.3, 27 September 2026

- The home page was broken by the release before this one, and broken badly:
  the policy's own sentence, the one the whole page is about, came out one
  character to a line in a tall thin column on any screen wider than 1000px.

  The Rialo page introduced a two column row and called it "said". So do the
  hero's five beats, and have since long before that page existed. A class
  selector reaches every element wearing that class, so the rule reached all
  seven: a 390px box became a grid whose second column was 26rem, the first
  collapsed to nothing, and the text stacked. It is named for what it is now,
  and a test holds that nothing declared in this page's own style regions is
  worn on another screen. That test was written twice: the first version
  passed with the collision put back, because it decided which classes were
  "this page's" from a list of name prefixes, which is the answer written
  into the question.

  Three names moved rather than being renamed: t-2, t-3 and t-settled name a
  colour of text inside a drawing, and the hero's landscape instrument was
  already wearing one of them. They belong with a-edge and a-signal as shared
  vocabulary, not inside one page's region.

- The REX drawing was wrong, and wrong about the thing it exists to explain.
  It showed four validators labelled with four agency names and applied the
  agencies' tolerance to them. Those are two different disagreements. Each
  validator reads every agency and keeps their middle answer; then the four
  validators' answers are reconciled on chain, three of four, median, five per
  cent. So the picture is two stages now, which is what world.py does, and the
  earlier correction in 1.32.2 was itself half wrong: 5% was never the wrong
  figure for REX, the agency names on those dots were.

- Small print given the measure the rest of the page has. A 13.5px paragraph
  filling a 1120px band is a 166 character line, and the Proof page had four,
  For insurers eight and the pool one. All now sit at the same measure as the
  prose above them. Checked afterwards: the one thing still that wide is a
  single line verdict banner, which has no next line for an eye to find, so it
  was left alone.

## 1.32.2, 27 September 2026

- Three drawings on the Rialo page, because the page's subject is a mechanism
  and a mechanism is shown rather than described. A condition riding above a
  run of blocks, faint while it is false and lit once the reading lands, with
  the settlement drawn inside that same block and not after it. Four agencies
  reporting on one earthquake, plotted where they actually fall. A call passing
  four filters with the credential held behind the last of them.

  The middle one was drawn wrong twice before it was drawn right. First the
  four readings sat at even spacing, which is the one thing a picture about
  distance must not do: two of those agencies published the same magnitude and
  belong on the same mark. Then it was labelled "5% tolerance", which is REX's
  generic default and not what an earthquake uses. The figure in the code is
  0.2 of a magnitude, absolute, because a tenth is routine between agencies and
  a third is not. It now plots the real readings from Elbistan on 6 February
  2023, on a scale, inside the band the contract actually names.

- Two sentences lifted out of their paragraphs and set beside them, because
  each is the sentence its section exists to make. Set beside, not underneath:
  a quote given a row of its own leaves the other half of that row empty, which
  is the same fault as a page that does not use its width.

- Attribution for the sets this site shows and did not credit. The protocol has
  been sending the airportsdata line with every airport search and the page was
  dropping it, which is a licence not being met rather than a styling lapse; it
  now sits under the results, where GeoNames already sits under the place
  results. And the model behind the assistant is named, because one that will
  not say whose judgement it runs on is asking for more trust than it has
  earned.

- The earthquake terms name every agency that is actually asked. The chain
  queried on each event is USGS, EMSC, GFZ GEOFON and the national network, and
  two of those were in the code and not in the text that is section 10 of the
  contract. A source whose reading can settle money, or refuse to, belongs in
  the terms.

## 1.32.1, 27 September 2026

- The Rialo page named one thing this protocol uses and left out the two that
  are most worth reading, which is what happens when a page is written from
  research into somebody else's site rather than an audit of one's own.

  REX is the first. Rialo reads an ordinary web API from inside the chain, and
  every validator performs the call itself, so what lands on chain is a set of
  independent measurements rather than one agreed figure. Reconciling them is
  left to a separate aggregator whose default rule is not published: no quorum,
  no median rule, no dispute path. That is ordinary for a young chain and fatal
  for an insurer, so this protocol writes its own rule into the contract, three
  of four, median, five per cent dispersion, and the page now says so.

  Latch is the second. Rider holds no model key at all: Rialo's own agent
  authorisation layer holds it, and what this server has is a scoped token that
  passes a spend limit, an endpoint allowlist, a method filter and a rate limit
  before the real credential is touched. Buying needs a permission signed on the
  buyer's own device and goes through a second latch. That is a load bearing
  piece of this protocol's safety and it was not mentioned anywhere a reader
  could see.

- And the em dash is gone from every sentence a reader sees, in the markup and
  in five of the six dictionaries. Each was a sentence that wanted a comma, a
  colon or a full stop, so each was rewritten rather than swapped for a hyphen.
  Russian keeps its own, deliberately: there the dash stands in for the copula
  the language leaves out, and stripping it would leave a hundred and twenty two
  sentences ungrammatical.

## 1.32.0, 27 September 2026

- A page about the chain this protocol runs on. The front page said "Built on
  Rialo" and nothing else, which tells a reader a logo rather than a fact, and
  the fact is more interesting than the badge: what this protocol is made of is
  the chain's headline feature, and a parametric policy is the shape that
  feature was made for. A predicate lives on the chain and is evaluated during
  block execution; when it becomes true the network enqueues the transaction
  itself. That is a policy, exactly.

  The page names the three calls the client actually makes -- get_subscription,
  get_triggered_transactions, get_workflow_lineage -- and a test holds those
  names against the client, so renaming one there cannot leave the page saying
  something that stopped being true. It gives Rialo's published figures as
  Rialo's claim rather than as our measurement, and it says what this protocol
  does not use: native privacy, threshold cryptography, consistency levels.

- And what Rialo has published, read rather than remembered. There is no feed
  to subscribe to -- the documentation is behind a sign in, the blog answers a
  fetcher with nothing, /blog/rss.xml answers with HTML and there is no
  sitemap -- so the protocol reads Rialo's own front page every few hours and
  the page shows what it found, with the time it last looked. Seventeen pieces
  today. A list frozen into the markup would be wrong by next month, and a test
  holds that none of it is.

## 1.31.5, 27 September 2026

- A reader insured a flat, went back to the first question, chose a flight
  instead, and was carried all the way past the price and the contract before
  the protocol refused the purchase: "http 422", against a declared value at
  risk of 150,000 on a trip, where a trip is capped at 20,000.

  Three things put that figure there, and all three are fixed. The declaration
  opened at a made up 150,000 that nobody had entered; a change of peril
  cleared every field of the declaration except the figure, so a flat's value
  rode along onto a flight; and the slider that offers the figure was bounded
  by four times the largest cover rather than by the bounds the protocol
  publishes for exactly this purpose -- its own endpoint says "so the page can
  show a buyer the ceiling as they type and the protocol can hold them to it".
  Walked in a browser along the reader's own path: 118,737 declared against a
  flight before, 1,000 after.

- And the sentence they were shown, which was not English: "what the trip cost
  must be between 50 and 20000". Those names are read back inside two
  sentences, so they are noun phrases now rather than questions.

## 1.31.4, 27 September 2026

- A flight policy showed somebody else's cover on the page they sign on. The
  confirm step drew an earthquake sentence, an earthquake payout table, an
  earthquake chart and an earthquake contract underneath a summary of the
  reader's flight, with three prices on screen that did not agree, and the
  purchase could not be completed: the button asked for a contract to be
  accepted that had just been accepted.

  One line caused all of it. The flight sentence read the route out of ROUTES
  by flow.subject. The subject of a flight is "IST-GZT"; that table is keyed
  "TK-IST-LHR" and holds six routes in all, so the lookup was undefined and
  the line threw on every flight policy. The step is drawn top to bottom, so
  everything after the throw kept what it had: the policy before this one. The
  button stayed stuck because the contract on screen was not the contract the
  gate was hashing. The sentence names the two ends of the flight the reader
  chose, the way the summary beside it already did.

- And the class of it, rather than only the instance: a redraw of that step
  that does not finish now blanks what it could not redraw, says so where the
  reader is looking, and stops the purchase. Nothing below a failed redraw
  belongs to this policy, so nothing below it is shown and nothing can be
  agreed to. The fault still reaches the console; a page that swallows its own
  errors is how this one stayed hidden.

## 1.31.3, 27 September 2026

- The confirm step was laid out in 952px of a 1328px page, with the rest blank
  down the right of the longest page in the product. The running rail is the
  page's second column on every question, and the confirm step is the one step
  that hides it, because it is itself the summary -- but a grid track is held
  open by the stylesheet, not by what is in it, so its 340px and the 36px gap
  stayed behind as 376px of nothing.

  The track goes when its occupant does. The step now takes 1200px, the measure
  the stylesheet always meant it to have, centred rather than pinned left. On a
  1920 screen that is 1200 of 1328 rather than 952, and the summary column
  stops wrapping a street address onto five lines.

## 1.31.2, 27 September 2026

- Still too big, and the last measurement was of the wrong thing. Narrowing the
  column from 380 to 320 took 38px off the height and made the shape worse --
  1:1.74 to 1:1.95 -- because the rule text under the drawing wraps to more
  lines in a narrower card. The card was not too wide. The drawing was too tall
  for what was in it.

  It declared 340 units and drew in 296 of them, with 56 units of nothing
  between the validators and the line the rule was written on and 33 above
  them. Those are closed: the validators come down to meet the instrument, the
  box is 278 units, and the ink uses 93% of it. Nothing was shrunk -- the
  labels are the same size they were drawn at, because the caption is already
  at the floor of what can be read.

  The drawing is also capped at its own 320px now instead of being painted
  across whatever the column gives it. Between the two the panel is 558px
  rather than 661, and in a 900px window that is 200px of air below it rather
  than 100.

- The upright trace was drawing itself against a dash 1100 units long on a path
  that is 916, because only the landscape one was ever measured. Both are now.

## 1.31.1, 27 September 2026

- The instrument was too big, and it was too big for the reason it has been too
  big every time: a drawing given a frame larger than itself. Upright beside the
  steps it had whatever the column gave it, which was 499px for a drawing that
  is 320 wide -- 1.43 times itself, with every gap inside it stretched to match.
  The card came out 499 by 787.

  It gets a column it fits in now: 380px at most, which renders the drawing at
  1.06 times its own size, and the width it does not need goes to the steps,
  which are words and can use it -- 892px instead of 773 on a 2560 screen. The
  five steps still advance with the scroll, a little sooner for having more room
  to say themselves in: two at 360px, three at 600, four at 840, five at 1080.

## 1.31.0, 27 September 2026

- The instrument is upright again, pinned beside the steps, and the reader
  moves it. A row played the policy through once on arrival and then held the
  whole picture, which is a picture of the end; standing up beside five steps
  that scroll past it, it answers whichever one is being read. The steps take
  the left of the page and the reading the right, so the width carries two
  things at once instead of one thing twice.

  Three drawings of one instrument is still two: the long one for the band of
  widths where the instrument has a row to be long in, the upright one where it
  has a column -- on a phone, and now above 1300px as well. Checked at eight
  widths from 320 to 2560: exactly one drawing is shown at each, and the right
  one, with nothing scrolling sideways.

- What moves it is how far through the steps the reader is, not which step
  crosses the middle of the window. The middle rule is right when a step is
  most of a screen; here the five of them are 875px on a 1400px screen, so the
  middle line is past the last step before the second has been read -- measured
  at 2560 by 1400, the instrument jumped to the end at the first touch of the
  wheel and stayed there. Distance through the block is what actually tracks
  the reading, and it advances evenly now: step two at 360px of scroll, three
  at 600, four at 840, five at 1200.

  It still runs on nothing. A scroll listener that does its work in an animation
  frame, no interval, and a reader who asked for less motion is given the whole
  picture at once instead.

## 1.30.1, 27 September 2026

- The hero's right hand block is centred in the column it was given. Held to
  the column's left edge, the buttons took 409px of 678 and the marks under
  them 328, so a third of it stood empty beside both and the block read as
  pushed aside rather than placed. The three of them now share one axis: the
  sentence, the buttons and the marks all centre on 1605 of a column running
  1266 to 1944.

  What moved them was not what it looked like. They are narrower than the area
  they sit in, so centring them is justify-self on the item; justify-content
  inside it does nothing, which is what the first attempt did and why the
  paragraph moved and the buttons did not.

- The five steps are five rows. Side by side each had about 250px to say itself
  in and the block ran 1328px wide, so the words broke into short stacks and
  the row was wide without being full. Across, a step is one line of reading:
  what it is called, what happened, and the line the protocol wrote, left to
  right. The three columns hold their positions down all five rows, and the
  block stops at 1180px -- a width a sentence can be read across rather than
  whatever the window happens to have.

  The instrument above them stops at the same 1180. One block with one edge,
  rather than a reading and its explanation stepping in and out of each other.

## 1.30.0, 27 September 2026

- Every screen is banded now, not just the home page. A band reaches the edges
  of the window and puts its own content back where the column had it, so the
  ground is a band and the words never move: the explanation's three parts, the
  cover flow's rail and its "what happens after you buy", the proof page's three
  questions, and what the holder's page found. It is done from inside the column
  rather than by rebuilding the markup of four screens, and it is measured
  rather than assumed -- a band a few pixels wider than the window is a window
  that scrolls sideways, and none of the five screens does at 2560, 1440 or
  390px.

- The five steps are a row that is actually a row. They were five columns whose
  contents each centred themselves, so every one started at a different height
  and the five code boxes landed wherever their own paragraph left them -- a row
  of five things that plainly were not a row. Subgrid puts the label, the
  heading, the words and the line the protocol wrote on four rows the whole band
  shares. Measured at 2560 and 1440, in English, Turkish and German: every one
  of the four aligns to the pixel, and the boxes share a floor as well as a
  ceiling.

  Five into three columns is a row of three and a row of two, which is the
  asymmetry it was meant to fix, so the row is five columns or it is a stack.

- The covers are in the hero, stacked beside the heading. They were in a band
  below the fold while the column under the heading was empty for its whole
  height -- the five things this page exists to sell, under the part of the page
  nobody scrolls to. Each is a row now rather than a card: the picture is a
  thumbnail at the size it was drawn, the name and what it pays on beside it. A
  card with a banner across it is 200px tall and five of them is a thousand,
  which is not a column.

  The right of the hero had 370px of nothing between the buttons and the marks
  under them, because the covers are taller than the words beside them and the
  height had nowhere to go. It has a row to go to now, and the gap is 26px.

## 1.29.0, 27 September 2026

- The page is built in bands now, and the column stopped being the problem it
  was being treated as. The complaint was a real one and had been made more
  than once: on a wide screen the site is a narrow strip with nothing either
  side of it. Measured on a 2560px screen, the composition was 1340px wide with
  610px of nothing before it and 682px after -- half the screen was margin.

  The first two repairs were both wrong and both were mine. Stretching the
  instrument to fill the space made a bigger panel with the same drawing inside
  it, hollow; the comment already in the file had said so. Then the container
  was widened to 2080, which is the obvious repair and the wrong one. The sites
  this one is measured against say so plainly: Stripe caps its main column at
  939px, Lemonade at 1025, Hippo at 1250, Linear at 1280. Ours was 1240 and was
  already right. None of them is wide. All of them are banded -- the section
  reaches the edges of the window and the words stay where words can be read,
  so the eye never meets a column adrift on an open field.

  So the column goes back to 1240, rising to 1440, and a band is what fills the
  screen. Three of them on the home page, each full width with its own ground:
  the hero on its gradient, the covers on the sunk surface, the live readings on
  the ground. The surfaces are the palette's own, already measured by the
  contrast tests, so no band can introduce a pair nobody has checked.

- The hero is a row, and plays once. It was two columns with a tall panel pinned
  beside five steps of text, and that panel is what forced everything narrow: a
  drawing in a fixed portrait frame, which cannot grow without going hollow. A
  seismic reading is a thing that is long, so it is drawn long -- a new frame at
  seven to one, across the full width, with the words above it as a row of their
  own: the heading on one side and what follows it on the other.

  A phone gets the tall drawing instead, because seven to one at 390px renders
  51px high, which is a hairline. Two drawings of one instrument, and the screen
  chooses; neither is the other stretched, since a drawing forced into a frame it
  was not drawn for is the fault this release is about.

  The five steps are five columns, so the whole policy is on the screen at once
  rather than one fifth of it. That made the old behaviour incoherent -- it
  showed whichever step was crossing the middle of the window, and now they all
  are -- so the instrument plays the policy through once when it arrives, from
  written to paid, and then holds the whole picture. Once, on arrival: nothing
  on an interval, nothing drifting, nothing burning a background tab.

  This is the home page. The other four screens are still laid out the way they
  were and are next.

## 1.28.0, 27 September 2026

- The register is a window, and says which one. It looked like an archive while
  being one, and that is the whole of what made the figure beside it read as a
  contradiction: 2,976 payments on a button and a single row underneath. Two
  repairs were tried on the wrong end of it. 1.26.0 added a sentence explaining
  the gap where a reader happened to meet it. 1.27.0 dropped the counts until
  they matched what was kept, which threw away the history to make the page
  consistent. Raising what is kept until they agreed was the third wrong answer
  waiting to be given: ten thousand records kept so that a page can show ten is
  ten thousand records nobody reads.

  Nobody needs the whole book to see that this protocol decides. So the page
  shows the most recent ten of a stage and says so beside the buttons that choose
  it, before a reader meets the rows rather than after -- and the count on each
  button is every decision of that kind this protocol has ever made, with nothing
  capping it. The gap between the two is the design, stated, instead of a
  discrepancy to be explained. The sentence 1.26.0 added is gone with the thing
  it apologised for.

  Driven through the page's own buttons against the live protocol: ten rows for
  every decision, ten for those that did not trigger, the one payment the book
  still carries, and none for the stage with no data, which is correct because
  there are none. No console errors.

- Every stage has its own ten, including the one where the data never came. That
  filter was missing while the protocol has always decided it and the endpoint
  has always answered for it, so the one question a parametric buyer is most
  nervous about -- what happens when the source says nothing -- was the one
  question the register could not be asked. Its label is the words the row itself
  carries, so it needed no new ones.

  One figure it will not show honestly for a while: the uncapped count restarts
  from 2,003 rather than 74,474, because 1.27.0 reached the server and dropped
  the counts of records already deleted. Nothing brings those back. From here the
  count is uncapped again, as it was before, and this is what it is counting from.

## 1.27.2, 27 September 2026

- The row above the hero moved the hero, and the measurement that said it did
  not was the fault. 1.26.0 claimed the digest holds its height from the first
  paint, "measured at 55px empty and 55px full". The measurement was worthless:
  the feeds it used answered instantly, so by the time the row was read it had
  already filled. "Before" was the same moment as "after", and the state the
  measurement existed to check was never on screen.

  Measured properly -- the live feeds, with their answers held back four seconds
  -- the row stood 65px while it said it was reading and 55px once it had
  readings, so the hero moved ten pixels under the reader at the top of the page.
  That is the whole thing the standing-in line was added to prevent.

  Two constants were tried before the fix and both were wrong. The line of text
  was 43px against an assumed 37; then a 37px floor against a chip that actually
  measures 35.19px here. The figure moves with the font, so no number written
  here is right for long. The stand-in is a chip now, which is the same height as
  a chip by construction, and the row is 55px in both states on a phone and a
  desktop with nothing to get wrong. Its test holds that mechanism rather than
  the sentence, because the old test passed for the whole time the row was ten
  pixels out.

  Fixing the height broke the width, and that was measured too. A chip sits in a
  track that hides its overflow behind a mask, and the sentence the digest
  carried wanted 451px of a 252px track: a phone was shown two thirds of it, with
  the mask making the cut look like a fade. What the row says is one row long now
  -- and for the case where the protocol is not answering, it says what the sign
  in strip already says, which is short and already translated. Where even the
  short one does not fit, at 320px, it ends in an ellipsis, which at least says it
  was cut; that needed the row to stop being as wide as it wants, because a
  max-content row makes "as wide as the row" mean "as wide as you like".

  And the languages were never switched. Every measurement in 1.26.0 that claimed
  four or six languages set localStorage's "clause.lang"; the page reads
  "clause-lang". One language, measured four times, reported as four. Measured
  properly, at 390px and 320px, in English and all six: nothing overflows.

  Found by running the published page against the live protocol in a browser,
  which is also where the second look came from: the digest carried six chips
  rather than nine because the United States flight feed genuinely had no delay
  programmes in force. Three feeds, one of them empty, three plus three plus
  nothing -- the row was right and the expectation of nine was the mock's.

## 1.27.1, 27 September 2026

- 1.27.0 is reverted, and one part of it cannot be. The code is back to what
  1.26.0 shipped: forgetting a settled demonstration policy keeps its
  arithmetic again, the retention keeps 2,000 rather than 10,000, payments keep
  400 rather than 2,000, and the invented buyers have no target to stop at.

  What is not back is the numbers. 1.27.0 reached the server and did the one
  thing it was built to do first: it dropped the counts of decisions whose
  records had been deleted. The live protocol reported 74,474 decisions and
  2,976 payments before, and 2,003 decisions and 1 payment after. Those counts
  were the only thing left of policies that no longer exist, so nothing restores
  them -- not this revert and not any arithmetic. The figures are the records
  now, and they stay that way for the records that were already gone.

  What the revert does bring back is the behaviour that produced the gap: from
  here, a settled demonstration policy forgotten by the retention will again add
  to the published count without leaving a record behind it, and the proof page's
  own sentence about a register shorter than its count -- which 1.26.0 added and
  which this keeps -- will be doing that work again.

  The entry below is left in place rather than removed with the code. It is the
  only record of why the live figures changed, and a changelog that quietly drops
  the release that changed them is a changelog that cannot be used to find out.

## 1.27.0, 27 September 2026

- The figures answer for records that are here. 1.26.0 gave the proof page a
  sentence explaining why it could count 2,976 payments and open one of them.
  This removes the thing it was explaining. Measured on the live protocol:
  74,474 decisions published, and 72,466 of them with no record behind them at
  all -- so of the records the page invited a reader to check, 97 in 100 were
  gone. The sentence was honest about a page that should not have needed it.

  Forgetting a settled policy kept its arithmetic, so every figure the chain
  published stayed the same afterwards. That is the right rule for a real book,
  whose history happened whether or not its record is still carried, and it is
  the wrong rule for a demonstration: a page whose whole argument is that you do
  not have to believe it may not publish a figure it cannot show you. That is
  the thing it argues against. So the demonstration's retention now drops the
  arithmetic with the record, and the counts already in the saved book -- the
  ones whose records were deleted permanently, which no arithmetic brings back
  -- are dropped once on the next start. A real book's rule is unchanged, and it
  is safe because that retention is the only caller of forgetting and is guarded
  on nobody being able to reach the policy. Nothing a person bought is touched
  by either rule.

  The live page will read smaller for it, and that is the correction rather than
  a cost: about two thousand decisions instead of 74,474, and a payment count in
  the single figures instead of 2,976. Every one of them can be opened.

- The book is allowed to be ten thousand, and the invented buyers stop when it
  is. The retention keeps 10,000 rather than 2,000, payments keep 2,000 of their
  own, and arrivals take a target: the book fills once to the size it is meant
  to be and then nobody else arrives, ever. Unbounded was the actual fault
  behind all of this -- one every eight seconds is eleven thousand a day, which
  the retention then spent itself deleting -- and turning it off in 1.25.0 left
  the book unable to reach a useful size. A bound answers both.

  Arrivals stay off unless asked for, and what they cost is now written down
  rather than discovered: each one is priced against the book as it stands,
  measured at 938 ms of one core at the 12,000 trials this service runs with, so
  ten thousand records is about 156 minutes of a core fully busy however small
  the gap is made. A gap of two seconds spreads that across roughly eight hours
  at about a third of a core.

  The test for it runs the loop and waits for it to stop, rather than reading the
  source for a switch, because the thing worth knowing is that it actually stops.

## 1.26.0, 27 September 2026

- The live readings are above the hero, not at the foot of the page. Three
  bands carry what the sources this protocol settles against are reporting --
  earthquakes, today's weather, flight delays -- and they sat at the bottom of
  the home page, where a reader who does not scroll never learns that any of it
  is live. That is the strongest thing the page has to say about itself and it
  was the last thing on it.

  One row now carries the same readings above the hero, and it is one row for a
  measured reason. The whole section put there would have taken 457px of a
  390x844 phone: 54% of the first screen before the hero's first word, on a
  product whose buyers are on mid range Android phones. One row takes 55px, and
  the hero moves down 65px -- 7.7% of that screen. It keeps its two columns at
  every width, where the section below stacks, and carries no source line,
  because a one line label is what holds the row to the height of a single chip.

  It says it is reading from the first paint rather than standing empty and
  filling later, so the hero does not move under the reader: measured at 55px
  empty and 55px full, on a phone and a desktop, in four languages. The three
  feeds answer separately, so none of them can draw the row alone -- each
  stores what it built and whoever finishes last draws the merge, which means a
  feed that fails or has nothing still has to say so or the row reads for ever.
  A test counts the two against each other. Severe readings come first, because
  the row scrolls and a glance gets whatever is in view, and no feed may take
  more than three places: a hundred late departures would otherwise be the whole
  row. It carries no links, unlike the bands below, where the earthquake chips
  point at USGS beside their source line -- in front of the hero those are nine
  tab stops a keyboard reader pays on the way to the first thing they came to do.

- A register shorter than its own count says why. The button read 2,976 paid and
  the register could open one of them, with nothing between the two figures to
  explain it -- on the one subject this page exists to be trusted about. 1.25.0
  gave payments a pot of their own and stopped the cause; the records deleted
  before that pot existed are gone for good, and that is what needed saying.
  Empty already explained itself. Short did not.

  Fewer rows than were asked for is what a protocol out of records looks like; a
  full page is just a page and says nothing. The figure asked for is now named
  once, because the sentence compares what came back against it and two twelves
  in two places is one of them being changed alone.

## 1.25.2, 27 September 2026

- Three releases were tested and none of them was deployed. The run that gates
  the deployment has failed on every push since 1.23.1, so 1.23.1, 1.24.0 and
  1.25.0 reached nobody: the filter on the proof register and the end of the
  invented arrivals were both sitting behind a red tick. The page they describe
  was correct the whole time.

  What failed is the test 1.23.1 added to ask the minifier directly whether the
  palette survives being published. Asking it requires esbuild; esbuild lives in
  the Privy bundle's `node_modules`; the runner installs Python and nothing
  else. So the check ran on the machine it was written on and nowhere it was
  relied upon, which is not a check. The runner now installs esbuild at the
  version the bundle's lock file pins, read from the lock file rather than
  written out a second time, and `CLAUSE_ESBUILD` lets the build use a binary it
  did not install itself — the minifier is not the Privy bundle's property, and
  that coupling is the whole of why this happened.

  The sharper half is that the test could have passed without asking anything.
  `CLAUSE_BUILD_ALLOW_UNMINIFIED=1` makes `minify` hand back the stylesheet it
  was given, and then every assertion in it compares the source with itself and
  goes green — which is exactly what whoever met it failing without the tooling
  would have reached for, and it would have looked like a fix. It now checks
  that minification happened before it checks what survived it, and a third test
  holds the runner to installing the binary rather than skipping the step.

## 1.25.1, 27 September 2026

- One old policy was answering for the whole book. `GET /api/policies` came
  back five hundred on the live protocol — two thousand policies, and the
  endpoint unreadable because one of them was written before the airport
  catalogue existed.

  Cover from then names one of six routes rather than two airport codes, and
  `validate_subject` reads that back into the two airports so that cover
  already sold describes and settles the same way. But it runs when a policy is
  written, and a policy already in the book was written before it: restored
  from disk, those records still carry `route` and no `origin`. Every line that
  reached for `subject["origin"]` raised KeyError on them, and because the
  endpoint formats every policy in the book, one bad row was the whole answer.

  The migration belonged to the reading and not only to the door. `airports_of`
  resolves either shape and every reader in the peril goes through it — the
  description, the route key, the sector distance and the scheduled departure,
  all four of which would have failed on the same record. A route nothing can
  resolve comes back empty rather than raising: a record that cannot be named
  is still a record, and failing to name one must not take a page down.

  Both hypotheses I formed before reading the traceback were wrong — a None
  sort key, and a dictionary mutated while being iterated. The log said
  KeyError: 'origin', which was neither.

## 1.25.0, 27 September 2026

- Nobody arrives who was not sent by a person. A policy was written every eight
  seconds — about eleven thousand a day — so that a fresh deployment would not
  demonstrate an empty pool. That was worth having when there was nothing else
  in the book, and it stops being worth having the moment real policies are in
  there: the invented ones crowd the register, they are what the retention then
  has to forget, and every figure on the proof page becomes mostly about them.
  `CLAUSE_DEMO_ARRIVALS` is the gap in seconds; unset or zero, nobody arrives.

- The policies that paid are kept when the quiet ones are forgotten, and that
  is why the register could not show a payment. The demonstration forgets its
  own old closed policies, and payments were in the same pot as everything
  else — so they were flushed at the same rate, and since they are a few in a
  hundred the register ran out of them long before it ran out of anything.
  Measured on the live protocol: 2,974 payments counted, and not one that could
  be opened. A tally outlives the record it counted; only the record can be
  read back. `CLAUSE_DEMO_KEEP_PAID` holds them, four hundred by default.

- And where the register still comes back empty, the page says why. It said
  "no decision of this kind has been made yet" next to a button reading 2,974 —
  a page contradicting itself, on the one subject it exists to be trusted
  about. It now says how many were decided, that this is a demonstration which
  forgets its own old policies, and that any one of them still answers to its
  id.

  These three are one fault seen from three sides, and the one that mattered
  was the third: the first two are a demonstration's housekeeping, and the
  third was the page telling a reader something untrue.

## 1.24.0, 27 September 2026

- The proof register can be read one half at a time, because in practice it
  could only be read as one. The page opens on the last twelve decisions of
  any kind, and in a book where most policies run their term quietly that is
  twelve quiet ones — so a reader looking for a payment scrolled a page of
  "nothing paid" while the figures at the top of that same page said thousands
  had been made. The band's own words are "both halves are here", and they were
  true of the record and not of the reading.

  `GET /api/decided` takes `kind`, one of paid, lapsed or expired, and the
  chain walks back past the quiet decisions to find them. The counts come back
  either way and sit on the buttons: a filter that hid how large the other half
  is would be the advertisement this page exists not to be.

  The walk is capped. It runs under the chain's lock, and a kind that has not
  happened for a long time would otherwise hold it while the whole history was
  read; twelve of anything that happens at all is found in the first few
  hundred.

  The buttons are bound by delegation, on the band rather than on themselves,
  because the register is redrawn on every choice and a handler attached to a
  button that has been replaced is a handler on nothing. And the choice asks
  the protocol rather than filtering the rows already on the page — those are
  the twelve that do not contain what the reader is looking for.

## 1.23.1, 26 September 2026

- Two tests, for a hole found while checking that the last release had
  reached the live page. Everything that measures the palette reads
  `site/index.html`, the readable source, so nothing would notice a minifier
  that dropped a theme block, renamed a custom property or rounded a colour:
  the contrast tests would go on passing against a file nobody is served. The
  minifier is now asked the question directly, which is cheap, rather than by
  running a whole build.

- The second one closes something sharper. The light theme is written twice,
  once for the explicit choice and once for the device preference, and the
  contrast test reads both of them as one span — so the later block overwrites
  the earlier one and only the device palette is ever measured. Left stale on
  purpose, the explicit-choice palette passed all thirty-four contrast
  assertions. That is the kind of fault that hides: whoever is testing has a
  preference set, and sees the half that works. The two are now required to be
  the same palette.

  Nothing served changes in this release.

## 1.23.0, 26 September 2026

- The palette is measured with APCA as well as WCAG, and three tokens moved
  because of what that found. WCAG 2 adds 0.05 to both sides before dividing,
  which inflates every dark pair: an interface can satisfy 1.4.11 and still be
  drawn in lines nobody can follow. That is what had happened. The lines the
  diagrams are drawn with measured 3.03:1 at worst — passing — and Lc 22.3,
  which is a line you cannot see. This is the second time that fault has been
  found here; the first time it was fixed to the 3:1 that was asked for and no
  further, and the hero illustration reading as an empty panel was the symptom.
  `--art-line` is now `#8D9AA7`: the same hue and saturation, lifted until it
  clears Lc 45 on the worst surface it is drawn on. Every WCAG ratio went up
  with it, to 5.85 at worst.

- The light theme's ink ladder had drifted from the dark theme's. Secondary
  text measured Lc 73.0 on the sunk surface and tertiary Lc 67.4 — and tertiary
  is what the 10.5px uppercase labels are set in, which is the size APCA is
  strictest about, not the most forgiving, while WCAG passed it at 4.60. Both
  are darkened by the least that clears Lc 75 everywhere. Secondary is taken
  further on purpose: the first pair of corrected values landed 0.1 apart,
  which is two names for one grey rather than a hierarchy. The gap is 8.3 now,
  against the dark theme's 8.6 — one ladder in both themes, which is what it
  was always meant to be.

- The brand orange was left alone, and that is a decision rather than an
  oversight. In the dark theme it measures Lc 41.7 against a non-text floor of
  45, a near miss on a mark rather than on a word, and the only way to clear it
  is to give the dark theme a different orange from the light one. That fork
  existed once, worked, and cost the brand: two values 0.05 apart in OKLab,
  bright orange by night and burnt brick by day, which is two brands and not
  one. Four points of Lc on a fill is not worth buying that back.

- `tests/test_site_contrast.py` now asks both questions of every pair it
  already checked — WCAG because it is the standard the product is held to,
  APCA because it is the one that matches what a reader sees — and holds the
  ink tiers a measured step apart so a later correction cannot collapse them.
  The formula is pinned to the one figure that can be checked against somebody
  else's published number, mid grey on white at Lc 63.1, because everything
  else in the file is computed with it.

## 1.22.0, 26 September 2026

- The page serves its own typefaces. All three Latin families came from
  fonts.googleapis.com, which costs every visitor two handshakes to somebody
  else before a single word can be drawn in the right face: the browser has to
  resolve and connect to googleapis, fetch a stylesheet, parse it to learn the
  font URLs, and only then resolve and connect to gstatic to ask for them. None
  of that is on the critical path now, and nobody's address is handed to a third
  party in order to read a page about their own insurance. Measured in a
  browser: three families loaded, drawn from this origin, and zero requests to
  Google — in English and in Russian.

  The weights are still asked for as variable ranges rather than as a list, and
  that is not a detail. Archivo and IBM Plex Sans carry their whole ranges in
  34 KB and 45 KB of Latin; the four weights this page actually sets, fetched
  as four static faces, cost 115 KB for Plex Sans alone. Only the alphabets the
  site is written in are carried — Latin, its extension, and Cyrillic for
  Russian — and a browser still fetches only the slices the text on screen
  needs, which a run in Russian confirmed by pulling the Cyrillic ones and
  nothing else.

  Japanese stays where it was, on purpose. Its cut is a CJK family that Google
  serves as a hundred-odd slices keyed by unicode-range, so a Japanese page
  pulls only the characters it sets; carrying it here would mean shipping
  megabytes to everybody for the readers of one language. It is fetched on
  demand, after first paint, by them alone. The test that holds the rest of it
  in place allows exactly that one exception — and it first failed on its own
  explanation, because prose about why the fonts moved is not a request, so it
  now looks at what the page fetches rather than at what it says.

## 1.21.0, 26 September 2026

- A price promised for ten minutes is still that price after the service is
  replaced. The promise is on the screen in words, and it was kept in a
  dictionary in the process, which made it exactly as durable as the process —
  and replacing the service is something an operator does on purpose, in the
  afternoon, while somebody is part way through buying. That buyer pressed the
  button and was told the price had moved.

  So the promise is no longer stored. `clause/api/holding.py` signs it and hands
  it to the buyer, and it comes back with the purchase: the identifier *is* the
  promise. It carries the price and the cover it is a price for, so presenting
  it for different cover does not work, presenting it after ten minutes does not
  work, and making one up does not work. Anything holding the key can honour it,
  which covers a restart, a replacement, and more than one process behind one
  address. The dictionary stays beside it as a courtesy: while the process that
  quoted is still running it hands back the whole quote, including the prose a
  token does not carry.

  The key is derived from the authenticator's own secret rather than being a new
  one, because that secret is the only thing here already arranged to outlive a
  restart — the store keeps it and puts it back. Derived and not reused, so a key
  for one purpose cannot verify a statement made for another.

  The test for this was written wrong first and said so in its own docstring: a
  fresh service on the same seed prices identically, so comparing two numbers
  across a restart passed whether or not the promise was honoured. Breaking the
  token reader on purpose left it green. It now promises a price the pool would
  not give, so the two outcomes cannot be confused — honoured, the policy costs
  what was promised; not honoured, the pool prices again and refuses.

## 1.20.0, 26 September 2026

- A purchase whose reply went missing can be asked for again, and asking again
  buys nothing more. This is the failure a buyer meets most often and can do
  least about: the application is one POST, and if its answer is lost on the
  way back — a phone changing network between sending and hearing, a proxy
  dropping the connection, the protocol being replaced mid-request — the
  browser cannot tell a request that was never read from one that was read and
  acted on. Sending a second one is how somebody is charged twice, so the page
  did not: it said the cover might already be theirs and they should go and
  look. That was usually wrong in the worst direction, because the request had
  in fact been read and the cover was already written.

  What makes the second ask safe is that the challenge it is signed over is
  single use, so the protocol can recognise the same purchase arriving twice.
  `clause/api/repeat.py` keeps what each signed request was answered with for a
  quarter of an hour, and `POST /api/applications` answers a repeat with the
  application it already wrote, or the refusal it already gave, without writing
  anything. Refusals are kept too: without that, the second ask reported an
  authentication failure about a challenge the buyer had spent legitimately,
  and the reason they were actually refused for was lost. The page then asks
  exactly once more, and only when the failure carried no answer at all — a
  refusal is an answer and is shown as one.

  Nothing secret is kept. A signature that travelled once may have been
  captured, and holding a captured signature is not holding the key that made
  it, so a repeat reads back the application it already paid for and is given
  no session: the page that legitimately asks again signed in seconds earlier
  and still holds its own.

  Measured, not assumed: driven in a browser against a proxy that answers the
  first application and then drops the reply on the floor. Before, that ended
  on the banner about not knowing whether the money moved. Now the buyer gets
  their application, and the protocol wrote one.

  The other direction is covered too. A first ask lost on its way *out* is
  still being decided when the second arrives, and the challenge is spent by
  then — which from the outside is indistinguishable from a forged one. That
  used to answer "not authorised" to somebody whose cover was about to exist.
  It now answers that the purchase is being decided, and the page says so
  without promising the money stayed put: "not sure", never "nothing was
  charged". Only a refusal may promise that.

- A purchase no longer signs in twice. It always called `signIn()`, even
  holding a session, so the device door registered, challenged and verified a
  second time for one purchase: three round trips added to the most fragile
  moment in the flow, on exactly the slow line where one of them is most
  likely to be the one that fails. Seven requests after the button, now four.

- `asked again` is counted, by day and by peril. It is the only visible measure
  of how often a reply goes missing, and one that keeps climbing is a network
  or a proxy to look at rather than a buyer doing something wrong.

## 1.19.0, 26 September 2026

- The weather sources were never asked. A reference is written without a
  scheme, because that is the form a policy carries and the form the host
  checks are made against, and nothing added one before the request was made.
  Every read of the archive failed with `unknown url type` into a dictionary
  nobody was watching, so rain, storm and drought policies read nothing and
  settled as though the sky had been dry. The quake side was unaffected: its
  agencies' addresses carry https already, which is why this survived a suite
  that passes. Nine hundred tests went through it because every feed test
  reads bytes recorded in `tests/feeds` rather than making a request.
- With the scheme added, the archive answers 429. Open-Meteo's free tier is
  rate limited by address, and a server sharing one spends the day's quota and
  then reads nothing — which does not look like an error, it looks like a dry
  week. `CLAUSE_OPENMETEO_KEY` sends the same query to the customer host. The
  key is applied when the request is made and never written into a reference,
  because a reference is the public query anybody can repeat and an operator's
  credential does not belong on the proof page. Only https is opened at all
  now: a reference naming a file on this machine is not a source somebody else
  can check, which is the whole of what a reference is for.
- The feed's failures are on `/api/health` under `sources`, with whether a
  subscription is held. Unreported is how the above stayed broken. It does not
  change whether the service is well: an agency being down is not this service
  being unwell, and flapping a health check on somebody else's outage would
  take the site off its own load balancer.
- The proof page answers the three questions somebody deciding whether to
  trust an insurer actually asks, in that order: is there money to pay you,
  who decides that it pays, has it paid anyone else. It used to open with the
  third and leave the first two on other pages. Each band answers from the
  protocol or says it could not ask. The first measures own funds against
  required capital rather than the balance, since premium taken for cover that
  has not run yet is owed to that cover and cannot also be the capital that
  makes the next sale safe; the pool's summary carries both figures now.
- The orange measured well and could not be read. The primary button carried a
  near-black label chosen on 5.84:1 against white's 3.33:1. Both figures are
  right and the choice they justified was wrong: in APCA, which handles a
  saturated warm hue where WCAG 2's luminance formula does not, that ink reads
  Lc +43.8 at the band the label sits in and the white reads Lc -65.3, against
  a body-text floor of Lc 75. Dark on orange cannot reach that floor at this
  chroma at all. The fill is flat `#C34700` with a white label, clearing APCA
  and WCAG AA together, and the accent as a word splits from the accent as a
  fill: `#A82B00` light, `#FFCAA4` dark. `--signal` is untouched and still
  fills every chart, pip and stroke.
- The dark theme's grey was worse than its orange and nothing had noticed,
  because WCAG 2's flare term inflates every dark pair. Secondary text read
  6.57:1, which is comfortable AA, and Lc -46.7, which is two thirds of the
  way to the floor. Lifted until it clears, and the quieter tier with it.
- The purchase flow is two columns on a desk, with a running summary beside
  the question from the first step, in its empty state. It is a view and never
  an input: every line is changed by going back to the step that set it. The
  mechanism is under the choice — something happens, an instrument records it,
  the figure meets your line or it does not, it pays in that block — and under
  that, the sentence an advertisement would leave out.
- The page stopped being a narrow card in an empty room. On a 2560 monitor the
  content column was 1360 wide with six hundred empty pixels down each side;
  it steps to 1400, 1560 and 1720 now, with prose still capped in ch, so what
  gets the width is the work and not the sentences. The instrument in the hero
  is centred in the window rather than pinned under the header, where a 395px
  panel left 429px of a 900px window empty beneath it.
- The header publishes its own height. Everything that stops below it was
  written against 61px and added its own margin by hand; the header is 89px as
  soon as the navigation wraps, which happens at 1024 in English and sooner in
  a language whose words are longer, and six hand-set offsets were wrong at
  every one of those widths.
- Both translation tests require a space, so no one-word label could ever fail
  them. "Against" reached a Turkish reader in English in a label the rail
  uppercases, arriving as AGAINST with the dotted capital Turkish gives an i.
  There is a test for single words now, and it immediately found a second: the
  New pill on an unopened document, untranslated in all six languages since it
  was written.

## 1.18.0, 23 September 2026

- Cover no longer starts at the till. A premium is the chance of an event in a
  term of so many days, worked out for a buyer who does not know whether one is
  coming, and almost every peril here breaks that in the same way: a named
  storm is on the news about a week before it lands, an aftershock sequence is
  public from the moment the mainshock is felt, and an airline knows its
  aircraft is late hours before the passenger does. Cover bought in those hours
  is bought by someone who knows more than the price does, and the people who
  bought early pay for it. So earthquake waits seven days, storm and vehicle
  flood ten. The wait does not shorten the cover: a year bought is a year of
  cover, starting later and ending later, and the price is unchanged, because a
  window of a given length costs the same wherever it is put.
- An event inside the wait pays nothing and ends nothing. The policy is not
  cancelled and the premium is not returned; the cover starts on the day the
  document names whatever the weeks before it brought. `Chain._too_early` is
  the one place that decides it, and it catches the case that would otherwise
  have been missed: a source whose index is a running maximum is still carrying
  the figure a storm set during the wait on the morning the cover starts. That
  needed a record of when the maximum was last raised, because when the source
  last spoke is a different thing and a quiet day speaks too.
- Drought could not use a waiting period, so it got the rule it actually
  needs. A season is a hundred and fifty days long and cannot be waited out: by
  the time a farmer knows the rain has not come, weeks of it are gone and the
  total is already low. A station's season is now a range of dates in the
  calendar, the same every year, rather than a hundred and fifty day timer that
  started whenever a policy was bought — which is what it was, and which meant
  there was nothing for a deadline to close against. The season a policy
  measures is the next one to open, cover starts on its opening day, and sales
  for a season close fifteen days before it. Cover bought after the deadline is
  cover for the following season, and both dates are on the quote and in the
  contract before anything is paid. The chain's own rainfall source follows the
  same calendar: it opens on the station's day, fills, closes, and stands at
  zero until the next year's opening.
- Flight cover names one flight, so a wait would put that flight outside the
  cover instead of inside it. It refuses the sale instead, and it can now do so
  exactly: a departure date on its own is a different instant in every
  timezone, so the subject carries the scheduled departure time and it is read
  in the clock of the airport the flight leaves from. Cover has to be bought at
  least twenty-four hours before that moment. The step asks for the time beside
  the date, and says why.
- Every rule above is a term of the policy, not a setting: it is written into
  the rulebook, so it reaches section 10 of every contract and the Calculation
  rules page, and section 2 now states the start date in words beside the term.
- The price bar says what the cover pays at each reading, not only where it
  starts paying. "Pays from magnitude 5.5" answered half of what a buyer was
  asking; the other half — how much, at which reading — was only on the chart
  further down the page. It is now the line beside the price, and a row of the
  confirm step's summary, alongside the day the cover starts and one sentence
  on why that is not today.

## 1.17.0, 23 September 2026

- Cover held earns RIALO, paid by the platform out of its own fee. A
  programme that pays people to buy insurance is an inducement, and in most
  places a regulated one; this is deliberately not that, and the three rules
  that keep it on the right side of the line are enforced in
  `clause/protocol/rewards.py` rather than promised in a footnote. It is not a
  discount: the price on the screen is the pool's price and stays so, because
  that price is an actuarial statement about risk and a loyalty scheme has no
  business moving it. It is not the insurer's money: the platform's fee comes
  from the issuing company's fronting fee and never from the buyer, and the
  award comes out of that and nothing else. And it cannot promise more than
  the platform has earned: the budget is a share of net fee income, an award
  beyond it is credited as far as the budget reaches, and the shortfall is
  recorded. A rewards programme that can run out of money without saying so is
  a lie told slowly.
- What is rewarded is cover held, not cover bought: the limit, for the days it
  was actually in force, at a rate raised by each unbroken renewal. A year of
  cover earns a year's worth and a policy cancelled on its second day earns
  two days, so there is no bonus for buying a longer term, only for holding
  one. Nothing is credited until the term has run, because what a live policy
  has earned so far can still fall; it is shown as earning rather than as a
  balance. Continuity uses the same grace as the renewal instruction, so the
  page cannot say a policy was renewed while the programme says it was not,
  and an award keeps the rate it was earned under.
- The unit is RIALO, and on this build the chain is simulated and so is the
  balance. The panel says that in the same words the test network warning
  uses: nothing is held in a wallet, nothing can be spent, and what is
  credited is an account of what would be owed.
- A version bump publishes its own release notes. The notes and the changelog
  are the same words, and writing them twice is how they come apart; the
  workflow reads the version out of the source, reads that version's section
  out of CHANGELOG.md and creates the release with the tag it needs. A test
  keeps the two from drifting.
- The README opens with what this is and shows it: the build's state, the home
  page, and policy tokens across four tiers.

## 1.16.1, 22 September 2026

- The policy token is the bargain, drawn, rather than the policy retyped.
  Every token was the same card with different words on it: eleven labelled
  fields, a sixty-four character hash nobody can read, and a line of small
  print. A wallet renders attributes itself, so repeating them in the picture
  only made the picture a form. The image now carries the one thing a list of
  traits cannot: the index this cover watches, the level it has to reach, and
  the moment the two meet. The trace is generated from the policy id and the
  hash of the terms, so no two tokens are alike and the drawing is a function
  of the contract rather than an ornament laid on it. The terms hash is
  thirty-two marks instead of sixty-four characters.
- Each peril has its own signature and its own subject behind it. An
  earthquake is quiet and then one burst; a season that does not fill
  descends past the line; a flight is flat until the step the delay puts in;
  wind is a gust train; a day's rain is rain above and water that rises and
  stays up. Behind each, the thing insured: a house on moving ground, a sun
  over furrows, a plane, a car in water. A token is read at the size of a
  thumbnail, and at that size a trace alone does not say which kind it is.
- A tier — Diamond, Platinum, Gold, Silver, Bronze — names the band the cover
  falls in. It is the limit and nothing else: a grade of size, not a grade of
  quality, and the description says so. Its metal is spent on the edge and on
  one stamp, never on the trace, so the card keeps one loud thing and that is
  the state.
- A deposit from a wallet names the chain it is watched on. The mechanism was
  built and waiting only for addresses in the environment; turning it on that
  way would have printed twenty bytes with nothing saying where to send them,
  and the same twenty bytes exist on every EVM chain and all of their test
  networks. A destination with no chain named is no longer offered at all, and
  a deployment on test networks declares it, so the page can say what that
  means: send test USDC only, and the balance it credits is not money either.
- Every page is measured now, in every language, at three widths: twelve
  routes by seven languages by three widths, checked for a label that leaves
  its picture, a label that leaves the box it was drawn in, two labels on top
  of each other, a page that scrolls sideways, a box that hides its own text
  and a target too small to hit. The first run found the fault I had just
  diagnosed elsewhere still living in the hero: in French the policy's own
  sentence ran out of the handset and over the bezel. The handset is no longer
  drawn — the waveform and the trigger line are a drawing, the policy and the
  payout notice are writing, and writing belongs in the page, where it wraps.
- The rest of what it found: a drought label anchored at the left grew off the
  right edge of its drawing; every peril card on a phone lost the bottom
  thirty-two pixels of its illustration to a height cap meant for a narrow
  card; two Istanbul districts on the pool's map are six units apart with
  names ninety long, so their labels were one smear; a policy id in the
  register was an eighteen pixel target where 2.5.8 asks for twenty-four; and
  the step cards on three pages slid up into a block that clips its own
  corners, arriving with their bottoms cut off.
- Forty refusals had no translation in any language. A person is told no in
  Python, not in the page, and nothing was reading those sentences, so the one
  moment the protocol says no was the one moment it dropped into English. They
  are translated, and a test now collects every Refused and every safe_detail
  fallback and fails when one cannot be read.
- Complaint reasons are statements rather than headings. "The company: how it
  dealt with me" is not a sentence in English either, which is why every
  translation of it came out broken.
- A storm policy read its cover name and half its address line in English on
  an otherwise Turkish page. Those sentences come from the protocol, and
  neither the literal scan nor the markup scan could see them; a test now
  enumerates every cover name and subject line the protocol can compose.

## 1.16.0, 22 September 2026

- The home page follows one policy from written to paid, and the reader
  moves it. The picture used to run a six second loop: it told the whole
  story and then forgot it, every six seconds, whether or not anybody was
  looking. Now five steps scroll past a picture that holds, and each step
  adds to it instead of replacing it, because that is what happens to a
  policy: the rule does not stop existing when the ground moves, and the
  reading does not stop existing when the money lands. The first step is
  drawn before any script runs, so the page at rest is the hero it always
  was, and the source the policy listens to is on it from the beginning,
  quiet.
- Nothing in it runs on a timer any more. One IntersectionObserver decides
  which step is being read; there is no interval to drift, nothing burning
  a background tab, and for a browser asking for less motion the steps
  still change but nothing eases, ripples or draws itself. On a phone the
  picture is no longer hidden: it sits below the header and travels with
  the steps, which is where the whole argument is.
- The proof page opens with the record instead of asking for one. It used
  to open with an empty box wanting a policy id, which only somebody who
  already had one could answer. It now opens with the book's figures and
  the policies the chain decided last, paid and not paid, each with the
  line it was written on and the figure that met it. `GET /api/decided`
  serves them; it publishes no field the chain was keeping, because a
  settlement is already a public transaction and any policy's lineage
  already answers to its id, and it leaves the holder out because no part
  of the argument needs it.
- Both halves are in that register. A policy that ran its term without the
  index ever reaching the line is the harder promise to keep, and a page
  that lists only what it paid is an advertisement. The payment is the
  loud figure in its row; "nothing paid" sits in the same place and the
  same size and does not shout.
- A heading breaks a word rather than running off the page. The German
  home page headline measured 387px in a 308px column and had only ever
  been invisible because the hero clipped whatever left it; the hero no
  longer clips, so the headline was caught the moment it stopped being
  hidden. Checked in all six languages at 390px and 1366px.
- Translations are checked in the markup as well as in the script. The
  i18n test could only see sentences handed to `t()`, so a heading or a
  paragraph written straight into the page could ship without one and
  reach a Japanese reader in English with nothing to say so. It now reads
  every `data-i18n` element the way the page itself does, and it found one
  line that had been in that state already.

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
