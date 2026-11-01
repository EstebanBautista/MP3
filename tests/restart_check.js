"use strict";
// Runs web/static/app.js against a stub page and a fetch whose replies the scenario releases by hand,
// so the order of replies during a restart is exact. Usage: node tests/restart_check.js <scenario>
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const FALSE_ERRORS = /terminó antes|reemplazada|Simulación detenida/;

class Element {
  constructor() {
    this.style = {};
    this.dataset = {};
    this.hidden = false;
    this.textContent = "";
    this.innerHTML = "";
    this.disabled = false;
    this.className = "";
    this.clientWidth = 20;
    this.clientHeight = 20;
    this.text = "";
  }
  get value() { return this.text; }
  set value(next) { this.text = String(next); }  // A real input turns what it gets into a string.
  addEventListener() {}
  append() {}
  focus() {}
  setAttribute() {}
  getBoundingClientRect() { return { left: 0, width: 20 }; }
  getContext() {
    return new Proxy({}, {
      get: (_, key) => (key === "createImageData" ? (w, h) => ({ data: new Uint8ClampedArray(w * h * 4) }) : () => {}),
      set: () => true,
    });
  }
}

function jsonReply(status, value) {
  return {
    ok: status < 400,
    status,
    json: async () => value,
    arrayBuffer: async () => new ArrayBuffer(0),
    headers: { get: () => null },
  };
}

function framesReply(finished) {
  return {
    ok: true,
    status: 200,
    json: async () => ({}),
    arrayBuffer: async () => new ArrayBuffer(0),
    headers: { get: (name) => (name === "X-Finished" ? (finished ? "1" : "0") : null) },
  };
}

function runInfo(id) {
  return { run_id: id, rows: 2, cols: 2, n_gen: 100, seed: null };
}

function flush() {
  return new Promise((resolve) => setImmediate(resolve));
}

class Page {
  constructor() {
    const elements = new Map();
    this.calls = [];
    const fetchStub = (url) => new Promise((resolve, reject) => {
      this.calls.push({ url, resolve, reject, done: false });
    });
    const sandbox = {
      document: {
        body: {},
        getElementById: (id) => {
          if (!elements.has(id)) elements.set(id, new Element());
          return elements.get(id);
        },
        querySelector: () => ({ value: "case", checked: true }),
        querySelectorAll: () => [],
        createElement: () => new Element(),
        addEventListener() {},
      },
      window: { addEventListener() {}, devicePixelRatio: 1 },
      navigator: { sendBeacon() {} },
      location: { reload() {} },
      performance,
      fetch: fetchStub,
      AbortController,
      ResizeObserver: class { observe() {} },
      requestAnimationFrame() {},
      setInterval: () => 0,
      clearInterval() {},
      getComputedStyle: () => ({ fontFamily: "serif" }),
    };
    this.elements = elements;
    this.context = vm.createContext(sandbox);
    const source = fs.readFileSync(path.join(__dirname, "..", "web", "static", "app.js"), "utf8");
    vm.runInContext(source, this.context);
  }

  eval(code) { return vm.runInContext(code, this.context); }
  pending(prefix) { return this.calls.filter((c) => !c.done && c.url.startsWith(prefix)); }

  frames(id) { return this.pending("/api/frames").filter((c) => c.url.endsWith(`&run=${id}`) && !c.url.includes("count=0")); }

  release(call, reply) {
    call.done = true;
    call.resolve(reply);
    return flush();
  }

  async load() {
    await flush();
    await this.release(this.pending("/api/cases")[0], jsonReply(200, {
      cases: [{ name: "2x2", rows: 2, cols: 2, rabbits: 1, foxes: 1, rocks: 0, gen_proc_rabbits: 1,
                gen_proc_foxes: 1, gen_food_foxes: 1, n_gen: 100 }],
      engine_error: null,
    }));
    this.eval('$("case").value = "2x2"');
  }

  async submit() {
    this.eval("start({ preventDefault() {} })");
    await flush();
  }

  // Leaves run `id` in progress with one frame request waiting for its reply.
  async begin(id) {
    await this.submit();
    await this.release(this.pending("/api/start").pop(), jsonReply(200, runInfo(id)));
    assert.strictEqual(this.eval("run.id"), id);
    return this.frames(id)[0];
  }

  async tick() {
    this.eval("tick(performance.now())");
    await flush();
  }

  state() { return this.eval("state"); }
  banner() { return this.eval('$("error").hidden') ? "" : this.eval('$("error").textContent'); }

  assertHealthy(id) {
    assert.strictEqual(this.state(), "running");
    assert.strictEqual(this.banner(), "", "false error shown");
    assert.doesNotMatch(this.eval('$("status-text").textContent'), FALSE_ERRORS);
    assert.strictEqual(this.eval("run.id"), id);
    assert.strictEqual(this.eval("run.serverDone"), false);
    assert.strictEqual(this.eval("run.abort.signal.aborted"), false, "the run was aborted");
  }
}

const REPLACED = () => jsonReply(409, { error: "Esa simulación ya fue reemplazada." });

const SCENARIOS = {
  async stale_409_while_start_pending(page) {
    const old = await page.begin(1);
    await page.submit();
    await page.release(old, REPLACED());
    await page.tick();
    assert.strictEqual(page.banner(), "");
    assert.strictEqual(page.state(), "running");
    await page.release(page.pending("/api/start")[0], jsonReply(200, runInfo(2)));
    page.assertHealthy(2);
    assert.ok(page.frames(2).length, "the new run asks for frames");
  },

  async stale_409_body_read_after_new_run(page) {
    const old = await page.begin(1);
    let releaseBody;
    const reply = jsonReply(409, {});
    reply.json = () => new Promise((resolve) => { releaseBody = () => resolve({ error: "vieja" }); });
    await page.release(old, reply);
    await page.submit();
    await page.release(page.pending("/api/start")[0], jsonReply(200, runInfo(2)));
    releaseBody();
    await flush();
    page.assertHealthy(2);
  },

  async stale_heartbeat_body_read_after_new_run(page) {
    await page.begin(1);
    page.eval("heartbeat()");
    await flush();
    let releaseBody;
    const reply = jsonReply(409, {});
    reply.json = () => new Promise((resolve) => { releaseBody = () => resolve({ error: "vieja" }); });
    await page.release(page.pending("/api/frames?count=0")[0], reply);
    await page.submit();
    await page.release(page.pending("/api/start")[0], jsonReply(200, runInfo(2)));
    releaseBody();
    await flush();
    page.assertHealthy(2);
  },

  async stale_heartbeat_while_start_pending(page) {
    await page.begin(1);
    page.eval("heartbeat()");
    await flush();
    await page.submit();
    await page.release(page.pending("/api/frames?count=0")[0], REPLACED());
    assert.strictEqual(page.banner(), "");
    assert.strictEqual(page.state(), "running");
    await page.release(page.pending("/api/start")[0], jsonReply(200, runInfo(2)));
    page.assertHealthy(2);
  },

  async stale_finish_while_start_pending(page) {
    const old = await page.begin(1);
    await page.submit();
    await page.release(old, framesReply(true));
    await page.tick();
    assert.strictEqual(page.banner(), "");
    assert.strictEqual(page.state(), "running");
    await page.release(page.pending("/api/start")[0], jsonReply(200, runInfo(2)));
    await page.tick();
    page.assertHealthy(2);
  },

  async new_run_clears_the_banner(page) {
    await page.begin(1);
    await page.submit();
    page.eval('showError("anterior")');
    await page.release(page.pending("/api/start")[0], jsonReply(200, runInfo(2)));
    page.assertHealthy(2);
  },

  async second_submit_waits_for_the_first(page) {
    await page.begin(1);
    await page.submit();
    await page.submit();
    assert.strictEqual(page.pending("/api/start").length, 1);
  },

  async real_failure_is_still_reported(page) {
    const frames = await page.begin(1);
    await page.release(frames, jsonReply(409, { error: "Se detuvo por inactividad." }));
    assert.strictEqual(page.state(), "error");
    assert.strictEqual(page.banner(), "Se detuvo por inactividad.");
  },

  async real_early_finish_is_still_reported(page) {
    const frames = await page.begin(1);
    await page.release(frames, framesReply(true));
    await page.tick();
    assert.strictEqual(page.state(), "error");
    assert.match(page.banner(), /terminó antes/);
  },

  async failure_hidden_by_a_rejected_start_comes_back(page) {
    const frames = await page.begin(1);
    await page.submit();
    await page.release(frames, jsonReply(409, { error: "Se detuvo por inactividad." }));
    await page.release(page.pending("/api/start")[0], jsonReply(400, { error: "Filas no válidas." }));
    assert.strictEqual(page.banner(), "Filas no válidas.");
    assert.strictEqual(page.state(), "running");
    await page.tick();
    await page.release(page.frames(1)[0], jsonReply(409, { error: "Se detuvo por inactividad." }));
    assert.strictEqual(page.state(), "error");
    assert.strictEqual(page.banner(), "Se detuvo por inactividad.");
  },

  async finish_hidden_by_a_rejected_start_comes_back(page) {
    const frames = await page.begin(1);
    await page.submit();
    await page.release(frames, framesReply(true));
    await page.release(page.pending("/api/start")[0], jsonReply(400, { error: "Filas no válidas." }));
    await page.tick();
    await page.release(page.frames(1)[0], framesReply(true));
    await page.tick();
    assert.strictEqual(page.state(), "error");
    assert.match(page.banner(), /terminó antes/);
  },
};

async function main() {
  const scenario = SCENARIOS[process.argv[2]];
  if (!scenario) throw new Error(`Unknown scenario. Known: ${Object.keys(SCENARIOS).join(", ")}`);
  const page = new Page();
  await page.load();
  await scenario(page);
}

main().catch((error) => {
  console.error(error.stack || error);
  process.exit(1);
});
