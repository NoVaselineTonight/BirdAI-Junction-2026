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

// Writes text only when it differs, so a poll that changes nothing leaves the DOM (and screen readers) alone.
function setText(id, text) {
  const node = $(id);
  if (node.textContent !== text) node.textContent = text;
}

function renderLive() {
  if (!live) return;
  const t = parseSim(live.sim_time);
  setText("clock-day", `${t.weekday} ${t.da} ${MONTHS[t.mo - 1]} ${t.y}`);
  setText("clock-time", `${pad(t.h)}:${pad(t.mi)}`);
  setText("sheet-day", `${t.da} ${MONTHS[t.mo - 1]}`);
  setText("scale-sim", spanText(live.time_scale));
  if (!modelCard || !modelCard.name) {
    setText("card-name", live.detector);
    setText("model-name", live.detector);
  }
  setText("model-ms", `${msText(live.detect_ms)} on this machine`);
  setText("card-ms", `${msText(live.detect_ms)} per frame`);
  setText("unidentified-n", String(live.unidentified));
  setText("footage-note", live.footage_note || "");
  $("footage-note").hidden = !live.footage_note;
  const photo = typeof live.photo_every_s === "number";
  setText("photo-note", photo ? `One photo every ${live.photo_every_s} s, as the board's camera would take them.` : "");
  $("photo-note").hidden = !photo || live.two_feeds;
  setText("spec-interval", photo ? `One photo every ${live.photo_every_s} s` : "Photo mode off");
  setText("spec-source", SPEC_SOURCES[live.source]);
  renderFeeds();

  renderLatch(live.latch);

  if (live.error) showStopped(`${live.error}.`);
  else if (!$("stopped").dataset.lost) showStopped(null);

  if (!tables) return;
  renderTally(t);
}

// The red band over the whole first screen; touched only when its text or visibility changes.
function showStopped(message) {
  const band = $("stopped");
  if (message) setText("stopped-msg", message);
  if (band.hidden !== !message) {
    band.hidden = !message;
    layoutBoard(); // the band takes height from the pictures
  }
}

// Below the first screen only, and hidden when the program runs without a latch. In sim mode no hardware
// moves, and the page says so. `headline` is decided by the server: the page never calls the latch open or
// closed when the board did not confirm the last command ("not_answering").
const LATCH_HEADLINES = { off: "", open: "Latch: open", closed: "Latch: closed", not_answering: "Latch: not answering" };

function renderLatch(latch) {
  const block = $("latch");
  const headline = latch && latch.headline in LATCH_HEADLINES ? latch.headline : "off";
  block.hidden = headline === "off";
  if (block.hidden) return;
  const who = latch.reason_name ? `· ${latch.reason_name.english} · ${latch.reason_name.finnish} at the feeder` : "";
  // written only on a change: the line is a polite live region and must not repeat itself every second
  setText("latch-state", LATCH_HEADLINES[headline]);
  setText("latch-who", headline === "open" ? "" : who);
  $("latch-sim").hidden = latch.mode !== "sim";
  setText("latch-error-msg", latch.error || "");
  $("latch-error").hidden = !latch.error;
}

// Every species the model can name, always, so the panel keeps its shape: visits today and most seen at the
// same time today. Most visits first; species with nothing today last (dimmed), in species.toml order.
let tallyRows = [];
let tallyKey = "";
let tallyLayout = "";
function renderTally(t) {
  const today = `${t.y}-${pad(t.mo)}-${pad(t.da)}`;
  const maxOf = (sp) => live.day_max[sp.key] ?? 0;
  const visitsOf = (sp) => live.visits_today[sp.key] ?? 0;
  tallyRows = tables.nameable.map((sp, i) => ({ sp, i, visits: visitsOf(sp), max: maxOf(sp) }))
    .sort((a, b) => b.visits - a.visits || b.max - a.max || a.i - b.i);
  // live.sim_time only moves with recorded detections, so a newer day than the tables' was watched
  const watched = tallyRows.some((r) => r.visits || r.max) || tables.day !== today || tables.hours.length > 0;
  const line = $("unseen");
  setText("unseen", watched ? "" : "Not watched yet today.");
  line.dataset.unwatched = watched ? "" : "1";
  line.hidden = watched;

  // the panel is rebuilt only when a number changed, not on every poll
  const key = JSON.stringify(tallyRows.map((r) => [r.sp.key, r.visits, r.max]));
  if (key === tallyKey) return;
  tallyKey = key;
  tallyLayout = "";
  fitTally();
}

function tallyTable(rows) {
  return el("table", { class: "tally" },
    el("thead", {}, el("tr", {},
      el("th", { scope: "col" }, "Species"),
      el("th", { scope: "col", class: "num" }, "Visits"),
      el("th", { scope: "col", class: "num" }, "Most at once"))),
    el("tbody", {}, ...rows.map((r) => el("tr", r.visits || r.max ? {} : { class: "zero" },
      el("th", { scope: "row", title: fullName(r.sp) }, el("span", { class: "name" }, r.sp.english)),
      el("td", { class: "num visits" }, String(r.visits)),
      el("td", { class: "num max" }, String(r.max))))));
}

// Picks the first layout that fits the box, across and down: two side-by-side lists when the panel is wide,
// one when it is narrow, then tighter rows. Only as a last resort (a 4:3 screen) the two caveat sentences
// under the list give way; the full list itself is never cut. A stacked (phone) page has no fixed box.
function fitTally() {
  const box = $("tally-box");
  if (!tallyRows.length) return;
  const rem = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
  const wide = box.clientWidth >= 30 * rem;
  const layouts = wide
    ? ["2", "2 tight", "1 tight", "2 tight nonote", "1 tight nonote"]
    : ["1", "1 tight", "2 tight", "1 tight nonote", "2 tight nonote"];
  const over = () => box.scrollHeight > box.clientHeight + 1 || box.scrollWidth > box.clientWidth + 1;
  const sizeKey = `${box.clientWidth}x${box.clientHeight}|${tallyKey}`;
  if (tallyLayout === sizeKey) return;
  for (const layout of layouts) {
    const cols = Number(layout[0]);
    const per = Math.ceil(tallyRows.length / cols);
    const groups = Array.from({ length: cols }, (_, c) => tallyRows.slice(c * per, (c + 1) * per));
    box.className = `tally-box cols-${cols}${layout.includes("tight") ? " tight" : ""}`;
    $("stats-note").hidden = layout.includes("nonote");
    box.replaceChildren($("unseen"), ...groups.map(tallyTable));
    if (!over()) break;
  }
  tallyLayout = `${box.clientWidth}x${box.clientHeight}|${tallyKey}`; // hiding the note may have grown the box
}

/* ---------- the first screen's two columns ---------- */

// The left column is as wide as two stacked pictures can be at the height left after their own headings
// (measured, not assumed); the right column takes the rest but never less than it needs. One-feed mode keeps
// the same split, so the stats get the same room in both modes.
const BOARD_MEDIA = window.matchMedia("(min-width: 900px) and (min-height: 560px)");
function layoutBoard() {
  const board = $("board");
  if (!BOARD_MEDIA.matches) {
    board.style.removeProperty("--pic-w");
    return;
  }
  const pictures = $("pictures");
  const aiPane = $("feed").closest(".pane");
  const img = $("feed");
  const ratio = img.naturalWidth && img.naturalHeight ? img.naturalWidth / img.naturalHeight : 16 / 9;
  const rem = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
  const gap = parseFloat(getComputedStyle(pictures).rowGap) || 0;
  const colGap = parseFloat(getComputedStyle(board).columnGap) || 0;
  // on a squarer screen (4:3) the pictures are letterboxed anyway: the stats get half the width there
  const minSide = Math.max(30 * rem, board.clientWidth * (innerWidth / innerHeight < 1.5 ? 0.5 : 0.45));
  for (let pass = 0; pass < 2; pass++) { // headings wrap differently at the new width: measure once more
    const chromeOf = (pane) => pane.offsetHeight - pane.querySelector(".window").offsetHeight;
    const liveShown = !$("live-pane").hidden;
    const chrome = chromeOf(aiPane) + (liveShown ? chromeOf($("live-pane")) : chromeOf(aiPane));
    const padX = aiPane.offsetWidth - aiPane.querySelector(".window").offsetWidth;
    const picH = (pictures.clientHeight - gap - chrome) / 2;
    const most = board.clientWidth - colGap - minSide;
    const width = Math.max(Math.min(picH * ratio + padX, most), board.clientWidth * 0.3);
    board.style.setProperty("--pic-w", `${Math.floor(width)}px`);
  }
}

let fitTimer = 0;
function relayout() {
  clearTimeout(fitTimer);
  fitTimer = setTimeout(() => { layoutBoard(); fitTally(); }, 100);
}
if ("ResizeObserver" in window) {
  new ResizeObserver(relayout).observe($("pictures"));
  new ResizeObserver(() => { clearTimeout(fitTimer); fitTimer = setTimeout(fitTally, 100); }).observe($("tally-box"));
} else {
  window.addEventListener("resize", relayout);
}
$("feed").addEventListener("load", layoutBoard, { once: true }); // the picture's own shape, once known

let failedPolls = 0;
async function pollLive() {
  try {
    const j = await getJSON("/api/live");
    // an older or partial server may leave fields out: treat them as empty
    j.day_max = j.day_max || {};
    j.visits_today = j.visits_today || {};
    j.footage_note = j.footage_note || null;
    j.photo_every_s = j.photo_every_s || null;
    j.source = j.source === "camera" ? "camera" : "recorded";
    j.two_feeds = j.two_feeds === true;
    j.latch = j.latch || { mode: "off", closed: false, reason: null, error: null, reason_name: null, headline: "off" };
    live = j;
    // Watchdog: after a server restart an MJPEG <img> often just stops, with no error event to reconnect on,
    // and Chromium fires `load` only for a stream's first frame, so a stale frame cannot be told from a live
    // one. The first good poll after failed ones therefore restarts every stream.
    if (failedPolls > 0) for (const f of feeds) f.img.src = `${f.url}?t=${Date.now()}`;
    failedPolls = 0;
    delete $("stopped").dataset.lost;
    renderLive();
  } catch {
    // without the counter the page cannot know that today was not watched
    failedPolls += 1;
    if ($("unseen").dataset.unwatched) $("unseen").hidden = true;
    $("stopped").dataset.lost = "1";
    showStopped("This page cannot reach the counter.");
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

// "91 % of 899 frames", then the footage it was measured on; only what the card says
function exactText(m) {
  if (m.count_exact == null) return "not yet measured";
  const frames = typeof m.frames === "number" ? ` of ${m.frames} unseen frames` : " of unseen frames";
  const footage = Array.isArray(m.footage) && m.footage.length ? m.footage.join(", ") : "";
  const out = el("span", {}, `${pct(m.count_exact)}${frames}`);
  if (footage) out.append(el("span", { class: "dd-sub" }, `on ${footage}`));
  return out;
}

async function loadModel() {
  try { modelCard = await getJSON("/api/model"); } catch { return false; }
  renderModel();
  return true;
}

// 2400000 -> "2.4 million", 850000 -> "850 thousand"
function paramsText(n) {
  if (n >= 1e6) return `${Number((n / 1e6).toFixed(1))} million`;
  if (n >= 1e3) return `${Math.round(n / 1e3)} thousand`;
  return String(n);
}

function renderModel() {
  if (!modelCard) return;
  $("card-name").textContent = modelCard.name || (live ? live.detector : DASH);
  $("model-name").textContent = $("card-name").textContent;
  // only what the model's own metadata states (feeder.json via /api/model); the rows stay hidden otherwise
  if (Number.isInteger(modelCard.params) && modelCard.params > 0) {
    $("spec-params").textContent = paramsText(modelCard.params);
    $("spec-params-row").hidden = false;
  }
  if (Number.isInteger(modelCard.imgsz) && modelCard.imgsz > 0) {
    $("spec-imgsz").textContent = `${modelCard.imgsz} × ${modelCard.imgsz} px`;
    $("spec-imgsz-row").hidden = false;
  }
  const m = modelCard.metrics;
  let line = m ? "Measured on footage the model had not seen." : "Accuracy not yet measured on this footage.";
  // `qualified` is false when a student ships although it misses the accuracy bar. The two-stage detector's card
  // is always false too, but it is not "shipping because it counts better", so only a student's card says it.
  if (m && modelCard.kind === "student" && m.qualified === false) line += " Below our accuracy bar; it ships because it counts better than the alternative.";
  $("accuracy-short").textContent = line;
  $("accuracy-long").textContent = line;
  if (modelCard.board_ms != null) {
    $("card-board").textContent = `${msText(modelCard.board_ms)} per frame`;
    $("card-board-row").hidden = false;
    $("spec-board").textContent = `${msText(modelCard.board_ms)} on the board`;
    $("spec-board").hidden = false;
  }
  if (modelCard.count_threshold != null) {
    const source = modelCard.threshold_source ? ` ${sentence(modelCard.threshold_source)}` : "";
    $("card-threshold").textContent = `Counted at confidence ≥ ${modelCard.count_threshold.toFixed(2)}.${source}`;
    $("card-threshold").hidden = false;
    $("spec-threshold").textContent = `Confidence ≥ ${modelCard.count_threshold.toFixed(2)}`;
  }
  if (!m) return;
  $("card-exact").textContent = pct(m.count_exact);
  $("card-exact-row").hidden = false;
  $("spec-exact").replaceChildren(exactText(m));
  const per = m.per_species || {};
  const keys = Object.keys(per);
  if (!keys.length) return;
  const byKey = Object.fromEntries((tables ? tables.nameable : []).map((s) => [s.key, s]));
  const table = $("metrics");
  table.replaceChildren(
    el("thead", {}, el("tr", {}, ...["Species", "Precision", "Recall", "Boxes"].map((h) => el("th", { scope: "col" }, h)))),
    el("tbody", {}, ...keys.map((k) => el("tr", {},
      el("th", { scope: "row" }, byKey[k] ? fullName(byKey[k]) : k.replace(/_/g, " ")),
      el("td", {}, pct(per[k].precision)),
      el("td", {}, pct(per[k].recall)),
      el("td", {}, per[k].val_boxes == null ? DASH : String(per[k].val_boxes))))));
  table.hidden = false;
}

/* ---------- feed ---------- */

// The stream may be slow (the board): keep the last frame up, and reconnect if it ends.
const feeds = []; // started streams, for the watchdog
function startFeed(imgId, waitingId, url) {
  const img = $(imgId);
  feeds.push({ img, url });
  const shown = () => { img.classList.add("on"); $(waitingId).hidden = true; };
  img.addEventListener("load", shown);
  // some browsers fire no load event for a multipart stream; a decoded frame has a size
  const check = setInterval(() => { if (img.naturalWidth) { shown(); clearInterval(check); } }, 500);
  img.addEventListener("error", () => setTimeout(() => { img.src = `${url}?t=${Date.now()}`; }, 3000));
  img.src = url;
}

// Photo mode shows two pictures: the raw live picture, and the photo the model analysed with its boxes.
// The second stream starts only once the server says there is one (/live.mjpg is 404 otherwise).
const SOURCE_LINES = {
  camera: "Live picture from the camera.",
  recorded: "Recorded feeder footage, standing in for the camera.",
};
const LIVE_NOTES = {
  camera: "Live picture from the camera.",
  recorded: "Recorded feeder footage, playing in real time, standing in for the camera.",
};
const SPEC_SOURCES = { camera: "Live camera", recorded: "Recorded feeder footage" };
let liveFeedStarted = false;

function renderFeeds() {
  const two = live.two_feeds;
  setText("source-line", SOURCE_LINES[live.source]);
  $("source-line").hidden = two; // each picture has its own caption then
  if ($("live-pane").hidden === two) {
    $("board").classList.toggle("two", two);
    $("live-pane").hidden = !two;
    layoutBoard();
  }
  $("feed-note").hidden = !two;
  // the footage note sits with the picture that shows the footage: the live one when there are two
  const noteHome = two ? $("live-footage-slot") : $("source-line").parentElement;
  if ($("footage-note").parentElement !== noteHome) noteHome.append($("footage-note"));
  $("feed").alt = two
    ? "The photo the model analysed, with a box around each bird it found"
    : "Live view of the feeder with a box around each bird the model found";
  if (!two) return;
  setText("live-note", LIVE_NOTES[live.source]);
  setText("feed-note", `One photo every ${live.photo_every_s} s, with a box around each bird the model found.`);
  if (!liveFeedStarted) {
    liveFeedStarted = true;
    startFeed("live-feed", "live-waiting", "/live.mjpg");
  }
}

function start() {
  startFeed("feed", "waiting", "/stream.mjpg");
  every(1000, pollLive);
  every(5000, pollTables);
  every(5000, pollEvidence);
  // the card does not change while the server runs; retry only until it loads
  const model = async () => { if (!(await loadModel())) setTimeout(model, 5000); };
  model();
}
start();
