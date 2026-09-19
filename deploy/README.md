# Putting Clause on a server

Three commands, then a certificate, then it is live. What follows is what each
one does and what to check afterwards, because a protocol that holds money
should not be installed by pasting something you have not read.

## Before you start

You need a server running Ubuntu with a public address, and a subdomain pointing
at it. The site and the API are deliberately separate hosts:

    clause.insure          the interface, on Netlify
    api.clause.insure      this service, on your server

In Netlify's DNS for `clause.insure`, add an `A` record with the name `api` and
your server's IP address. Confirm it before installing, since the certificate
cannot be issued until the name resolves:

    dig +short api.clause.insure

## Install

Copy the source to the server, unpack it, and run the installer:

    scp clause-1.0.1.tar.gz root@YOUR-SERVER:/root/
    ssh root@YOUR-SERVER
    tar xzf clause-1.0.1.tar.gz && cd clause
    sudo bash deploy/install.sh api.clause.insure you@example.com

It installs Python, nginx and certbot; creates an unprivileged `clause` user;
builds a virtual environment; writes the service, the nginx site and the
configuration file; and obtains the certificate. Running it again is safe and is
how you deploy an update.

## Check it

    curl -s https://api.clause.insure/api/health

You should get JSON with a block height that changes between calls. If not:

    systemctl status clause
    journalctl -u clause -n 50 --no-pager

## What is switched off, and why

Configuration lives in `/etc/clause/clause.env`, readable only by root. Every
setting there defaults to the safe value when absent, so the file exists to turn
things on deliberately rather than to make the service work.

**The demonstration endpoints are off.** `/api/chain/inject` and
`/api/chain/silence` drive the chain by hand: they settle real policies and
silence real sources. With `CLAUSE_DEMO` unset they return 404, so they do not
even reveal that they exist. To use them for a presentation:

    CLAUSE_DEMO=1
    CLAUSE_OPERATOR_TOKEN=<openssl rand -hex 32>

Then every call to them needs `x-operator-token`. The service refuses to start
with the first set and not the second, because a demonstration build reachable
from the internet without a token is the worst configuration available.

**The faucet is off.** `CLAUSE_FAUCET=1` funds every newly connected address,
which is what makes the interface operable without arranging money first, and is
free money in public. On for a demonstration, off otherwise.

**The schema page is off.** It lists every route including the ones that move
money. `CLAUSE_PUBLIC_DOCS=1` publishes it.

**Origins are named.** `CLAUSE_ORIGINS` lists the sites whose browsers may call
this API. Never a wildcard: every write here is a POST, so a wildcard would let
any page on the internet act through a visitor's browser.

## Admitting a company

A company registers itself, from the public form at **For insurers**. That needs
nothing from you: no account on this server, no token, no email. The
registration arrives `pending`, which means it is visible on the site and can
write nothing at all.

Letting it write is your decision, and it is the only manual step in this
protocol. Nothing here can read a regulator's register from inside a block, so a
person takes the licence number to the authority's own public register and
confirms it is held by that company, for that class of business, and still in
force. A registration that activated itself would mean anyone could claim to be
an insurer here.

To be able to take that decision, set the operator token and restart:

    CLAUSE_OPERATOR_TOKEN=<openssl rand -hex 32>

Then, on the site, go to **For insurers**, scroll to *Reviewing registrations*,
and sign in with it. The token is sent once and exchanged for a session that
expires in 45 minutes and does not survive a restart of this service. The screen
lists every pending company with its licences, its contact, and the regulator
that would hold each reference, and will not let you activate one until you tick
the line saying you checked. What you write in the note, and the name you signed
in under, are kept with that company permanently, including after it is
suspended.

There is no other way in. Without the token the endpoints answer 401, and on a
deployment where the token was never set they answer 404 and the screen says so.

### What anchors a registration

A name and a licence number are claims. Three things turn them into
something a reviewer can rely on, and the review screen shows all three
under *What anchors this registration*:

1. **The LEI.** The company gives its Legal Entity Identifier and the server
   looks it up at GLEIF (api.gleif.org, free, no key) the moment it
   registers: legal name, status, country, and how well the name matches.
   Every insurer of any size has one. A registration without one is shown
   as unanchored, not refused.
2. **Control of the company's domain.** After registering, the company is
   given one line to publish at `https://<its domain>/.well-known/clause-insurer.txt`
   (the signing address). The server fetches it, on registration and
   whenever "Run the automatic checks again" is pressed. A licence number
   can be copied from a public register; a file on the company's own
   website cannot be put there by a stranger.
3. **The licence, by a person.** No supervisor offers a free API for this,
   so the screen links the right register for the licence's country (SEDDK
   and TSB for Türkiye, EIOPA for the EU and EEA, the FCA register with the
   number filled in for the UK, BaFin, ACPR, DGSFP, IVASS, the FSA, NAIC,
   CNSF, FINMA) and the reviewer reads it. Activation records which of the
   four items (LEI, domain, licence, documents) the reviewer confirmed, in
   the note that stays with the company.

Documents the company uploads (licence certificate, register extract; PDF,
PNG or JPEG, 3 MB each, 4 at most) are kept under `$CLAUSE_STATE_DIR/evidence/`
and opened from the review screen. They are evidence of what is claimed, not
proof: a PDF can be edited, a register cannot, which is why item 3 is a
person's.

Suspending is the same screen and takes effect immediately: the company stops
being matched to new cover. Policies already written are unaffected, and are
checked against the registry again before anything pays out, which is where a
lapsed licence stops a payout that would otherwise have gone out on invalid
paper.

## The book is kept

Everything that is a record, not a calculation, is written to
`/var/lib/clause/clause.sqlite`: every policy and what happened to it, the
pool's ledger, balances and their movements, every settlement the chain
performed, every company with its licences and review trail, and the sign in
keys and Privy accounts. It is saved after every change and every five
seconds, and restored when the service starts, so a restart or a new version
changes nothing anyone can see. Open policies are armed on the chain again.

Back it up like any database. A consistent copy while the service runs:

    sudo sqlite3 /var/lib/clause/clause.sqlite ".backup '/root/clause-backup.sqlite'"

To start again from nothing, stop the service and move the file away; do not
delete it until you are sure.

## Signing in through Privy

The site offers email, Google, a passkey or a wallet through Privy when the
server has an app id. Add this line to `/etc/clause/clause.env` and restart:

    CLAUSE_PRIVY_APP_ID=<your app id, from the Privy dashboard>

The app id is public. The Privy app secret is not used anywhere; do not put it
on the server. The server reads Privy's public keys from auth.privy.io, and
`curl https://api.clause.insure/api/privy` answers `"enabled": true` once it
is on.

Privy's window lives in `site/privy/`, built from `privy-bundle/`. To rebuild
it after upgrading Privy: `cd privy-bundle && npm install && npm run build`.

## Applications, offers and cancellation

A purchase through the site is an application. The buyer chooses which
company issues it (every company licensed for that cover is offered, with
its fee and its terms), signs at the price shown, and the premium and fee are
held. The issuing company then does its checks (sanctions screening;
identity above 10,000) and approves or rejects on its company page. Stand in
companies have nobody, so on a demonstration there are two ways to decide for
them. The operator page opens on its "Applications" tab whenever any wait.
Or, to show the insurer's side as an insurer: sign out, sign in as a company
(any account will do), and on the Company page take the desk of the stand in
named on the application; its applications then appear there with the
checks to confirm and the approve and reject buttons. "Leave this desk" gives
it back. This needs CLAUSE_SPECIMENS=1 and does nothing otherwise. An
application nobody decides in three days is refunded.

Cancellation follows the buyer's law: anything can be cancelled for a full
refund within an hour; within the cooling off period (14 days in the EU, UK
and Türkiye, 8 in Japan, none for cover under a month) the whole premium and
fee come back; after that earthquake cover refunds the unexpired part, and
rain and flight cover run to the end of their term.

## Money in: how a person adds balance

Balance is USDC at the person's address. Two ways in are offered, both
announced on My cover under "Add balance" and both confirmed by a person:

- **Bank transfer.** Set `CLAUSE_FUNDING_IBAN`, `CLAUSE_FUNDING_NAME` and
  `CLAUSE_FUNDING_BANK` to the operator's (or the issuing company's) account.
  The person announces an amount and gets the IBAN and a reference
  (`CL-XXXXXX`) to write on the transfer.
- **A wallet deposit.** Set `CLAUSE_FUNDING_RIALO`, `CLAUSE_FUNDING_SOLANA`
  or `CLAUSE_FUNDING_EVM` to addresses you hold. The person is shown the
  address and the reference to put in the memo.

Every announcement is a funding request. On the operator page, tab
"Money in", each waiting request shows the account, the amount announced,
the sender wallet if given and the reference; the operator checks the bank
statement or the explorer, types the amount that actually arrived and
confirms, and only then is the address credited, with the operator's name
and the bank or transaction reference on the record. "Nothing arrived"
closes a request with a note the person sees. A request nobody confirms in
thirty days expires. A bank transfer is always confirmed by a person. A wallet deposit is
confirmed by the service itself when an RPC endpoint is set
(`CLAUSE_FUNDING_SOLANA_RPC`, `CLAUSE_FUNDING_EVM_RPC` with
`CLAUSE_FUNDING_EVM_USDC`): every half minute it reads the USDC transfers
into the receiving address, matches them (Solana: the reference in the
memo, or the sending address; Ethereum style chains: the sending address the
person gave, since a token transfer has no memo) and credits what actually
arrived, recording the transaction. A transfer it cannot match stays on the
operator's list. Rialo deposits are confirmed by the operator until Rialo's
RPC is public.

The demonstration faucet (`CLAUSE_FAUCET=1`) is separate and off in a
public deployment; "Add balance" is what a public deployment offers.

## Protecting the code

The Software is proprietary: see `LICENSE` at the top of the package (all
rights reserved; no licence granted). What that means in practice:

- The server package (`clause-1.0.1.tar.gz`) is the readable source. It goes
  only to your own server; do not publish the repository.
- The site package for Netlify is built by `python3 site/build.py` and
  contains the minified page (`site/dist/`): no comments, no readable
  names, a copyright notice at the top of every script. A browser has to
  receive the page to run it, so this is a deterrent and a clear statement
  of terms, not secrecy; anything that must stay private (pricing internals,
  keys, the book) lives on the server and is never sent to a browser.
- The API host does not serve its source, its schema page is off unless
  `CLAUSE_PUBLIC_DOCS=1`, and the state directory is readable by the
  service alone.

## Partners, payouts and Rider's purchases

Three things added together, each off until you turn it on.

**Partners** sell cover inside their own product. Admit one on the operator
page (tab "Partners"): it gets an API key and a webhook secret, both shown
once. The partner's premiums come from its own address, which it has to fund;
on a demonstration server the address is funded with pretend money. The
public API reference is on the site under "For insurers".

**Payouts to a bank or a mobile wallet** are chosen by each holder on their
My cover page. Until a payment partner is connected (`CLAUSE_OFFRAMP_URL`,
`CLAUSE_OFFRAMP_SECRET` in the env file) every such payout waits on the
operator page, tab "Payouts to banks", with the full destination. Make the
transfer from the issuing company's account and mark it paid with the bank's
reference; marking it failed returns the money to the holder's address.

**Rider buying** needs a signed permission from the person (My cover page) and
two settings on the server: the SHA-256 of a purchase key, and a second latch
that alone holds that key (see the env example). Without both, Rider only
prepares proposals, as before.

Payouts can also be directed to a wallet on a chain: a Rialo public key (the
playground's custodial keypair, for instance), a Solana address or an
Ethereum style address, chosen under "Where payouts go" and signed like a
bank preference. On the manual rail these arrive as orders for the operator
like bank transfers do: the operator sends the USDC and marks the order
paid. Addresses in this build are shown in Rialo's shape (32 bytes, base58);
accounts made before this build keep their 0x addresses and keep working.

## Earthquake models

Earthquake cover is priced in Türkiye by its fault model, and elsewhere by a
catalogue model per country, built offline and shipped as files in
`clause/hazard/models/`. A country is sold only if its model passed a backtest:
fitted on the catalogue up to 2010, then asked about 2011 onward, with the
tests set before any result was seen. Each file records every number, pass or
fail, and `https://api.clause.insure/api/models` lists them.

The server needs nothing extra to read them. To rebuild them (a new year of
catalogue, a new country), on any machine with network access:

    pip install -r requirements-build.txt
    python -m clause.hazard.build

It downloads the catalogues into `hazard_build/`, fits, backtests, and rewrites
the model files. Ship the new files like any other code change. A country whose
model now fails stops being sold the moment the new files are deployed.

## What nginx is doing

Terminating TLS, and rate limiting before the application spends anything on a
request. Pricing is limited to twenty a minute per address because each call
runs a Monte Carlo over the whole book; reading is limited far more loosely.
Simultaneous connections per address are capped, which is what stops one client
holding open a pile of event streams.

It also passes the client's address through, which the application's own limiter
needs. That is why `CLAUSE_BEHIND_PROXY=1` is set: without it, the application
would treat the forwarded header as untrusted and see every request as coming
from nginx.

## Building a release

One command builds both packages from one checkout, after running the
tests, and writes a `RELEASE-<version>.md` next to them:

    bash deploy/release.sh

The version is `__version__` in `clause/__init__.py` (also in
`pyproject.toml`); `/api/health` reports it, so a server and a site can be
checked against each other. Bump it, add the entry to `CHANGELOG.md`, build.

## Updating

    scp clause-1.0.1.tar.gz root@YOUR-SERVER:/root/
    ssh root@YOUR-SERVER 'tar xzf clause-1.0.1.tar.gz && cd clause && sudo bash deploy/install.sh api.clause.insure you@example.com'

The virtual environment and your configuration survive. The service restarts
and reloads the book from `/var/lib/clause/clause.sqlite`: policies, balances,
companies and applications are as they were, and open policies are armed on
the chain again. A book written by a newer build than the one starting is
refused with a clear message rather than misread.

## If something is wrong

    journalctl -u clause -f              the service's own log
    systemctl restart clause             restart it
    nginx -t && systemctl reload nginx    check and reload the front

A port that will not free after a stop is the one failure this service used to
have and no longer does: `TimeoutStopSec` and `KillMode=mixed` in the unit bound
the shutdown, so a held open event stream cannot keep the process alive.

## Pointing the site at the API

The page finds the API in this order, and the first that applies wins:

1. `?api=https://…` in the address bar. This is how you test a server before
   its name exists, and how you point the published page at a different one
   without republishing it.
2. The same origin, when the page is opened on localhost or 127.0.0.1 (a
   developer running the service and the page together).
3. `https://api.clause.insure`.

So once the `api` record resolves and the certificate is issued, the site on
Netlify finds the protocol with no configuration at all. Until then the bar at
the top of the page says **Not connected**, and everything below it is computed
in the browser from the same model, with nothing pretending to be real.

To check the two ends are talking, open the site and read that bar. If it says
not connected while `curl https://api.clause.insure/api/health` works, the cause
is almost always `CLAUSE_ORIGINS`: the browser is calling from a name the API
was not told to accept. The browser console will say so in as many words.

## If something already serves port 80

A server that is already doing work usually has a reverse proxy on it, and
adding a second one is not the answer: they cannot both hold the port, and the
one that loses takes your other sites down with it. Install Clause the normal
way, let the nginx step fail, and put the domain on the proxy that is already
there. The protocol itself is finished at that point: it is listening on
`127.0.0.1:8080` and simply has no front door yet.

Find out what holds the port:

    ss -ltnp | grep -E ':80|:443'

### Caddy

The easy case, because Caddy gets its own certificate. Stop the nginx this
installer put in, then add one block to `/etc/caddy/Caddyfile`:

    systemctl stop nginx && systemctl disable nginx

    api.clause.insure {
        reverse_proxy 127.0.0.1:8080
    }

    caddy validate --config /etc/caddy/Caddyfile
    systemctl reload caddy

Caddy sends `X-Forwarded-For` by default, which is what `CLAUSE_BEHIND_PROXY=1`
in the environment file expects, so the application's rate limiter sees real
callers rather than the proxy.

What you lose by not using the nginx configuration in this directory is its two
rate limit zones, which cap quoting at twenty a minute per address before the
application spends a Monte Carlo on it. The application has its own limiter at
the same boundary, so this is a second line rather than the only one, but it is
worth knowing you are running with one line instead of two. Caddy can do the
same with the `caddy-ratelimit` plugin, which needs a custom build.

### Apache

    <VirtualHost *:443>
        ServerName api.clause.insure
        ProxyPreserveHost On
        ProxyPass        / http://127.0.0.1:8080/
        ProxyPassReverse / http://127.0.0.1:8080/
        RequestHeader set X-Forwarded-Proto "https"
    </VirtualHost>

with `a2enmod proxy proxy_http headers`, and `certbot --apache -d
api.clause.insure` for the certificate.

### A Docker container

Whatever publishes the port is a container you own; either add the domain to
whatever reverse proxy is inside it, or move that container off 80 and let this
installer's nginx take the port. Do not choose the second without knowing what
the container serves.
