"use strict";
// Polls the counter: /api/live every second, the tables and the evidence every 5 seconds.

const $ = (id) => document.getElementById(id);
const MONTHS = ["January", "February", "March", "April", "May", "June", "July",
  "August", "September", "October", "November", "December"];
const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

let tables = null; // last /api/tables
let live = null;   // last /api/live
let modelCard = null;

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else node.setAttribute(k, v);
  }
  for (const c of children) if (c !== null && c !== undefined) node.append(c);
  return node;
}

// sim_time is a naive ISO string; read its parts as written, not through a time zone
function parseSim(iso) {
  const [d, t] = iso.split("T");
  const [y, mo, da] = d.split("-").map(Number);
  const [h, mi] = t.split(":").map(Number);
  return { y, mo, da, h, mi, weekday: WEEKDAYS[new Date(Date.UTC(y, mo - 1, da)).getUTCDay()] };
}
const pad = (n) => String(n).padStart(2, "0");
const hours1 = (h) => h.toFixed(1);
const msText = (ms) => `${ms < 10 ? ms.toFixed(1) : Math.round(ms)} ms`;

function spanText(seconds) {
  const unit = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  if (seconds % 3600 === 0) return unit(seconds / 3600, "hour");
  if (seconds % 60 === 0) return unit(seconds / 60, "minute");
  return unit(Math.round(seconds * 10) / 10, "second");
}

function names(sp) {
  return [el("span", { class: "name" }, sp.english), el("span", { class: "fi" }, sp.finnish)];
}
const fullName = (sp) => `${sp.english} · ${sp.finnish}`;

// A slow board must not leave requests hanging: every fetch gives up after 4 s.
async function getJSON(url) {
  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), 4000);
  try {
    const r = await fetch(url, { cache: "no-store", signal: abort.signal });
    if (!r.ok) throw new Error(`${url}: ${r.status}`);
    return await r.json();
  } finally {
    clearTimeout(timer);
  }
}

// Runs `fn`, then schedules the next run only once it finished, so polls never overlap.
function every(ms, fn) {
  const run = async () => {
    try { await fn(); } finally { setTimeout(run, ms); }
  };
  run();
}

/* ---------- live ---------- */

function renderLive() {
  if (!live) return;
  const t = parseSim(live.sim_time);
  $("clock-day").textContent = `${t.weekday} ${t.da} ${MONTHS[t.mo - 1]} ${t.y}`;
  $("clock-time").textContent = `${pad(t.h)}:${pad(t.mi)}`;
  $("sheet-day").textContent = `${t.da} ${MONTHS[t.mo - 1]}`;
  $("scale-sim").textContent = spanText(live.time_scale);
  $("model-name").textContent = live.detector;
  if (!modelCard || !modelCard.name) $("card-name").textContent = live.detector;
  $("model-ms").textContent = msText(live.detect_ms);
  $("card-ms").textContent = `${msText(live.detect_ms)} per frame`;
  $("unidentified").textContent = `Unidentified in frame: ${live.unidentified}`;
  $("unidentified").hidden = !live.unidentified;
  $("footage-note").textContent = live.footage_note || "";
  $("footage-note").hidden = !live.footage_note;
  const photo = typeof live.photo_every_s === "number";
  $("photo-note").textContent = photo ? `One photo every ${live.photo_every_s} s, as the board's camera would take them.` : "";
  $("photo-note").hidden = !photo;

  renderLatch(live.latch);

  const stopped = $("stopped");
  if (live.error) {
    $("stopped-msg").textContent = `${live.error}.`;
    stopped.hidden = false;
  } else if (!stopped.dataset.lost) {
    stopped.hidden = true;
  }

  if (!tables) return;
  renderTally(t);
}

// Hidden when the program runs without a latch. In sim mode no hardware moves, and the page says so.
// `headline` is decided by the server: the page never calls the latch open or closed when the board did
// not confirm the last command ("not_answering", in neutral ink, never the green open or the red band).
const LATCH_HEADLINES = { off: "", open: "Latch: open", closed: "Latch: closed", not_answering: "Latch: not answering" };

function renderLatch(latch) {
  const block = $("latch");
  const headline = latch.headline in LATCH_HEADLINES ? latch.headline : "off";
  block.hidden = headline === "off";
  block.parentElement.classList.toggle("with-latch", !block.hidden);
  if (block.hidden) return;
  const who = latch.reason_name ? ` · ${latch.reason_name.english} · ${latch.reason_name.finnish} at the feeder` : "";
  $("latch-state").textContent = LATCH_HEADLINES[headline];
  $("latch-who").textContent = headline === "open" ? "" : who;
  block.classList.toggle("closed", headline === "closed");
  block.classList.toggle("not-answering", headline === "not_answering");
  $("latch-sim").hidden = latch.mode !== "sim";
  $("latch-error-msg").textContent = latch.error || "";
  $("latch-error").hidden = !latch.error;
}

// One row per species seen today or in frame now; the rest share one line, so eight species still fit.
function renderTally(t) {
  const today = `${t.y}-${pad(t.mo)}-${pad(t.da)}`;
  const maxOf = (sp) => live.day_max[sp.key] ?? 0;
  const nowOf = (sp) => live.now[sp.key] ?? 0;
  const shown = tables.nameable.filter((sp) => maxOf(sp) > 0 || nowOf(sp) > 0);
  // "watched for" = the species the tables give a column (core, or seen this season), as there a zero is stated too
  const unseen = tables.species.filter((sp) => !shown.some((x) => x.key === sp.key));
  // live.sim_time only moves with recorded detections, so a newer day than the tables' was watched
  const watched = shown.length > 0 || tables.day !== today || tables.hours.length > 0;

  $("tally").replaceChildren(...shown.map((sp) => el("tr", {},
    el("th", { scope: "row" }, el("span", { class: "name" }, sp.english), " ", el("span", { class: "fi" }, sp.finnish)),
    el("td", { class: "num in-frame" }, String(nowOf(sp))),
    el("td", { class: "num max" }, String(maxOf(sp))),
    el("td", { class: "num visits" }, String(live.visits_today[sp.key] ?? 0)))));
  $("tally-table").hidden = shown.length === 0;

  const line = $("unseen");
  if (!watched) {
    line.textContent = "Not watched yet today.";
  } else {
    line.replaceChildren(el("span", { class: "lead" }, "Watched for, none today:"), " ",
      unseen.map(fullName).join(", "));
  }
  line.dataset.unwatched = watched ? "" : "1";
  line.hidden = watched && unseen.length === 0;
}

async function pollLive() {
  try {
    const j = await getJSON("/api/live");
    // an older or partial server may leave fields out: treat them as empty
    j.day_max = j.day_max || {};
    j.visits_today = j.visits_today || {};
    j.footage_note = j.footage_note || null;
    j.photo_every_s = j.photo_every_s || null;
    j.latch = j.latch || { mode: "off", closed: false, reason: null, error: null, reason_name: null, headline: "off" };
    live = j;
    delete $("stopped").dataset.lost;
    renderLive();
  } catch {
    // without the counter the page cannot know that today was not watched
    if ($("unseen").dataset.unwatched) $("unseen").hidden = true;
    const s = $("stopped");
    s.dataset.lost = "1";
    $("stopped-msg").textContent = "This page cannot reach the counter.";
    s.hidden = false;
  }
}

/* ---------- tables ---------- */

function countTable(table, rows, species, firstHeader, currentKey) {
  if (!rows.length) {
    table.replaceChildren(el("caption", {}, "Nothing watched yet."));
    return;
  }
  const head = el("tr", {}, el("th", { scope: "col" }, firstHeader), el("th", { scope: "col" }, "Hours watched"),
    ...species.map((sp) => el("th", { scope: "col", title: fullName(sp) }, ...names(sp))));
  const body = rows.map((r) => el("tr", r.key === currentKey ? { class: "current" } : {},
    el("th", { scope: "row" }, r.label),
    el("td", { class: "watched" }, hours1(r.hours_watched)),
    ...species.map((sp) => {
      const n = r.counts[sp.key] ?? 0;
      return el("td", n ? {} : { class: "zero" }, String(n));
    })));
  table.replaceChildren(el("thead", {}, head), el("tbody", {}, ...body));
}

function renderTables() {
  const t = tables;
  const day = t.day.split("-").map(Number);
  $("today-label").textContent = `${day[2]} ${MONTHS[day[1] - 1]}`;
  $("period-label").textContent = t.period;
  const hourKey = live ? pad(parseSim(live.sim_time).h) : null;
  countTable($("hours"), t.hours, t.species, "Hour", hourKey);
  countTable($("days"), t.days, t.species, "Day", t.day);
  const currentPeriod = t.periods.find((p) => p.label === t.period);
  countTable($("periods"), t.periods, t.species, "Period", currentPeriod && currentPeriod.key);
  // more than four species columns do not fit two tables side by side: stack them at full width
  $("ledger").classList.toggle("wide", t.species.length > 4);

  const watched = t.hours.reduce((s, r) => s + r.hours_watched, 0);
  $("watched-today").textContent = `${hours1(watched)} h`;
  $("can-name").textContent = `This model can name: ${t.nameable.map((s) => s.english).join(", ")}.`;

  const total = t.habitats.reduce((s, h) => s + h.birds, 0);
  $("habitats").replaceChildren(...t.habitats.map((h) => {
    const share = total ? (100 * h.birds) / total : 0;
    return el("li", {},
      el("span", { class: "label" }, h.label),
      el("span", { class: "birds" }, String(h.birds)),
      el("span", { class: "bar", role: "img", "aria-label": `${Math.round(share)} percent` },
        el("span", { style: `width:${share}%` })),
      h.species.length ? el("span", { class: "members" }, h.species.join(", ")) : null);
  }));
  renderLive();
  renderModel(); // species names in the accuracy table come from the tables
}

async function pollTables() {
  try {
    tables = await getJSON("/api/tables");
    renderTables();
  } catch { /* the live poll reports a lost connection */ }
}

/* ---------- evidence ---------- */

let evidenceKey = "";
async function pollEvidence() {
  let rows;
  try { rows = await getJSON("/api/evidence"); } catch { return; }
  // names come from the tables, so redraw once they have arrived
  const key = (tables ? "named|" : "") + rows.map((e) => `${e.url}@${e.ts}`).join("|");
  if (key === evidenceKey) return;
  evidenceKey = key;
  const byKey = Object.fromEntries((tables ? tables.species : []).map((s) => [s.key, s]));
  $("evidence-empty").hidden = rows.length > 0;
  $("photos").replaceChildren(...rows.slice(0, 12).map((e) => {
    const sp = byKey[e.species] || { english: e.species, finnish: "" };
    const t = parseSim(e.ts);
    return el("li", {}, el("figure", {},
      el("img", { src: `${e.url}?v=${encodeURIComponent(e.ts)}`, alt: `${sp.english}, ${e.count} at once`, loading: "lazy" }),
      el("figcaption", {},
        el("span", { class: "what" }, `${e.count} × ${sp.finnish ? fullName(sp) : sp.english}`),
        el("span", { class: "when" },
          `${t.da} ${MONTHS[t.mo - 1].slice(0, 3)}, ${pad(t.h)}:${pad(t.mi)} · confidence ${e.confidence.toFixed(2)}`))));
  }));
}

/* ---------- model card ---------- */

const DASH = "–"; // not measured
const pct = (x) => (x == null ? DASH : `${Math.round(x * 100)}%`);

function sentence(text) {
  const t = text.trim();
  return t.charAt(0).toUpperCase() + t.slice(1) + (/[.!?]$/.test(t) ? "" : ".");
}

async function loadModel() {
  try { modelCard = await getJSON("/api/model"); } catch { return false; }
  renderModel();
  return true;
}

function renderModel() {
  if (!modelCard) return;
  $("card-name").textContent = modelCard.name || (live ? live.detector : DASH);
  const m = modelCard.metrics;
  const line = m ? "Measured on footage the model had not seen." : "Accuracy not yet measured on this footage.";
  $("accuracy-short").textContent = line;
  $("accuracy-long").textContent = line;
  if (modelCard.board_ms != null) {
    $("card-board").textContent = `${msText(modelCard.board_ms)} per frame`;
    $("card-board-row").hidden = false;
  }
  if (modelCard.count_threshold != null) {
    const source = modelCard.threshold_source ? ` ${sentence(modelCard.threshold_source)}` : "";
    $("card-threshold").textContent = `Counted at confidence ≥ ${modelCard.count_threshold.toFixed(2)}.${source}`;
    $("card-threshold").hidden = false;
  }
  if (!m) return;
  $("card-exact").textContent = pct(m.count_exact);
  $("card-exact-row").hidden = false;
  const per = m.per_species || {};
  const keys = Object.keys(per);
  if (!keys.length) return;
  const byKey = Object.fromEntries((tables ? tables.species : []).map((s) => [s.key, s]));
  const table = $("metrics");
  table.replaceChildren(
    el("thead", {}, el("tr", {}, ...["Species", "Precision", "Recall", "Boxes"].map((h) => el("th", { scope: "col" }, h)))),
    el("tbody", {}, ...keys.map((k) => el("tr", {},
      el("th", { scope: "row" }, byKey[k] ? fullName(byKey[k]) : k),
      el("td", {}, pct(per[k].precision)),
      el("td", {}, pct(per[k].recall)),
      el("td", {}, per[k].val_boxes == null ? DASH : String(per[k].val_boxes))))));
  table.hidden = false;
}

/* ---------- feed ---------- */

// The stream may be slow (the board): keep the last frame up, and reconnect if it ends.
function startFeed() {
  const img = $("feed");
  const shown = () => { img.classList.add("on"); $("waiting").hidden = true; };
  img.addEventListener("load", shown);
  // some browsers fire no load event for a multipart stream; a decoded frame has a size
  const check = setInterval(() => { if (img.naturalWidth) { shown(); clearInterval(check); } }, 500);
  img.addEventListener("error", () => setTimeout(() => { img.src = `/stream.mjpg?t=${Date.now()}`; }, 3000));
  img.src = "/stream.mjpg";
}

function start() {
  startFeed();
  every(1000, pollLive);
  every(5000, pollTables);
  every(5000, pollEvidence);
  // the card does not change while the server runs; retry only until it loads
  const model = async () => { if (!(await loadModel())) setTimeout(model, 5000); };
  model();
}
start();
