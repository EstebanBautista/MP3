"""Black-box tests: web/server.py always runs as a real subprocess."""
import http.client
import json
import os
import socket
import struct
import subprocess
import sys
import threading
import time
import unittest

from tests.helpers import ROOT, case_output, normalize

SERVER = os.path.join(ROOT, "web", "server.py")
HEADER = struct.Struct("<4i")
KIND_NAMES = {1: "ROCK", 2: "RABBIT", 3: "FOX"}
GENERATOR = dict(rows=10, cols=10, rabbits=20, foxes=5, rocks=5, seed=7,
                 gen_proc_rabbits=3, gen_proc_foxes=9, gen_food_foxes=6, n_gen=10)


def pid_alive(pid):
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
                             capture_output=True, text=True).stdout
        return f'"{pid}"' in out
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    with open(f"/proc/{pid}/stat") as f:  # a zombie has already exited
        return f.read().rsplit(")", 1)[1].split()[0] != "Z"


def wait_dead(pid, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not pid_alive(pid):
            return True
        time.sleep(0.1)
    return False


def process_memory(proc):
    """Memory of a child process, in bytes, using only the standard library."""
    if os.name != "nt":
        with open(f"/proc/{proc.pid}/statm") as f:
            return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

    counters = Counters()
    counters.cb = ctypes.sizeof(Counters)
    get_info = ctypes.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
    get_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    get_info.restype = wintypes.BOOL
    if not get_info(int(proc._handle), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return counters.PagefileUsage  # private bytes: what a growing buffer would inflate


class Server:
    def __init__(self, *args):
        self.proc = subprocess.Popen([sys.executable, SERVER, "--port", "0", *args],
                                     stdout=subprocess.PIPE, text=True)
        self.url = self.proc.stdout.readline().split()[-1]
        self.port = int(self.url.rsplit(":", 1)[1].rstrip("/"))

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            data = None if body is None else json.dumps(body)
            conn.request(method, path, body=data, headers=headers or {})
            response = conn.getresponse()
            return response.status, response.read(), response.headers
        finally:
            conn.close()

    def api(self, method, path, body=None):
        status, data, _ = self.request(method, path, body)
        return status, json.loads(data) if data else None

    def close(self):
        self.proc.kill()
        self.proc.wait()
        self.proc.stdout.close()


class ServerCase(unittest.TestCase):
    server_args = ()

    def setUp(self):
        self.server = Server(*self.server_args)
        self.addCleanup(self.server.close)

    def start_ok(self, body):
        status, info = self.server.api("POST", "/api/start", body)
        self.assertEqual(status, 200, info)
        return info

    def read_all_frames(self, info):
        frame_size = 16 + info["rows"] * info["cols"]
        frames = []
        while True:
            status, data, headers = self.server.request("GET", "/api/frames?count=4")
            self.assertEqual(status, 200)
            self.assertEqual(len(data) % frame_size, 0)
            frames += [data[i:i + frame_size] for i in range(0, len(data), frame_size)]
            if headers["X-Finished"] == "1":
                return frames


class TestServer(ServerCase):
    def test_start_case_and_read_frames(self):
        info = self.start_ok({"case": "5x5"})
        self.assertEqual((info["rows"], info["cols"], info["n_gen"]), (5, 5, 6))
        self.assertIsNone(info["seed"])
        self.assertEqual(info["params"]["gen_proc_rabbits"], 2)
        frames = self.read_all_frames(info)
        self.assertEqual(len(frames), 7)
        self.assertEqual([HEADER.unpack_from(f)[0] for f in frames], list(range(7)))

        _, rabbits, foxes, rocks = HEADER.unpack_from(frames[-1])
        objects = []
        for i, kind in enumerate(frames[-1][16:]):
            if kind:
                objects.append(f"{KIND_NAMES[kind]} {i // 5} {i % 5}")
        text = f"2 4 3 0 5 5 {len(objects)}\n" + "".join(o + "\n" for o in objects)
        self.assertEqual(text.encode(), normalize(case_output("5x5")))
        self.assertEqual(rabbits + foxes + rocks, len(objects))

    def test_cases_listed_with_their_parameters(self):
        status, body = self.server.api("GET", "/api/cases")
        self.assertEqual(status, 200)
        by_name = {c["name"]: c for c in body["cases"]}
        five = by_name["5x5"]
        self.assertEqual((five["rows"], five["gen_proc_foxes"]), (5, 4))
        self.assertEqual((five["rabbits"], five["foxes"], five["rocks"]), (3, 4, 2))
        self.assertIsNone(body["engine_error"])

    def test_case_parameters_can_be_overridden(self):
        info = self.start_ok({"case": "5x5", "gen_food_foxes": 5, "n_gen": 2})
        self.assertEqual(info["params"]["gen_food_foxes"], 5)
        self.assertEqual(len(self.read_all_frames(info)), 3)

    def test_generator_reports_seed_and_is_reproducible(self):
        first = self.start_ok({"generator": GENERATOR})
        self.assertEqual(first["seed"], 7)
        frames = self.read_all_frames(first)
        self.assertEqual(len(frames), 11)
        self.assertEqual(frames, self.read_all_frames(self.start_ok({"generator": GENERATOR})))

    def test_generator_picks_seed_when_missing(self):
        info = self.start_ok({"generator": {k: v for k, v in GENERATOR.items() if k != "seed"}})
        self.assertIsInstance(info["seed"], int)

    def test_case_path_traversal_rejected(self):
        for name in ("../x", "..\\x", "../../README.md", "5x5/../5x5"):
            status, body = self.server.api("POST", "/api/start", {"case": name})
            self.assertEqual(status, 400, name)
            self.assertIn("error", body)

    def test_invalid_params_400(self):
        bad = [
            {"generator": {**GENERATOR, "gen_proc_rabbits": 0}},
            {"generator": {**GENERATOR, "rabbits": 200}},
            {"generator": {**GENERATOR, "rows": "many"}},
            {"generator": {**GENERATOR, "rows": True}},
            {"case": "5x5", "gen_proc_rabbits": 0},
            {},
        ]
        for body in bad:
            status, reply = self.server.api("POST", "/api/start", body)
            self.assertEqual(status, 400, body)
            self.assertTrue(reply["error"])
        self.assertEqual(self.server.request("POST", "/api/start")[0], 400)
        conn = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=10)
        conn.request("POST", "/api/start", body="{not json")
        self.assertEqual(conn.getresponse().status, 400)
        conn.close()

    def test_restart_kills_previous_process(self):
        first = self.start_ok({"case": "200x200"})
        self.assertTrue(pid_alive(first["pid"]))
        second = self.start_ok({"case": "5x5"})
        self.assertTrue(wait_dead(first["pid"]))
        self.assertNotEqual(first["run_id"], second["run_id"])
        self.assertEqual(len(self.read_all_frames(second)), 7)

    def test_restart_during_read_does_not_hang(self):
        for _ in range(5):
            self.start_ok({"case": "200x200"})
            reader = threading.Thread(target=self.server.request, args=("GET", "/api/frames?count=500"))
            reader.start()
            self.start_ok({"case": "5x5"})
            reader.join(20)
            self.assertFalse(reader.is_alive())

    def test_stale_frame_request_gets_no_frames(self):
        old = self.start_ok({"case": "5x5"})
        new = self.start_ok({"case": "5x5"})
        path = f"/api/frames?count=7&run={old['run_id']}"
        self.assertEqual(self.server.request("GET", path)[0], 409)
        self.assertEqual(len(self.read_all_frames(new)), 7)

    def test_stop_kills_engine(self):
        info = self.start_ok({"case": "200x200"})
        self.assertEqual(self.server.api("POST", "/api/stop")[0], 200)
        self.assertTrue(wait_dead(info["pid"]))
        status, body = self.server.api("GET", "/api/frames?count=1")
        self.assertEqual(status, 409)
        self.assertTrue(body["error"])
        self.assertEqual(self.server.api("POST", "/api/stop")[0], 200)

    def test_frames_bad_count(self):
        self.start_ok({"case": "5x5"})
        self.assertEqual(self.server.request("GET", "/api/frames?count=x")[0], 400)
        self.assertEqual(self.server.request("GET", "/api/frames?count=-1")[0], 400)

    def test_paused_memory_bounded(self):
        info = self.start_ok({"case": "200x200"})
        self.assertEqual(self.server.request("GET", "/api/frames?count=1")[0], 200)
        before = process_memory(self.server.proc)
        time.sleep(2)
        growth = process_memory(self.server.proc) - before
        self.assertLess(growth, 50 * 1024 * 1024)
        self.assertTrue(pid_alive(info["pid"]), "a paused engine waits on the pipe")

    def test_static_files(self):
        for path, kind in (("/", "text/html"), ("/style.css", "text/css"), ("/app.js", "javascript")):
            status, data, headers = self.server.request("GET", path)
            self.assertEqual(status, 200, path)
            self.assertIn(kind, headers["Content-Type"])
            self.assertNotIn(b"http://", data)  # no external resources
            self.assertNotIn(b"https://", data)
        self.assertEqual(self.server.request("GET", "/../server.py")[0], 404)
        self.assertEqual(self.server.request("GET", "/nope")[0], 404)

    def test_foreign_host_rejected(self):
        status = self.server.request("POST", "/api/stop", headers={"Host": "evil.example"})[0]
        self.assertEqual(status, 403)

    def test_binds_loopback(self):
        self.assertTrue(self.server.url.startswith("http://127.0.0.1:"))
        with socket.create_connection(("127.0.0.1", self.server.port), timeout=5):
            pass
        addresses = {a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
        for address in addresses:
            if not address.startswith("127."):
                with self.assertRaises(OSError):
                    socket.create_connection((address, self.server.port), timeout=1).close()
        if os.name == "nt":
            out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True).stdout
            listeners = [line.split()[1] for line in out.splitlines()
                         if "LISTENING" in line and line.split()[-1] == str(self.server.proc.pid)]
            self.assertEqual(listeners, [f"127.0.0.1:{self.server.port}"])

    def test_server_death_kills_engine(self):
        info = self.start_ok({"case": "200x200"})
        self.server.request("GET", "/api/frames?count=1")
        self.server.proc.kill()  # the hardest exit: no Python cleanup can run
        self.server.proc.wait()
        self.assertTrue(wait_dead(info["pid"]), "orphan engine survived the server")


class TestMissingEngine(ServerCase):
    server_args = ("--engine", os.path.join(ROOT, "build", "no_such_engine.exe"))

    def test_missing_engine_message(self):
        status, body = self.server.api("POST", "/api/start", {"case": "5x5"})
        self.assertEqual(status, 503)
        self.assertIn("scripts/build.ps1", body["error"])
        status, body = self.server.api("GET", "/api/cases")
        self.assertEqual(status, 200)
        self.assertIn("scripts/build.ps1", body["engine_error"])


class TestIdleClient(ServerCase):
    server_args = ("--idle-timeout", "1")

    def test_silent_client_stops_engine(self):
        info = self.start_ok({"case": "200x200"})
        self.assertTrue(wait_dead(info["pid"], timeout=8), "engine outlived its client")
        status, body = self.server.api("GET", "/api/frames?count=1")
        self.assertEqual(status, 409)
        self.assertIn("inactividad", body["error"])

    def test_heartbeat_keeps_paused_run_alive(self):
        info = self.start_ok({"case": "200x200"})
        for _ in range(6):
            time.sleep(0.4)
            status, data, _ = self.server.request("GET", "/api/frames?count=0")
            self.assertEqual((status, data), (200, b""))
        self.assertTrue(pid_alive(info["pid"]))


if __name__ == "__main__":
    unittest.main()
