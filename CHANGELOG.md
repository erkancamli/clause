# Changelog

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
