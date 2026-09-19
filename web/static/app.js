/* Clause interface.
 *
 * One module, no build step, no dependencies. Every figure on screen comes from
 * the JSON API, so anything here can be checked against the endpoints directly.
 */

const state = {
  view: "cover",
  catalogue: null,
  peril: "earthquake",
  subject: {},
  quote: null,
  pool: null,
  risk: null,
  chain: null,
  policies: [],
  height: 0,
  seenSettlements: new Set(),
  firstFeed: true,
};

const VIEWS = ["cover", "pool", "chain", "policies", "method"];

// Premiums and payouts settle in a stable unit. Insurance priced in something
// that moves is not insurance.
const SETTLEMENT_ASSET = "USDC";

const PERIL_GLYPH = { earthquake: "▲", drought: "☰", flight_delay: "✈" };
const PERIL_BLURB = {
  earthquake: "pays on magnitude inside a radius",
  drought: "pays as seasonal rainfall falls short",
  flight_delay: "pays on arrival delay and cancellation",
};

/* ------------------------------------------------------------------ dom */

const $ = (id) => document.getElementById(id);
const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
};
const clear = (node) => node.replaceChildren();

/* -------------------------------------------------------------- format */

const money = (value, digits = 0) =>
  `${Number(value || 0).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`;

const compact = (value) => {
  const n = Number(value || 0);
  if (Math.abs(n) >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  if (Math.abs(n) >= 1e3) return `${(n / 1e3).toFixed(1)}k`;
  return money(n);
};

const percent = (value, digits = 2) => `${(Number(value || 0) * 100).toFixed(digits)}%`;

const humanSeconds = (seconds) => {
  const s = Math.max(0, Number(seconds) || 0);
  if (s < 90) return `${s.toFixed(0)}s`;
  if (s < 5400) return `${Math.floor(s / 60)}m`;
  return `${(s / 3600).toFixed(1)}h`;
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "content-type": "application/json", accept: "application/json" },
    ...options,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch (_) { /* not json */ }
    throw new Error(detail);
  }
  return response.json();
}

function toast(title, message, kind = "good") {
  const node = el("div", "toast");
  node.dataset.kind = kind;
  node.append(el("strong", null, title));
  if (message) node.append(el("span", null, message));
  $("toasts").append(node);
  setTimeout(() => node.remove(), 6500);
}

/* --------------------------------------------------------------- theme */

function initTheme() {
  let stored = null;
  try { stored = localStorage.getItem("clause-theme"); } catch (_) { /* blocked */ }
  if (stored === "dark" || stored === "light") {
    document.documentElement.dataset.theme = stored;
  }
  paintThemeLabel();

  $("theme-toggle").addEventListener("click", () => {
    const current = currentTheme();
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("clause-theme", next); } catch (_) { /* blocked */ }
    paintThemeLabel();
  });
}

function currentTheme() {
  const explicit = document.documentElement.dataset.theme;
  if (explicit) return explicit;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function paintThemeLabel() {
  $("theme-label").textContent = currentTheme() === "dark" ? "Light mode" : "Dark mode";
}

/* -------------------------------------------------------------- router */

function navigate() {
  const hash = window.location.hash.replace(/^#\/?/, "");
  const view = VIEWS.includes(hash) ? hash : "cover";
  state.view = view;

  for (const name of VIEWS) $(`view-${name}`).hidden = name !== view;
  for (const link of document.querySelectorAll(".nav-item")) {
    link.classList.toggle("active", link.dataset.view === view);
  }

  if (view === "pool") loadPool();
  if (view === "policies") loadPolicies();
  if (view === "method") renderMethod();
}

/* ------------------------------------------------------------ catalogue */

async function loadCatalogue() {
  state.catalogue = await api("/api/perils");
  renderPerilPicker();
  selectPeril(state.peril);
}

// Ordered by how much the cover asks of the protocol, not alphabetically: the
// earthquake product is the one the capital model exists for.
const PERIL_ORDER = ["earthquake", "drought", "flight_delay"];

function renderPerilPicker() {
  const container = $("peril-picker");
  clear(container);

  const ordered = [...state.catalogue.perils].sort(
    (a, b) => PERIL_ORDER.indexOf(a.key) - PERIL_ORDER.indexOf(b.key)
  );

  for (const peril of ordered) {
    const button = el("button", "peril-option");
    button.type = "button";
    button.dataset.key = peril.key;
    button.setAttribute("aria-pressed", peril.key === state.peril ? "true" : "false");

    button.append(el("span", "peril-glyph", PERIL_GLYPH[peril.key] || "●"));
    const copy = el("div", "peril-copy");
    copy.append(el("strong", null, peril.name.split(",")[0]));
    copy.append(el("span", null, PERIL_BLURB[peril.key] || peril.index));
    button.append(copy);

    button.addEventListener("click", () => selectPeril(peril.key));
    container.append(button);
  }
}

function selectPeril(key) {
  state.peril = key;
  for (const button of document.querySelectorAll(".peril-option")) {
    button.setAttribute("aria-pressed", button.dataset.key === key ? "true" : "false");
  }
  renderSubjectForm();

  const term = $("term-input");
  const limit = $("limit-input");
  if (key === "flight_delay") { term.value = 2; limit.value = 1500; }
  else if (key === "drought") { term.value = 150; limit.value = 80000; }
  else { term.value = 365; limit.value = 100000; }

  $("quote-panel").replaceChildren(
    cardWith(el("div", "empty", "Set the details and price it."))
  );
}

function cardWith(...nodes) {
  const card = el("div", "card");
  card.append(...nodes);
  return card;
}

function field(labelText, control) {
  const wrap = el("div", "field");
  const label = el("label", "label", labelText);
  label.setAttribute("for", control.id);
  wrap.append(label, control);
  return wrap;
}

function select(id, options, value) {
  const node = el("select");
  node.id = id;
  for (const option of options) {
    const opt = el("option", null, option.label);
    opt.value = option.value;
    if (String(option.value) === String(value)) opt.selected = true;
    node.append(opt);
  }
  return node;
}

function renderSubjectForm() {
  const form = $("subject-form");
  clear(form);
  const catalogue = state.catalogue;

  if (state.peril === "earthquake") {
    const places = catalogue.locations.map((place) => ({
      value: place.code,
      label: place.has_fault
        ? `${place.name} — fault at ${place.fault_distance_km} km`
        : `${place.name} — no mapped fault`,
    }));
    const location = select("f-location", places, "IST-KADIKOY");
    const radius = select(
      "f-radius",
      catalogue.radii.map((r) => ({ value: r, label: `${r} km` })),
      50
    );
    form.append(field("Location", location), field("Radius the index covers", radius));
    location.addEventListener("change", loadHazard);
    radius.addEventListener("change", loadHazard);
    loadHazard();
    return;
  }

  if (state.peril === "drought") {
    const stations = catalogue.stations.map((station) => ({
      value: station.code,
      label: `${station.name} — ${station.normal_mm} mm normal, ${station.season}`,
    }));
    const two = el("div", "form-two");
    const distance = el("input");
    distance.type = "number"; distance.id = "f-distance"; distance.min = 0;
    distance.max = 60; distance.step = 1; distance.value = 8;
    const hectares = el("input");
    hectares.type = "number"; hectares.id = "f-hectares"; hectares.min = 1;
    hectares.step = 1; hectares.value = 50;
    two.append(
      field("Field distance from station, km", distance),
      field("Hectares", hectares)
    );
    form.append(field("Weather station", select("f-station", stations, "TR-KONYA")), two);
    return;
  }

  const routes = catalogue.routes.map((route) => ({
    value: route.key,
    label: `${route.carrier} ${route.origin} to ${route.destination} — ${(route.late_rate * 100).toFixed(0)}% late`,
  }));
  const two = el("div", "form-two");
  const number = el("input");
  number.type = "text"; number.id = "f-flight"; number.value = "TK1979";
  const date = el("input");
  date.type = "text"; date.id = "f-date"; date.value = "2026-10-04";
  two.append(field("Flight number", number), field("Departure date", date));
  form.append(field("Route", select("f-route", routes, "TK-IST-LHR")), two);
}

function readSubject() {
  if (state.peril === "earthquake") {
    return {
      location: $("f-location").value,
      radius_km: Number($("f-radius").value),
    };
  }
  if (state.peril === "drought") {
    return {
      station: $("f-station").value,
      distance_km: Number($("f-distance").value),
      hectares: Number($("f-hectares").value),
    };
  }
  return {
    route: $("f-route").value,
    flight_number: $("f-flight").value.trim(),
    departure_date: $("f-date").value.trim(),
  };
}

/* -------------------------------------------------------------- hazard */

async function loadHazard() {
  if (state.peril !== "earthquake") return;
  const subject = readSubject();
  try {
    state.hazard = await api(
      `/api/hazard?location=${encodeURIComponent(subject.location)}&radius_km=${subject.radius_km}`
    );
  } catch (_) {
    state.hazard = null;
  }
}

/* --------------------------------------------------------------- quote */

async function requestQuote() {
  const button = $("quote-btn");
  button.disabled = true;
  button.textContent = "Pricing";

  try {
    const body = {
      peril: state.peril,
      subject: readSubject(),
      limit: Number($("limit-input").value),
      term_days: Number($("term-input").value),
    };
    state.quote = await api("/api/quote", { method: "POST", body: JSON.stringify(body) });
    renderQuote();
  } catch (error) {
    $("quote-panel").replaceChildren(
      cardWith(el("div", "empty", `That did not price: ${error.message}`))
    );
  } finally {
    button.disabled = false;
    button.textContent = "Price it";
  }
}

function renderQuote() {
  const quote = state.quote;
  const panel = $("quote-panel");
  clear(panel);

  const total = quote.premium || 1;
  const parts = [
    ["el", quote.expected_loss, "Expected loss", "the average payout, straight from the peril's own model"],
    ["rl", quote.risk_load, "Risk load", "the cost of the capital this policy makes the pool hold"],
    ["ex", quote.expense_load, "Running cost", "what it costs the protocol to carry the policy"],
  ];

  // -- price
  const priceCard = el("div", "card");
  const head = el("div", "price-head");

  const main = el("div", "price-main");
  main.append(el("span", "label", "Premium"));
  const price = el("div", "price-value", money(quote.premium));
  price.append(el("span", "unit", SETTLEMENT_ASSET));
  main.append(price);
  main.append(
    el("div", "price-sub",
      `${percent(quote.rate_on_line)} of a ${money(quote.limit)} limit over ${quote.term_days} days`)
  );
  head.append(main);

  const verdict = el("div", "verdict", quote.diversification);
  verdict.dataset.kind = quote.diversification;
  head.append(verdict);
  priceCard.append(head);

  const breakdown = el("div", "breakdown");
  const bar = el("div", "bar");
  for (const [cls, value] of parts) {
    const span = el("span", cls);
    span.style.width = `${Math.max(0, (value / total) * 100)}%`;
    bar.append(span);
  }
  breakdown.append(bar);

  const legend = el("div", "legend");
  for (const [cls, value, title, blurb] of parts) {
    const item = el("div", "legend-item");
    item.append(el("span", `legend-swatch ${cls}`));
    const copy = el("div", "legend-copy");
    copy.append(el("strong", null, `${title} · ${money(value)}`));
    copy.append(el("span", null, blurb));
    item.append(copy);
    legend.append(item);
  }
  breakdown.append(legend);
  priceCard.append(breakdown);

  if (quote.notes?.length) {
    const notes = el("div", "notes");
    for (const text of quote.notes) {
      const note = el("div", "note");
      if (/outside this|would not register|large step/.test(text)) note.classList.add("warn");
      note.append(el("span", null, text));
      notes.append(note);
    }
    priceCard.append(notes);
  }

  const buy = el("button", "btn", quote.can_write ? "Buy this cover" : "The pool cannot write this");
  buy.type = "button";
  buy.style.width = "100%";
  buy.disabled = !quote.can_write;
  buy.addEventListener("click", buyPolicy);
  priceCard.append(buy);

  if (!quote.can_write && quote.refusal_reasons?.length) {
    const why = el("div", "notes");
    for (const reason of quote.refusal_reasons) {
      const note = el("div", "note warn");
      note.append(el("span", null, reason));
      why.append(note);
    }
    priceCard.append(why);
  }
  panel.append(priceCard);

  // -- what it pays
  const structure = el("div", "card");
  structure.append(el("h2", null, "What it pays"));
  structure.append(el("p", "card-note", quote.subject_text));
  const list = el("ul", "structure");
  for (const line of quote.structure) list.append(el("li", null, line));
  structure.append(list);

  structure.append(el("h3", null, "The condition, as it goes onchain"));
  structure.append(el("div", "predicate", quote.predicate));
  structure.append(
    el("p", "card-note",
      `Read from ${quote.data_source.publisher}. ${quote.data_source.resolution}. ` +
      quote.data_source.on_missing_data)
  );
  panel.append(structure);

  // -- hazard, when there is one
  if (state.peril === "earthquake" && state.hazard) {
    const hazard = el("div", "card");
    hazard.append(el("h2", null, "The hazard behind the price"));
    hazard.append(
      el("p", "card-note",
        "Background seismicity is spread through the region and scales with the circle. " +
        "The fault is a line in a fixed place: either the circle reaches it or it does not.")
    );
    const wrap = el("div", "table-wrap");
    const table = el("table");
    const thead = el("thead");
    const hrow = el("tr");
    for (const column of ["Magnitude", "Background", "Fault", "Once every"]) {
      hrow.append(el("th", null, column));
    }
    thead.append(hrow);
    table.append(thead);
    const tbody = el("tbody");
    for (const row of state.hazard.rows) {
      const tr = el("tr");
      tr.append(el("td", "strong", `M ${row.magnitude.toFixed(1)}`));
      tr.append(el("td", "mono", row.background_rate ? row.background_rate.toFixed(5) : "—"));
      tr.append(el("td", "mono", row.characteristic_rate ? row.characteristic_rate.toFixed(5) : "—"));
      tr.append(
        el("td", "mono",
          row.return_period_years == null
            ? "beyond this source"
            : `${Math.round(row.return_period_years).toLocaleString()} yr`)
      );
      tbody.append(tr);
    }
    table.append(tbody);
    wrap.append(table);
    hazard.append(wrap);
    if (state.hazard.note) {
      const note = el("div", "note");
      if (/outside this|would not register/.test(state.hazard.note)) note.classList.add("warn");
      note.append(el("span", null, state.hazard.note));
      const notes = el("div", "notes");
      notes.append(note);
      hazard.append(notes);
    }
    panel.append(hazard);
  }

  // -- basis risk, always
  const basis = el("div", "card");
  basis.append(el("h2", null, "Where this cover is weakest"));
  const box = el("div", "basis");
  box.dataset.level = quote.basis_risk_level;
  box.append(el("strong", null, `Basis risk: ${quote.basis_risk_level}. `));
  box.append(document.createTextNode(quote.basis_risk));
  basis.append(box);
  panel.append(basis);
}

async function buyPolicy() {
  try {
    const body = {
      peril: state.peril,
      subject: readSubject(),
      limit: Number($("limit-input").value),
      term_days: Number($("term-input").value),
      holder: "you",
    };
    const result = await api("/api/policies", { method: "POST", body: JSON.stringify(body) });
    toast(
      "Cover bound",
      `${result.policy.policy_id} is registered onchain and waiting on its index.`
    );
    await Promise.all([loadPool(), loadPolicies()]);
    requestQuote();
  } catch (error) {
    toast("The pool refused", error.message, "bad");
  }
}

/* ---------------------------------------------------------------- pool */

async function loadPool() {
  const [pool, risk, ledger] = await Promise.all([
    api("/api/pool"),
    api("/api/pool/risk"),
    api("/api/pool/ledger?limit=40"),
  ]);
  state.pool = pool;
  state.risk = risk;
  renderPool(ledger.items);
}

function renderPool(ledgerItems) {
  const pool = state.pool;
  const risk = state.risk;
  $("nav-pool").textContent = compact(pool.balance);

  const solvency = pool.solvency_ratio;
  const stats = [
    ["Pool capital", `${money(pool.balance)}`, `${SETTLEMENT_ASSET}, put up by capital providers`, "key"],
    ["Free to leave", money(pool.free_capital), "the rest stands behind live policies", null],
    [
      "Solvency ratio",
      solvency == null ? "no book" : `${solvency.toFixed(2)}×`,
      "capital against what the worst half percent of years needs",
      solvency == null ? null : solvency >= 1.5 ? "good" : solvency >= 1 ? "warn" : "bad",
    ],
    ["Limit at risk", money(pool.limit_at_risk), `${pool.open_policies} live policies`, null],
    ["Premiums earned", money(pool.premiums_earned), "net of refunds", null],
    [
      "Underwriting result",
      money(pool.underwriting_result),
      `${money(pool.claims_paid)} paid out so far`,
      pool.underwriting_result >= 0 ? "good" : "bad",
    ],
  ];

  const container = $("pool-stats");
  clear(container);
  for (const [label, value, note, tone] of stats) {
    const card = el("div", "stat");
    if (tone) card.dataset.tone = tone;
    card.append(el("span", "label", label));
    card.append(el("div", "stat-value", value));
    card.append(el("div", "stat-note", note));
    container.append(card);
  }

  // accumulation
  const accumulation = $("accumulation");
  clear(accumulation);
  const entries = Object.entries(risk.accumulation || {});
  const peak = Math.max(...entries.map(([, v]) => v), 1);
  const cap = risk.concentration_cap || 0;
  for (const [name, amount] of entries.slice(0, 10)) {
    const row = el("div", "meter-row");
    row.append(el("span", "meter-label", name));
    const track = el("div", "meter-track");
    const fill = el("div", "meter-fill");
    fill.style.width = `${(amount / peak) * 100}%`;
    if (cap && amount > cap * 0.75) fill.dataset.tone = "warn";
    track.append(fill);
    row.append(track);
    row.append(el("span", "meter-value", money(amount)));
    accumulation.append(row);
  }
  if (!entries.length) accumulation.append(el("div", "empty", "No live exposure."));

  // exceedance
  const exceedance = $("exceedance");
  clear(exceedance);
  const wanted = [2, 5, 10, 25, 50, 100, 200];
  for (const target of wanted) {
    const row = (risk.exceedance_curve || []).reduce((best, item) => {
      if (!best) return item;
      return Math.abs(item.return_period_years - target) <
        Math.abs(best.return_period_years - target) ? item : best;
    }, null);
    if (!row) continue;
    const tr = el("tr");
    tr.append(el("td", "strong", `1 in ${target} years`));
    tr.append(el("td", "mono", money(row.loss)));
    tr.append(el("td", "mono", pool.balance ? percent(row.loss / pool.balance, 1) : "—"));
    exceedance.append(tr);
  }

  // turned away
  const declinedCard = $("declined-card");
  const declined = $("declined");
  clear(declined);
  const refusals = risk.declined || [];
  declinedCard.hidden = refusals.length === 0;
  for (const item of refusals) {
    const note = el("div", "note warn");
    const where = Object.values(item.subject || {}).slice(0, 2).join(", ");
    note.append(el("span", null, `${item.peril.replace("_", " ")} at ${where}: ${item.reason}`));
    declined.append(note);
  }

  // ledger
  const ledger = $("ledger");
  clear(ledger);
  for (const entry of ledgerItems) {
    const tr = el("tr");
    tr.append(el("td", "strong", entry.kind));
    tr.append(el("td", null, entry.account));
    tr.append(el("td", "mono", entry.reference));
    const amount = el("td", "mono", `${entry.amount >= 0 ? "+" : ""}${money(entry.amount)}`);
    amount.style.color = entry.amount >= 0 ? "var(--turquoise)" : "var(--clay)";
    tr.append(amount);
    tr.append(el("td", "mono", money(entry.balance_after)));
    ledger.append(tr);
  }
}

/* --------------------------------------------------------------- chain */

function renderChain(payload) {
  const stats = payload.stats;
  state.height = stats.height;
  $("chain-height").textContent = stats.height.toLocaleString();
  $("nav-chain").textContent = String(stats.armed);

  const container = $("chain-stats");
  clear(container);
  const cards = [
    ["Waiting onchain", String(stats.armed), "predicates the chain holds open", "key"],
    ["Paid by the chain", String(stats.paid), "settled with no claim filed", "good"],
    ["Premiums returned", String(stats.expired), "sources that went quiet", stats.expired ? "warn" : null],
    ["Settlement delay", stats.mean_latency_blocks < 0.5 ? "same block" : `${stats.mean_latency_blocks.toFixed(1)} blk`,
      "from the reading holding to the payout", "good"],
  ];
  for (const [label, value, note, tone] of cards) {
    const card = el("div", "stat");
    if (tone) card.dataset.tone = tone;
    card.append(el("span", "label", label));
    card.append(el("div", "stat-value", value));
    card.append(el("div", "stat-note", note));
    container.append(card);
  }

  // pending
  const pending = $("pending");
  clear(pending);
  for (const item of payload.pending || []) {
    const row = el("li", "pending-item");
    row.dataset.silent = String(item.source_silent);
    const top = el("div", "pending-top");
    top.append(el("strong", null, `${item.peril.replace("_", " ")} · ${money(item.limit)}`));
    top.append(
      el("span", "pending-meta",
        item.current_index == null ? "no reading" : `index ${item.current_index}`)
    );
    row.append(top);
    row.append(el("div", "predicate", item.predicate));
    if (item.source_silent) {
      const note = el("div", "note warn");
      note.style.marginTop = "9px";
      note.append(el("span", null,
        "This source has stopped publishing. When the deadline passes the policy expires and the premium goes back."));
      row.append(note);
    }
    pending.append(row);
  }
  if (!(payload.pending || []).length) {
    pending.append(el("div", "empty", "Nothing waiting. Every policy has settled."));
  }

  // blocks
  const strip = $("blockstrip");
  clear(strip);
  const blocks = (payload.blocks || []).slice(-70);
  const peak = Math.max(...blocks.map((b) => b.transaction_count), 1);
  for (const block of blocks) {
    const bar = el("div", "blockbar");
    bar.style.height = `${Math.max(4, (block.transaction_count / peak) * 100)}%`;
    bar.title = `block ${block.height} · ${block.transaction_count} transactions · ${block.settlements.length} settled`;
    if (block.settlements.length) {
      const lit = el("div", "lit");
      lit.style.height = "55%";
      bar.append(lit);
    }
    strip.append(bar);
  }

  // feed
  const feed = $("feed");
  const items = payload.settlements || [];
  clear(feed);
  for (const item of items) {
    const row = el("div", "feed-item");
    row.append(el("span", "feed-block", `#${item.block_number}`));
    const body = el("div", "feed-body");
    const title = el("strong", null, item.policy_id);
    const pill = el("span", "pill", item.kind);
    pill.dataset.kind = item.kind;
    title.append(pill);
    body.append(title);
    body.append(el("span", null, item.summary));
    row.append(body);
    feed.append(row);

    if (!state.firstFeed && !state.seenSettlements.has(item.signature)) {
      state.seenSettlements.add(item.signature);
      if (item.kind === "paid") {
        toast("The chain paid a policy", item.summary);
      } else if (item.kind === "expired") {
        toast("Premium returned", item.summary, "warn");
      }
    } else {
      state.seenSettlements.add(item.signature);
    }
  }
  state.firstFeed = false;
  if (!items.length) feed.append(el("div", "empty", "Nothing has settled yet."));
}

/* ------------------------------------------------------------ policies */

async function loadPolicies() {
  const data = await api("/api/policies?limit=200");
  state.policies = data.items;
  $("nav-policies").textContent = String(data.count);

  const tbody = $("policies");
  clear(tbody);
  for (const policy of data.items) {
    const tr = el("tr");
    tr.append(el("td", "mono", policy.policy_id));
    tr.append(el("td", "strong", policy.subject_text));
    tr.append(el("td", "mono", money(policy.limit)));
    tr.append(el("td", "mono", money(policy.premium)));
    tr.append(el("td", "mono", percent(policy.premium / policy.limit, 2)));
    const status = el("td");
    const pill = el("span", "pill", policy.status);
    pill.dataset.kind = policy.status;
    status.append(pill);
    tr.append(status);
    tr.append(el("td", null, policy.settlement_note || "waiting on its index"));
    tbody.append(tr);
  }
  if (!data.items.length) {
    const row = el("tr");
    const cell = el("td", "empty", "No policies yet.");
    cell.colSpan = 7;
    row.append(cell);
    tbody.append(row);
  }
}

/* -------------------------------------------------------------- method */

function renderMethod() {
  const body = $("method-body");
  if (body.childElementCount) return;

  const sections = [
    {
      title: "The premium",
      note: "Three parts, and the middle one is the whole argument.",
      lines: [
        "Expected loss comes from the peril's own probability model, not from the simulation, so it is exact rather than sampled.",
        "The risk load is the marginal cost of capital: what the pool must hold with this policy, less what it must hold without it, priced at the pool's cost of capital over the term. A protocol that charges a flat margin prices the fiftieth earthquake policy in one city exactly like the first, and they are not the same risk.",
        "The running cost is a fixed share of expected loss.",
      ],
    },
    {
      title: "How the capital is sized",
      note: "Losses arrive together, so the book is simulated as events rather than as a sum of independent risks.",
      lines: [
        "Twenty thousand states of the world are drawn. Each one settles every live policy at once, so an earthquake pays every policy inside its circle in the same trial and a dry year pays every farm around the station.",
        "Capital is the average loss in the worst half percent of those years, less the expected loss, which premium already funds.",
        "The world is drawn once and cached, and a policy's own randomness comes from a stream seeded by its identifier. Adding a policy therefore cannot disturb any other policy's draws, and the marginal capital figure is the policy rather than simulation noise.",
      ],
    },
    {
      title: "Where the probabilities come from",
      note: "Each peril is modelled the way its own field models it.",
      lines: [
        "Earthquake: Gutenberg and Richter for background seismicity, truncated, plus a separate characteristic rate for the mapped fault. Large events on a fault recur more often than an extrapolation from its small events predicts, and a model without that term puts the return period for a major Istanbul event several times too long.",
        "Drought: seasonal rainfall as a gamma distribution fitted by method of moments from the station's long run mean and variability, which is the standard treatment in agrometeorology.",
        "Flight: a cancellation rate, a late rate, and a lognormal for delay length among late arrivals, pinned by the published median.",
      ],
    },
    {
      title: "What this cover cannot do",
      note: "Stated here rather than left to be discovered.",
      lines: [
        "Parametric cover pays on an index, not on your loss. It can pay when nothing was damaged, and fail to pay when everything was. That gap is basis risk and it is largest for earthquake, where magnitude and distance are a loose proxy for how hard the ground moved at one address.",
        "A drought policy follows the station, not the field. Ten kilometres of separation is enough for a season to differ, and the quote says how much correlation is left at the distance you gave it.",
        "A policy whose source never publishes cannot settle either way. Rather than leave it armed forever, each cover carries a settlement deadline written in at purchase, and reaching it returns the premium in full.",
      ],
    },
  ];

  for (const section of sections) {
    const card = el("div", "card");
    card.append(el("h2", null, section.title));
    card.append(el("p", "card-note", section.note));
    const stack = el("div", "notes");
    for (const line of section.lines) {
      const note = el("div", "note");
      note.append(el("span", null, line));
      stack.append(note);
    }
    card.append(stack);
    body.append(card);
  }
}

/* ------------------------------------------------------------- inject */

/* Events a demonstration can attest. Each one is a reading the simulated world
 * could have produced on its own; nothing downstream is bypassed. */
const INJECTABLE = [
  {
    label: "Magnitude 7.2 on the Marmara fault, inside 50 km of Kadikoy",
    reference: "api.seismic.example/v1/max-magnitude?lat=40.99&lon=29.03&radius_km=50",
    field: "max_magnitude", value: 7.2,
  },
  {
    label: "Magnitude 6.1 within 50 km of Izmir",
    reference: "api.seismic.example/v1/max-magnitude?lat=38.42&lon=27.13&radius_km=50",
    field: "max_magnitude", value: 6.1,
  },
  {
    label: "Magnitude 7.4 on the East Anatolian fault, inside 50 km of Adiyaman",
    reference: "api.seismic.example/v1/max-magnitude?lat=37.76&lon=38.28&radius_km=50",
    field: "max_magnitude", value: 7.4,
  },
  {
    label: "Konya season closes at 44 mm, a little over a third of normal",
    reference: "api.meteo.example/v1/station/TR-KONYA/cumulative",
    field: "rainfall_mm", value: 44, also: { window_closed: 1 },
  },
  {
    label: "Edirne season closes at 96 mm, about half of normal",
    reference: "api.meteo.example/v1/station/TR-EDIRNE/cumulative",
    field: "rainfall_mm", value: 96, also: { window_closed: 1 },
  },
];

function setupInject() {
  const picker = $("inject-pick");
  if (!picker) return;
  clear(picker);
  INJECTABLE.forEach((item, index) => {
    const option = el("option", null, item.label);
    option.value = String(index);
    picker.append(option);
  });

  $("inject-btn").addEventListener("click", async () => {
    const item = INJECTABLE[Number(picker.value)];
    const button = $("inject-btn");
    button.disabled = true;
    try {
      // The window has to close before a seasonal reading means anything, so
      // that field is attested first and the index second.
      for (const [field, value] of Object.entries(item.also || {})) {
        await api(
          `/api/chain/inject?reference=${encodeURIComponent(item.reference)}` +
          `&field=${encodeURIComponent(field)}&value=${value}&final=false`,
          { method: "POST" }
        );
      }
      await api(
        `/api/chain/inject?reference=${encodeURIComponent(item.reference)}` +
        `&field=${encodeURIComponent(item.field)}&value=${item.value}&final=true`,
        { method: "POST" }
      );
      toast("Attested", `${item.label}. Watch what the chain does with it.`);
    } catch (error) {
      toast("Could not attest", error.message, "bad");
    } finally {
      button.disabled = false;
    }
  });
}

/* ---------------------------------------------------------------- live */

function connectStream() {
  const source = new EventSource("/api/stream");
  source.addEventListener("tick", (event) => {
    const payload = JSON.parse(event.data);
    state.chain = payload;
    $("chain-height").textContent = payload.stats.height.toLocaleString();
    $("nav-chain").textContent = String(payload.stats.armed);
    if (state.view === "chain") renderChain(payload);
  });
  source.addEventListener("pool", (event) => {
    const payload = JSON.parse(event.data);
    state.pool = payload.pool;
    state.risk = payload.risk;
    $("nav-pool").textContent = compact(payload.pool.balance);
    if (state.view === "pool") loadPool();
  });
}

/* ----------------------------------------------------------------- boot */

async function boot() {
  initTheme();
  setupInject();
  $("quote-btn").addEventListener("click", requestQuote);
  window.addEventListener("hashchange", navigate);

  try {
    await loadCatalogue();
    await Promise.all([loadPool(), loadPolicies()]);
    const chain = await api("/api/chain");
    state.chain = chain;
    renderChain(chain);
  } catch (error) {
    toast("Could not reach the protocol", error.message, "bad");
  }

  navigate();
  connectStream();
}

boot();
