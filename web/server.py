"""Local web interface for the ecosystem engine. Standard library only, loopback only.

The engine streams frames through a pipe and blocks when nobody reads them, so a paused page holds
no growing memory: frames are computed only as fast as the page asks for them.
"""
import argparse
import atexit
import json
import os
import random
import signal
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.worldgen import generate_world  # noqa: E402

HOST = "127.0.0.1"
STATIC_DIR = os.path.join(ROOT, "web", "static")
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}
EXAMPLES_DIR = os.path.join(ROOT, "ecosystem_examples")
DEFAULT_ENGINE = os.path.join(ROOT, "build", "eco_seq" + (".exe" if os.name == "nt" else ""))
BUILD_HINT = "powershell -ExecutionPolicy Bypass -File scripts/build.ps1"

FRAME_HEADER_SIZE = 16
MAX_FRAMES_BYTES = 32 * 1024 * 1024
MAX_BODY_BYTES = 64 * 1024
DEFAULT_IDLE_TIMEOUT = 120.0  # A paused page sends a heartbeat, so only a vanished one gets here.
MAX_SIDE = 500
LIMITS = {
    "rows": ("Filas", 1, MAX_SIDE),
    "cols": ("Columnas", 1, MAX_SIDE),
    "rabbits": ("Conejos", 0, MAX_SIDE * MAX_SIDE),
    "foxes": ("Zorros", 0, MAX_SIDE * MAX_SIDE),
    "rocks": ("Rocas", 0, MAX_SIDE * MAX_SIDE),
    "gen_proc_rabbits": ("GEN_PROC_RABBITS", 1, 1000),
    "gen_proc_foxes": ("GEN_PROC_FOXES", 1, 1000),
    "gen_food_foxes": ("GEN_FOOD_FOXES", 1, 1000),
    "n_gen": ("N_GEN", 0, 100000),
}
RULE_KEYS = ("gen_proc_rabbits", "gen_proc_foxes", "gen_food_foxes")


class BadRequest(Exception):
    """The request is wrong; the message is shown to the user."""


class EngineMissing(Exception):
    """The engine binary is not there; the message is shown to the user."""


def checked_int(payload, key):
    label, low, high = LIMITS[key]
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise BadRequest(f"{label} debe ser un número entero.")
    if not low <= value <= high:
        raise BadRequest(f"{label} debe estar entre {low} y {high}.")
    return value


def world_parameters(text):
    """Parses the header and counts the objects of an engine input."""
    lines = text.splitlines()
    head = [int(field) for field in lines[0].split()]
    kinds = [line.split()[0] for line in lines[1:] if line.strip()]
    return {
        "gen_proc_rabbits": head[0], "gen_proc_foxes": head[1], "gen_food_foxes": head[2],
        "n_gen": head[3], "rows": head[4], "cols": head[5],
        "rabbits": kinds.count("RABBIT"), "foxes": kinds.count("FOX"), "rocks": kinds.count("ROCK"),
    }


def list_cases():
    """The input files are the whitelist: a case name never reaches the file system unchecked."""
    if not os.path.isdir(EXAMPLES_DIR):
        return {}
    cases = {}
    for entry in os.listdir(EXAMPLES_DIR):
        path = os.path.join(EXAMPLES_DIR, entry)
        if entry.startswith("input") and os.path.isfile(path):
            cases[entry[len("input"):]] = path
    return cases


def read_case(path):
    with open(path, encoding="ascii", newline="") as f:
        return f.read().replace("\r\n", "\n")


def world_from_case(payload):
    name = payload["case"]
    cases = list_cases()
    if not isinstance(name, str) or name not in cases:
        raise BadRequest("Ese caso de prueba no existe.")
    text = read_case(cases[name])
    params = world_parameters(text)
    overrides = {key: checked_int(payload, key) for key in (*RULE_KEYS, "n_gen") if key in payload}
    if overrides:
        params.update(overrides)
        head, rest = text.split("\n", 1)
        fields = head.split()
        fields[:4] = [str(params[key]) for key in (*RULE_KEYS, "n_gen")]
        text = " ".join(fields) + "\n" + rest
    return text, params, None


def world_from_generator(payload):
    if not isinstance(payload, dict):
        raise BadRequest("Los datos del mundo aleatorio no son válidos.")
    params = {key: checked_int(payload, key) for key in LIMITS}
    total = params["rabbits"] + params["foxes"] + params["rocks"]
    cells = params["rows"] * params["cols"]
    if total > cells:
        raise BadRequest(f"Hay {total} objetos y solo {cells} celdas. Reduce las poblaciones o agranda la grilla.")
    seed = payload.get("seed")
    if seed is None:
        seed = random.randrange(1, 1_000_000)
    elif not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise BadRequest("La semilla debe ser un número entero positivo.")
    return generate_world(seed=seed, **params), params, seed


class Run:
    """One engine process and what is needed to read its frames."""

    def __init__(self, run_id, proc, stderr, params, seed):
        self.id = run_id
        self.proc = proc
        self.stderr = stderr
        self.params = params
        self.seed = seed
        self.frame_size = FRAME_HEADER_SIZE + params["rows"] * params["cols"]
        self.read_lock = threading.Lock()
        self.closed = False
        self.at_end = False


class KillOnExitJob:
    """A Windows job that ends its processes when the server dies, even by TerminateProcess.

    An orphan could not otherwise be stopped: on Windows the engine ignores the broken pipe and
    keeps simulating until N_GEN. On POSIX, SIGPIPE already kills it at its next write.
    """

    def __init__(self):
        self.handle = None
        if os.name != "nt":
            return
        import ctypes
        from ctypes import wintypes

        class Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class Extended(ctypes.Structure):
            _fields_ = [("Basic", Basic), ("IoCounters", ctypes.c_ulonglong * 6),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self._assign = kernel32.AssignProcessToJobObject

        job_object_extended_limit_information = 9
        job_object_limit_kill_on_job_close = 0x2000
        info = Extended()
        info.Basic.LimitFlags = job_object_limit_kill_on_job_close
        self.handle = kernel32.CreateJobObjectW(None, None)
        if not self.handle or not kernel32.SetInformationJobObject(
                self.handle, job_object_extended_limit_information, ctypes.byref(info), ctypes.sizeof(info)):
            raise ctypes.WinError(ctypes.get_last_error())

    def add(self, proc):
        if self.handle:
            self._assign(self.handle, int(proc._handle))


class Simulation:
    """Owns at most one engine process."""

    def __init__(self, engine, idle_timeout):
        self.engine = engine
        self.idle_timeout = idle_timeout
        self.job = KillOnExitJob()
        self.lock = threading.RLock()
        self.run = None
        self.next_id = 1
        self.last_seen = time.monotonic()
        self.stop_reason = None
        threading.Thread(target=self._watch_idle, daemon=True).start()

    def engine_error(self):
        if os.path.isfile(self.engine):
            return None
        return (f"No se encontró el motor de simulación ({os.path.relpath(self.engine, ROOT)}). "
                f"Compílalo con: {BUILD_HINT}")

    def start(self, text, params, seed):
        error = self.engine_error()
        if error:
            raise EngineMissing(error)
        with self.lock:
            self.stop()
            stderr = tempfile.TemporaryFile()  # A file cannot fill up and block the engine.
            proc = subprocess.Popen([self.engine, "--frames"], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=stderr)
            self.job.add(proc)
            try:
                proc.stdin.write(text.encode("ascii"))
                proc.stdin.close()
            except OSError:
                pass  # The engine already exited: reading its frames reports the reason.
            self.run = Run(self.next_id, proc, stderr, params, seed)
            self.next_id += 1
            self.last_seen = time.monotonic()
            self.stop_reason = None
            return self.run

    def stop(self, reason=None):
        with self.lock:
            run, self.run = self.run, None
            self.stop_reason = reason
        if run is None:
            return
        run.proc.kill()  # Any reader now sees end of file, so taking its lock cannot hang.
        run.proc.wait()
        with run.read_lock:
            run.closed = True
            run.proc.stdout.close()
            run.stderr.close()

    def touch(self):
        self.last_seen = time.monotonic()

    def current(self):
        with self.lock:
            return self.run

    def read_frames(self, run, count):
        """Returns (bytes, finished). Blocks until the engine has produced the frames."""
        count = min(count, max(1, MAX_FRAMES_BYTES // run.frame_size))
        chunks = []
        with run.read_lock:
            if run.closed:
                return b"", True
            for _ in range(count):
                if run.at_end:
                    break
                frame = run.proc.stdout.read(run.frame_size)
                if len(frame) == run.frame_size:
                    chunks.append(frame)
                else:
                    run.at_end = True
            finished = run.at_end
            # Plain attribute read: start() can hold self.lock while it waits for read_lock.
            if finished and self.run is run and run.proc.wait() != 0:
                run.stderr.seek(0)
                detail = run.stderr.read(2000).decode("utf-8", "replace").strip()
                raise RuntimeError(f"El motor terminó con un error: {detail or run.proc.returncode}")
        self.touch()
        return b"".join(chunks), finished

    def _watch_idle(self):
        while True:
            time.sleep(min(1.0, self.idle_timeout / 4))
            with self.lock:
                run = self.run
                idle = time.monotonic() - self.last_seen > self.idle_timeout
            if run is not None and idle and run.proc.poll() is None and not run.read_lock.locked():
                self.stop("La simulación se detuvo por inactividad de la página. Pulsa Iniciar para correrla de nuevo.")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "EcoSim"
    sim = None  # Set in main().

    def log_message(self, format, *args):
        pass

    def send_bytes(self, status, data, content_type, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, status, value):
        self.send_bytes(status, json.dumps(value).encode("utf-8"), "application/json; charset=utf-8")

    def send_error_json(self, status, message):
        self.send_json(status, {"error": message})

    def read_body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if not 0 <= length <= MAX_BODY_BYTES:
            self.close_connection = True
            raise BadRequest("La petición no tiene un tamaño válido.")
        return self.rfile.read(length)

    def host_allowed(self):
        """Stops other sites from reaching this server through DNS rebinding."""
        port = self.server.server_address[1]
        return self.headers.get("Host") in (f"{HOST}:{port}", f"localhost:{port}")

    def dispatch(self, routes):
        if not self.host_allowed():
            self.send_error_json(403, "Solo se admiten peticiones locales.")
            return
        path = urlsplit(self.path).path
        route = routes.get(path)
        try:
            if route is None:
                self.send_error_json(404, "No existe esa ruta.")
            else:
                route(self)
        except (BrokenPipeError, ConnectionError):
            self.close_connection = True  # The page went away or aborted the request.
        except BadRequest as error:
            self.send_error_json(400, str(error))
        except EngineMissing as error:
            self.send_error_json(503, str(error))
        except (RuntimeError, OSError) as error:
            self.send_error_json(500, str(error))

    def do_GET(self):
        routes = {"/api/cases": Handler.get_cases, "/api/frames": Handler.get_frames}
        routes.update({path: Handler.get_static for path in STATIC_FILES})
        self.dispatch(routes)

    def do_POST(self):
        self.dispatch({"/api/start": Handler.post_start, "/api/stop": Handler.post_stop})

    def get_static(self):
        name, content_type = STATIC_FILES[urlsplit(self.path).path]
        with open(os.path.join(STATIC_DIR, name), "rb") as f:
            self.send_bytes(200, f.read(), content_type)

    def get_cases(self):
        cases = []
        for name, path in list_cases().items():
            cases.append({"name": name, **world_parameters(read_case(path))})
        cases.sort(key=lambda c: (c["rows"] * c["cols"], c["name"]))
        self.send_json(200, {"cases": cases, "engine_error": self.sim.engine_error()})

    def get_frames(self):
        query = parse_qs(urlsplit(self.path).query)
        try:
            count = int(query.get("count", ["1"])[0])
        except ValueError:
            count = -1
        if count < 0:
            raise BadRequest("count debe ser un número entero no negativo.")
        self.sim.touch()
        run = self.sim.current()
        if run is None:
            self.send_error_json(409, self.sim.stop_reason or "No hay ninguna simulación en curso.")
            return
        if query.get("run", [str(run.id)])[0] != str(run.id):
            self.send_error_json(409, "Esa simulación ya fue reemplazada.")  # Never lose frames of the new run.
            return
        data, finished = self.sim.read_frames(run, count) if count else (b"", run.at_end)
        self.send_bytes(200, data, "application/octet-stream",
                        {"X-Finished": "1" if finished else "0", "X-Run-Id": str(run.id)})

    def post_start(self):
        try:
            payload = json.loads(self.read_body() or b"null")
        except ValueError:
            raise BadRequest("El cuerpo de la petición no es JSON válido.") from None
        if isinstance(payload, dict) and "case" in payload:
            world = world_from_case(payload)
        elif isinstance(payload, dict) and "generator" in payload:
            world = world_from_generator(payload["generator"])
        else:
            raise BadRequest("Indica un caso de prueba o un mundo aleatorio.")
        run = self.sim.start(*world)
        params = run.params
        self.send_json(200, {
            "rows": params["rows"], "cols": params["cols"], "n_gen": params["n_gen"], "seed": run.seed,
            "params": {key: params[key] for key in (*RULE_KEYS, "rabbits", "foxes", "rocks")},
            "run_id": run.id, "pid": run.proc.pid,
        })

    def post_stop(self):
        self.read_body()
        self.sim.stop()
        self.send_json(200, {"stopped": True})


def main():
    parser = argparse.ArgumentParser(description="Interfaz web local de la simulación de ecosistema.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--engine", default=DEFAULT_ENGINE, help=argparse.SUPPRESS)
    parser.add_argument("--idle-timeout", type=float, default=DEFAULT_IDLE_TIMEOUT, help=argparse.SUPPRESS)
    args = parser.parse_args()

    sim = Simulation(args.engine, args.idle_timeout)
    Handler.sim = sim
    atexit.register(sim.stop)

    def exit_on_signal(*_):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, exit_on_signal)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, exit_on_signal)

    server = ThreadingHTTPServer((HOST, args.port), Handler)
    server.daemon_threads = True
    print(f"Abre la página en http://{HOST}:{server.server_address[1]}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        sim.stop()


if __name__ == "__main__":
    main()
