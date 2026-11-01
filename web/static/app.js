"use strict";

const $ = (id) => document.getElementById(id);

const KIND = { EMPTY: 0, ROCK: 1, RABBIT: 2, FOX: 3 };
const COLORS = { background: "#0F1E1A", grid: "#0F1E1A", empty: "#1A2E26", rock: "#7088A8", rabbit: "#E6D27A", fox: "#DE5A2A" };
const SPEEDS = [1, 2, 5, 10, 20, 50, 100, 200, 500];
const HEADER_BYTES = 16;
const GLYPH_MIN_SCALE = 8;      // From this cell size up, each kind also has its own shape.
const HEARTBEAT_MS = 20000;
const CHART_INTERVAL_MS = 50;
const MAX_REQUEST_BYTES = 16 * 1024 * 1024;
const RANDOM_DEFAULTS = { rows: 100, cols: 100, rabbits: 2000, foxes: 300, rocks: 200, gen_proc_rabbits: 3, gen_proc_foxes: 20, gen_food_foxes: 10, n_gen: 2000 };
const WORLD_INPUTS = ["rows", "cols", "rabbits", "foxes", "rocks"];
const RULE_INPUTS = ["gen_proc_rabbits", "gen_proc_foxes", "gen_food_foxes", "n_gen"];

let cases = [];
let state = "idle";     // idle, running, paused, finished, error
let run = null;
let starting = false;     // A start request is on its way; the server may already have killed the old run.
let speed = 50;
let lastTick = 0;
let heartbeatTimer = 0;
let tiles = null;
let image = null;
let chartDirty = true;
let lastChartDraw = 0;
let hoverGen = null;
let rate = { since: 0, frames: 0, value: null };

// ---------- Setup form ----------

function sourceIsCase() {
  return document.querySelector("input[name=source]:checked").value === "case";
}

function fill(values) {
  for (const key of [...WORLD_INPUTS, ...RULE_INPUTS]) $(key).value = values[key];
}

function caseLabel(name) {
  return name.replace(/_unbal0*(\d+)/, " desbalanceado $1");
}

function defaultSpeed(nGen) {
  return nGen <= 10 ? 2 : nGen <= 100 ? 10 : 50;
}

function syncSource() {
  const isCase = sourceIsCase();
  $("case-field").style.display = isCase ? "" : "none";
  $("seed").disabled = isCase;
  $("reroll").disabled = isCase;
  $("seed").placeholder = isCase ? "No aplica en un caso" : "";
  for (const key of WORLD_INPUTS) $(key).disabled = isCase;
  $("world-note").style.display = isCase ? "" : "none";
  if (isCase) {
    $("seed").value = "";
    applyCase();
  } else {
    fill(RANDOM_DEFAULTS);
    rollSeed();
  }
}

function applyCase() {
  const chosen = cases.find((c) => c.name === $("case").value);
  if (!chosen) return;
  fill(chosen);
  if (state !== "running" && state !== "paused") setSpeed(defaultSpeed(chosen.n_gen));
}

function rollSeed() {
  $("seed").value = 1 + Math.floor(Math.random() * 999999);
}

function numberFrom(id) {
  const text = $(id).value.trim();
  return text === "" ? null : Number(text);
}

function startRequest() {
  if (sourceIsCase()) {
    const body = { case: $("case").value };
    for (const key of RULE_INPUTS) body[key] = numberFrom(key);
    return body;
  }
  const generator = { seed: numberFrom("seed") };
  for (const key of [...WORLD_INPUTS, ...RULE_INPUTS]) generator[key] = numberFrom(key);
  return { generator };
}

function showError(message) {
  $("error").textContent = message;
  $("error").hidden = !message;
}

async function start(event) {
  event.preventDefault();
  if (starting) return;
  starting = true;
  showError("");
  let reply, body;
  try {
    reply = await fetch("/api/start", { method: "POST", body: JSON.stringify(startRequest()) });
    body = await reply.json();
  } catch {
    showError("No se puede conectar con el servidor. Comprueba que web/server.py siga en marcha.");
    return;
  } finally {
    starting = false;
  }
  if (!reply.ok) {
    showError(body.error);  // A rejected start leaves the current run as it was.
    return;
  }
  beginRun(body);
}

// ---------- Run state ----------

function beginRun(info) {
  if (run) run.abort.abort();
  showError("");
  run = {
    id: info.run_id,
    rows: info.rows,
    cols: info.cols,
    nGen: info.n_gen,
    frameSize: HEADER_BYTES + info.rows * info.cols,
    queue: [],
    queueHead: 0,
    fetching: false,
    serverDone: false,
    abort: new AbortController(),
    rabbits: new Int32Array(info.n_gen + 1),
    foxes: new Int32Array(info.n_gen + 1),
    gen: -1,
    grid: null,
    budget: 1,
    peak: 1,
  };
  if (info.seed !== null) $("seed").value = info.seed;
  $("world-label").textContent = info.seed !== null
    ? `Mundo aleatorio de ${info.rows}x${info.cols}, semilla ${info.seed}`
    : `Caso ${caseLabel($("case").value)}`;
  $("gen").textContent = "0";
  $("gen-total").textContent = `de ${info.n_gen}`;
  $("start").textContent = "Reiniciar";
  $("invite").hidden = true;
  $("chart-empty").hidden = true;
  layoutGrid();
  hoverGen = null;
  chartDirty = true;
  rate = { since: performance.now(), frames: 0, value: null };
  setState("running");
  clearInterval(heartbeatTimer);
  heartbeatTimer = setInterval(heartbeat, HEARTBEAT_MS);
  $("pause").focus();  // Space now pauses instead of restarting.
  lastTick = performance.now();
  pump();
}

function setState(next, message) {
  state = next;
  const status = $("status");
  status.dataset.state = next;
  const texts = {
    idle: "Sin iniciar",
    running: "En curso",
    paused: "En pausa",
    finished: run ? `Terminada en la generación ${run.gen}` : "Terminada",
    error: message || "Error",
  };
  $("status-text").textContent = texts[next];
  const canToggle = next === "running" || next === "paused";
  $("pause").disabled = !canToggle;
  $("pause-text").textContent = next === "paused" ? "Reanudar" : "Pausa";
  $("pause-icon").className = next === "paused" ? "icon play" : "icon";
  if (!canToggle) clearInterval(heartbeatTimer);
  syncSpeedLabel();
}

function togglePause() {
  if (state === "running") {
    setState("paused");
  } else if (state === "paused") {
    lastTick = performance.now();
    rate = { since: lastTick, frames: 0, value: null };
    setState("running");
    pump();
  }
}

function setSpeed(value) {
  speed = value;
  const index = SPEEDS.indexOf(speed);
  $("slower").disabled = index === 0;
  $("faster").disabled = index === SPEEDS.length - 1;
  $("speed-value").textContent = speed;
  if (run) run.budget = Math.min(run.budget, 1);
  rate = { since: performance.now(), frames: 0, value: null };
  syncSpeedLabel();
}

function stepSpeed(direction) {
  const next = SPEEDS[SPEEDS.indexOf(speed) + direction];
  if (next) setSpeed(next);
}

function syncSpeedLabel() {
  const show = state === "running" && rate.value !== null && Math.abs(rate.value - speed) > speed * 0.15;
  $("speed-real").textContent = show ? `real ${Math.round(rate.value)}` : "";
}

// ---------- Talking to the engine ----------

function failRun(message) {
  if (run) run.abort.abort();
  showError(message);
  setState("error", "Simulación detenida");
}

// While a start is pending, a failure may only be the restart killing the old run. If the start is
// rejected the run goes on, so the next request reports any real failure again.
function failRunIfCurrent(owner, message) {
  if (owner === run && !starting) failRun(message);
}

async function replyError(reply) {
  try {
    return (await reply.json()).error;
  } catch {
    return `El servidor respondió con el código ${reply.status}.`;
  }
}

async function pump() {
  const current = run;
  if (!current || starting || state !== "running" || current.fetching || current.serverDone) return;
  const wanted = Math.max(1, Math.min(Math.ceil(speed * 0.4), Math.floor(MAX_REQUEST_BYTES / current.frameSize)));
  const missing = wanted - (current.queue.length - current.queueHead);
  if (missing < Math.ceil(wanted / 2)) return;

  current.fetching = true;
  try {
    const reply = await fetch(`/api/frames?count=${missing}&run=${current.id}`, { signal: current.abort.signal });
    if (current !== run) return;
    if (!reply.ok) {
      failRunIfCurrent(current, await replyError(reply));
      return;
    }
    const buffer = await reply.arrayBuffer();
    if (current !== run) return;
    for (let at = 0; at + current.frameSize <= buffer.byteLength; at += current.frameSize) {
      current.queue.push({ buffer, at });
    }
    if (!starting) current.serverDone = reply.headers.get("X-Finished") === "1";
  } catch (error) {
    if (error.name !== "AbortError") {
      failRunIfCurrent(current, "Se perdió la conexión con el servidor. Comprueba que web/server.py siga en marcha.");
    }
    return;
  } finally {
    current.fetching = false;
  }
  pump();
}

async function heartbeat() {
  // A paused page reads no frames; this tells the server that it is still open.
  const current = run;
  if (!current || (state !== "running" && state !== "paused")) return;
  try {
    const reply = await fetch(`/api/frames?count=0&run=${current.id}`);
    if (!reply.ok && (state === "running" || state === "paused")) {
      const message = await replyError(reply);
      if (state === "running" || state === "paused") failRunIfCurrent(current, message);
    }
  } catch {
    // The next frame request reports a lost connection.
  }
}

// ---------- Main loop ----------

function consume(now) {
  const elapsed = (now - lastTick) / 1000;
  lastTick = now;
  run.budget = Math.min(run.budget + elapsed * speed, Math.max(1, speed * 0.25));
  let latest = null;
  let consumed = 0;
  while (run.budget >= 1 && run.queueHead < run.queue.length) {
    latest = run.queue[run.queueHead++];
    run.budget -= 1;
    consumed += 1;
    const view = new DataView(latest.buffer, latest.at, HEADER_BYTES);
    const gen = view.getInt32(0, true);
    run.gen = gen;
    run.rabbits[gen] = view.getInt32(4, true);
    run.foxes[gen] = view.getInt32(8, true);
    run.peak = Math.max(run.peak, run.rabbits[gen], run.foxes[gen]);
    latest.rocks = view.getInt32(12, true);
  }
  if (run.queueHead > 512) {
    run.queue = run.queue.slice(run.queueHead);
    run.queueHead = 0;
  }
  if (consumed === 0) {
    if (!starting && run.serverDone && run.queueHead >= run.queue.length && run.gen < run.nGen) {
      failRun("El motor terminó antes de la última generación.");
    }
    return;
  }

  rate.frames += consumed;
  if (now - rate.since > 1000) {
    rate.value = rate.frames * 1000 / (now - rate.since);
    rate.since = now;
    rate.frames = 0;
    syncSpeedLabel();
  }
  run.grid = new Uint8Array(latest.buffer, latest.at + HEADER_BYTES, run.rows * run.cols);
  paintGrid();
  showReadings(latest.rocks);
  chartDirty = true;
  if (run.gen === run.nGen) setState("finished");
}

function showReadings(rocks) {
  const gen = run.gen;
  $("gen").textContent = gen;
  $("count-rabbits").textContent = run.rabbits[gen];
  $("count-foxes").textContent = run.foxes[gen];
  $("count-rocks").textContent = rocks;
  const percent = run.nGen ? (gen / run.nGen) * 100 : 100;
  $("bar").style.width = `${percent}%`;
  $("track").setAttribute("aria-valuenow", Math.round(percent));
}

function tick(now) {
  if (run && state === "running") {
    consume(now);
    pump();
  } else {
    lastTick = now;
  }
  if (chartDirty && now - lastChartDraw >= CHART_INTERVAL_MS) {
    lastChartDraw = now;
    chartDirty = false;
    drawChart();
  }
  requestAnimationFrame(tick);
}

// ---------- World canvas: ImageData with an integer scale, so each cell is exact pixels ----------

function packColor(hex) {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function toPixel([r, g, b]) {
  return (255 << 24 | b << 16 | g << 8 | r) >>> 0;
}

function shapeCoverage(kind, x, y) {
  // x and y run from 0 to 1 inside the cell.
  const margin = 0.1;
  if (kind === KIND.RABBIT) return Math.hypot(x - 0.5, y - 0.5) <= 0.5 - margin;
  if (kind === KIND.FOX) {
    const top = margin, bottom = 1 - margin;
    if (y < top || y > bottom) return false;
    return Math.abs(x - 0.5) <= ((y - top) / (bottom - top)) * (0.5 - margin * 0.6);
  }
  return x >= margin && x <= 1 - margin && y >= margin && y <= 1 - margin;
}

function buildTile(scale, hex, kind) {
  const color = packColor(hex);
  const empty = packColor(COLORS.empty);
  const edge = packColor(COLORS.grid);
  const tile = new Uint32Array(scale * scale);
  if (scale < GLYPH_MIN_SCALE) return tile.fill(toPixel(kind === KIND.EMPTY ? empty : color));
  const samples = 4;
  for (let y = 0; y < scale; y++) {
    for (let x = 0; x < scale; x++) {
      if (x === scale - 1 || y === scale - 1) {
        tile[y * scale + x] = toPixel(edge);
        continue;
      }
      let covered = 0;
      if (kind !== KIND.EMPTY) {
        for (let sy = 0; sy < samples; sy++) {
          for (let sx = 0; sx < samples; sx++) {
            if (shapeCoverage(kind, (x + (sx + 0.5) / samples) / scale, (y + (sy + 0.5) / samples) / scale)) covered++;
          }
        }
      }
      const a = covered / (samples * samples);
      tile[y * scale + x] = toPixel(empty.map((v, i) => Math.round(v + (color[i] - v) * a)));
    }
  }
  return tile;
}

function layoutGrid() {
  const box = $("window");
  const dpr = window.devicePixelRatio || 1;
  const width = Math.floor(box.clientWidth * dpr);
  const height = Math.floor(box.clientHeight * dpr);
  const rows = run ? run.rows : 1;
  const cols = run ? run.cols : 1;
  const scale = Math.max(1, Math.min(Math.floor(width / cols), Math.floor(height / rows)));
  const canvas = $("grid");
  if (!run) {
    const side = Math.min(width, height);
    canvas.width = canvas.height = side;
    canvas.style.width = canvas.style.height = `${side / dpr}px`;
    const context = canvas.getContext("2d");
    context.fillStyle = COLORS.empty;
    context.fillRect(0, 0, side, side);
    return;
  }
  canvas.width = cols * scale;
  canvas.height = rows * scale;
  canvas.style.width = `${canvas.width / dpr}px`;
  canvas.style.height = `${canvas.height / dpr}px`;
  image = canvas.getContext("2d").createImageData(canvas.width, canvas.height);
  tiles = { scale, pixels: new Uint32Array(image.data.buffer), byKind: [] };
  tiles.byKind[KIND.EMPTY] = buildTile(scale, COLORS.empty, KIND.EMPTY);
  tiles.byKind[KIND.ROCK] = buildTile(scale, COLORS.rock, KIND.ROCK);
  tiles.byKind[KIND.RABBIT] = buildTile(scale, COLORS.rabbit, KIND.RABBIT);
  tiles.byKind[KIND.FOX] = buildTile(scale, COLORS.fox, KIND.FOX);
  paintGrid();
}

function paintGrid() {
  if (!run) return;
  const { scale, pixels, byKind } = tiles;
  const { rows, cols, grid } = run;
  const stride = cols * scale;
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const tile = byKind[grid ? grid[r * cols + c] : KIND.EMPTY];
      let out = r * scale * stride + c * scale;
      let source = 0;
      for (let y = 0; y < scale; y++) {
        for (let x = 0; x < scale; x++) pixels[out + x] = tile[source++];
        out += stride;
      }
    }
  }
  $("grid").getContext("2d").putImageData(image, 0, 0);
}

// ---------- Population chart: one min-max band per pixel column, whatever N_GEN is ----------

function niceCeiling(value) {
  const power = 10 ** Math.floor(Math.log10(Math.max(1, value)));
  for (const step of [1, 1.5, 2, 3, 4, 5, 6, 8, 10]) {
    if (value <= step * power) return step * power;
  }
  return 10 * power;
}

// The axis ends at the current generation, so a long run is readable from its first steps.
function xSpan() {
  return Math.max(1, Math.min(run.nGen, Math.max(run.gen, 50)));
}

// Few generations are a plain line. Many are one column per pixel: a faint min-max band behind the
// mean, which keeps fast oscillations visible without hiding the trend.
function drawSeries(context, series, lastGen, area, yOf, color) {
  const span = xSpan();
  const columns = area.width;
  const line = [];
  context.strokeStyle = context.fillStyle = color;
  if (lastGen < columns) {
    for (let g = 0; g <= lastGen; g++) line.push([area.left + (g / span) * columns, yOf(series[g])]);
  } else {
    const lows = [];
    const highs = [];
    let g = 0;
    for (let column = 0; column < columns && g <= lastGen; column++) {
      const end = Math.min(lastGen, Math.floor(((column + 1) / columns) * span));
      let low = series[g], high = series[g], sum = 0;
      for (let i = g; i <= end; i++) {
        if (series[i] < low) low = series[i];
        if (series[i] > high) high = series[i];
        sum += series[i];
      }
      const x = area.left + column + 0.5;
      lows.push([x, yOf(low)]);
      highs.push([x, yOf(high)]);
      line.push([x, yOf(sum / (end - g + 1))]);
      g = end + 1;
    }
    context.globalAlpha = 0.28;
    context.beginPath();
    highs.forEach(([x, y], i) => (i ? context.lineTo(x, y) : context.moveTo(x, y)));
    lows.reverse().forEach(([x, y]) => context.lineTo(x, y));
    context.closePath();
    context.fill();
    context.globalAlpha = 1;
  }
  context.beginPath();
  line.forEach(([x, y], i) => (i ? context.lineTo(x, y) : context.moveTo(x, y)));
  context.stroke();
}

function drawChart() {
  const canvas = $("chart");
  const box = $("chart-box");
  const dpr = window.devicePixelRatio || 1;
  const width = Math.round(box.clientWidth * dpr);
  const height = Math.round(box.clientHeight * dpr);
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  const context = canvas.getContext("2d");
  context.clearRect(0, 0, width, height);
  context.font = `${Math.round(11 * dpr)}px ${getComputedStyle(document.body).fontFamily}`;
  const inkMuted = "#8AA396";
  const area = { left: Math.round(40 * dpr), top: Math.round(6 * dpr), width: 0, height: 0 };
  area.width = width - area.left - Math.round(8 * dpr);
  area.height = height - area.top - Math.round(20 * dpr);
  if (area.width <= 0 || area.height <= 0) return;

  if (!run) return;
  const ceiling = niceCeiling(run.peak);
  const yOf = (value) => area.top + area.height - (value / ceiling) * area.height;

  context.lineWidth = 1;
  context.strokeStyle = "#2C4539";
  context.fillStyle = inkMuted;
  context.textAlign = "right";
  context.textBaseline = "middle";
  for (const part of [0, 0.5, 1]) {
    if (!Number.isInteger(ceiling * part)) continue;
    const y = Math.round(yOf(ceiling * part)) + 0.5;
    context.beginPath();
    context.moveTo(area.left, y);
    context.lineTo(area.left + area.width, y);
    context.stroke();
    context.fillText(String(ceiling * part), area.left - 6 * dpr, y);
  }

  context.textBaseline = "top";
  context.textAlign = "left";
  const xLabelY = area.top + area.height + 6 * dpr;
  context.fillText("0", area.left, xLabelY);
  context.textAlign = "right";
  context.fillText(String(xSpan()), area.left + area.width, xLabelY);

  if (run.gen < 0) return;
  context.lineJoin = "round";
  context.lineWidth = 1.5 * dpr;
  drawSeries(context, run.foxes, run.gen, area, yOf, COLORS.fox);
  drawSeries(context, run.rabbits, run.gen, area, yOf, COLORS.rabbit);

  if (hoverGen !== null && hoverGen <= run.gen) {
    const x = Math.round(area.left + (hoverGen / xSpan()) * area.width) + 0.5;
    context.lineWidth = 1;
    context.strokeStyle = "#B0C4B9";
    context.beginPath();
    context.moveTo(x, area.top);
    context.lineTo(x, area.top + area.height);
    context.stroke();
  }
}

function hoverChart(event) {
  if (!run || run.gen < 0) return;
  const box = $("chart-box").getBoundingClientRect();
  const left = 40, right = 8;
  const part = (event.clientX - box.left - left) / (box.width - left - right);
  if (part < 0 || part > 1) return leaveChart();
  hoverGen = Math.min(run.gen, Math.round(part * xSpan()));
  $("chart-key").textContent = `Generación ${hoverGen}: ${run.rabbits[hoverGen]} conejos, ${run.foxes[hoverGen]} zorros`;
  chartDirty = true;
}

const CHART_KEY = $("chart-key").innerHTML;

function leaveChart() {
  hoverGen = null;
  $("chart-key").innerHTML = CHART_KEY;
  chartDirty = true;
}

// ---------- Page wiring ----------

function onKey(event) {
  if (event.code !== "Space") return;
  if (event.target.closest("input, select, button, textarea")) return;
  event.preventDefault();
  togglePause();
}

function stopOnLeave() {
  navigator.sendBeacon("/api/stop");
}

async function loadCases() {
  try {
    const reply = await fetch("/api/cases");
    const body = await reply.json();
    cases = body.cases;
    if (body.engine_error) showError(body.engine_error);
  } catch {
    showError("No se puede conectar con el servidor. Comprueba que web/server.py siga en marcha.");
  }
  for (const c of cases) {
    const option = document.createElement("option");
    option.value = c.name;
    option.textContent = caseLabel(c.name);
    $("case").append(option);
  }
  if (cases.length === 0) {
    document.querySelector("input[name=source][value=random]").checked = true;
  } else {
    $("case").value = cases.some((c) => c.name === "100x100") ? "100x100" : cases[0].name;
  }
  syncSource();
}

$("setup").addEventListener("submit", start);
$("case").addEventListener("change", applyCase);
for (const radio of document.querySelectorAll("input[name=source]")) radio.addEventListener("change", syncSource);
$("reroll").addEventListener("click", rollSeed);
$("pause").addEventListener("click", togglePause);
$("slower").addEventListener("click", () => stepSpeed(-1));
$("faster").addEventListener("click", () => stepSpeed(1));
$("chart-box").addEventListener("pointermove", hoverChart);
$("chart-box").addEventListener("pointerleave", leaveChart);
document.addEventListener("keydown", onKey);
window.addEventListener("pagehide", stopOnLeave);
window.addEventListener("pageshow", (event) => { if (event.persisted) location.reload(); });
new ResizeObserver(() => { layoutGrid(); chartDirty = true; }).observe($("window"));
new ResizeObserver(() => { chartDirty = true; }).observe($("chart-box"));

setSpeed(speed);
setState("idle");
loadCases();
requestAnimationFrame(tick);
