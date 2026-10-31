#!/usr/bin/env python3
"""Performance measurements of the three engines.

Subcommands:
  gen-large   write the large generated world (deterministic, kept out of git)
  run         measure; appends one CSV row per run, resumable, aborts on any output mismatch
  summary     print the summary table (median, IQR, speedup, efficiency) of a CSV
  env         write environment.txt (hardware, compiler, parameters, CPU load before the run)
"""
import argparse
import csv
import datetime
import os
import platform
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from tools.worldgen import generate_world  # noqa: E402

DATA = os.path.join(ROOT, "experiments", "data")
RESULTS = os.path.join(ROOT, "experiments", "results")
EXAMPLES = os.path.join(ROOT, "ecosystem_examples")

FIELDS = ["design", "mode", "case", "threads", "rep", "wall", "cpu", "imbalance", "timestamp"]
TIME_RE = re.compile(r"time wall=(\S+) cpu=(\S+) threads=(\d+) imbalance=(\S+)")

# Large world: the densities of input200x200 (1000 rabbits, 200 foxes, 200 rocks in 200x200),
# scaled by 25 for 1000x1000. The seed and parameters are fixed and recorded here.
LARGE = dict(seed=20261031, rows=1000, cols=1000, rabbits=25000, foxes=5000, rocks=5000,
             gen_proc_rabbits=3, gen_proc_foxes=20, gen_food_foxes=10, n_gen=1000)
LARGE_NAME = "large1000x1000"
DEFAULT_CASES = ["20x20", "100x100", "200x200", "100x100_unbal01", "100x100_unbal02", LARGE_NAME]
DEFAULT_THREADS = [1, 2, 4, 8, 16]


def parse_time_line(stderr):
    m = TIME_RE.search(stderr)
    if not m:
        raise ValueError("no 'time wall=... cpu=...' line in engine stderr")
    return dict(wall=float(m.group(1)), cpu=float(m.group(2)),
                threads=int(m.group(3)), imbalance=float(m.group(4)))


def quartiles(values):
    """(Q1, median, Q3) with linear interpolation (numpy's default method)."""
    v = sorted(values)

    def pct(p):
        k = (len(v) - 1) * p
        lo = int(k)
        hi = min(lo + 1, len(v) - 1)
        return v[lo] + (v[hi] - v[lo]) * (k - lo)
    return pct(0.25), pct(0.5), pct(0.75)


def summarize(rows):
    """One row per (design, mode, case, threads) with median, IQR, speedup and efficiency.

    speedup = median wall at 1 thread of the same design/mode/case / median wall at N threads.
    speedup_vs_seq and overhead_vs_seq compare against eco_seq on the same case (1 thread).
    """
    groups = {}
    for r in rows:
        key = (r["design"], r["mode"], r["case"], int(r["threads"]))
        groups.setdefault(key, []).append(r)
    stats = {}
    for key, rs in groups.items():
        w1, wm, w3 = quartiles([float(r["wall"]) for r in rs])
        c1, cm, c3 = quartiles([float(r["cpu"]) for r in rs])
        _, im, _ = quartiles([float(r["imbalance"]) for r in rs])
        stats[key] = dict(design=key[0], mode=key[1], case=key[2], threads=key[3], n=len(rs),
                          wall_q1=w1, wall_median=wm, wall_q3=w3, wall_iqr=w3 - w1,
                          cpu_median=cm, cpu_iqr=c3 - c1, imbalance_median=im)
    out = []
    for key in sorted(stats):
        s = stats[key]
        base = stats.get((key[0], key[1], key[2], 1))
        s["speedup"] = base["wall_median"] / s["wall_median"] if base else None
        s["efficiency"] = s["speedup"] / s["threads"] if base else None
        seq = stats.get(("seq", "-", key[2], 1))
        if seq and s["threads"] == 1:
            s["speedup_vs_seq"] = seq["wall_median"] / s["wall_median"]
            s["overhead_vs_seq"] = s["wall_median"] / seq["wall_median"] - 1.0
        else:
            s["speedup_vs_seq"] = s["overhead_vs_seq"] = None
        out.append(s)
    return out


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def normalize(b):
    return b.replace(b"\r\n", b"\n")


def large_path():
    return os.path.join(DATA, LARGE_NAME + ".txt")


def gen_large():
    os.makedirs(DATA, exist_ok=True)
    text = generate_world(**LARGE)
    with open(large_path(), "w", newline="\n") as f:
        f.write(text)
    return large_path()


def case_input(case):
    if case == LARGE_NAME:
        if not os.path.exists(large_path()):
            gen_large()
        p = large_path()
    else:
        p = os.path.join(EXAMPLES, "input" + case)
    with open(p, "rb") as f:
        return f.read()


def expected_output(case, build, exe_suffix):
    """Expected bytes: the example's output file, or eco_seq's output for the large world."""
    if case != LARGE_NAME:
        with open(os.path.join(EXAMPLES, "output" + case), "rb") as f:
            return normalize(f.read())
    ref = os.path.join(DATA, LARGE_NAME + ".expected")
    if not os.path.exists(ref):
        r = subprocess.run([os.path.join(build, "eco_seq" + exe_suffix)], input=case_input(case),
                           capture_output=True)
        if r.returncode != 0:
            raise SystemExit("reference run of eco_seq failed")
        with open(ref, "wb") as f:
            f.write(normalize(r.stdout))
    with open(ref, "rb") as f:
        return f.read()


def configs(threads):
    cfgs = [("seq", "-", 1)]
    cfgs += [("pth", "-", t) for t in threads]
    cfgs += [("omp", m, t) for m in ("adaptive", "static") for t in threads]
    return cfgs


def run_one(build, suffix, design, mode, threads, data):
    cmd = [os.path.join(build, "eco_" + design + suffix)]
    if design != "seq":
        cmd += ["--threads", str(threads)]
    if design == "omp":
        cmd += ["--schedule", mode]
    return subprocess.run(cmd, input=data, capture_output=True)


def cmd_run(a):
    suffix = ".exe" if os.name == "nt" else ""
    build = os.path.abspath(a.build)
    rows = read_csv(a.csv)
    done = {(r["design"], r["mode"], r["case"], int(r["threads"]), int(r["rep"])) for r in rows}
    os.makedirs(os.path.dirname(os.path.abspath(a.csv)), exist_ok=True)
    new_file = not os.path.exists(a.csv) or os.path.getsize(a.csv) == 0
    cfgs = configs(a.threads)
    inputs = {c: case_input(c) for c in a.cases}
    expected = {c: expected_output(c, build, suffix) for c in a.cases}
    total = len(a.cases) * len(cfgs) * a.reps
    count = len(done)
    with open(a.csv, "a", newline="") as f:
        w = csv.DictWriter(f, FIELDS)
        if new_file:
            w.writeheader()
        for rep in range(1, a.reps + 1):
            for case in a.cases:
                order = cfgs if rep % 2 == 1 else cfgs[::-1]  # alternate order between reps
                for design, mode, t in order:
                    if (design, mode, case, t, rep) in done:
                        continue
                    r = run_one(build, suffix, design, mode, t, inputs[case])
                    err = r.stderr.decode(errors="replace")
                    if r.returncode != 0:
                        raise SystemExit(f"ABORT: {design} {mode} {case} t={t} exit {r.returncode}: {err}")
                    if normalize(r.stdout) != expected[case]:
                        raise SystemExit(f"ABORT: output mismatch: {design} {mode} {case} t={t} rep={rep}")
                    tl = parse_time_line(err)
                    w.writerow(dict(design=design, mode=mode, case=case, threads=t, rep=rep,
                                    wall=tl["wall"], cpu=tl["cpu"], imbalance=tl["imbalance"],
                                    timestamp=datetime.datetime.now().isoformat(timespec="seconds")))
                    f.flush()
                    os.fsync(f.fileno())
                    count += 1
                    print(f"[{count}/{total}] rep{rep} {case} {design} {mode} t={t} "
                          f"wall={tl['wall']:.3f}", flush=True)
    print("done, all outputs verified")


def fmt(x, p=3):
    return "-" if x is None else f"{x:.{p}f}"


def cmd_summary(a):
    print("design mode case threads n wall_med wall_iqr cpu_med speedup eff imb ovh_seq")
    for s in summarize(read_csv(a.csv)):
        print(s["design"], s["mode"], s["case"], s["threads"], s["n"], fmt(s["wall_median"]),
              fmt(s["wall_iqr"]), fmt(s["cpu_median"]), fmt(s["speedup"], 2), fmt(s["efficiency"], 2),
              fmt(s["imbalance_median"]), fmt(s["overhead_vs_seq"], 3))


def markdown_tables(rows):
    """Markdown tables per case: wall median [IQR] s, speedup vs eco_seq, efficiency; 1-thread overhead."""
    st = summarize(rows)
    out = []
    threads = sorted({s["threads"] for s in st})
    for case in sorted({s["case"] for s in st}):
        seq = next(s for s in st if s["design"] == "seq" and s["case"] == case)
        out.append(f"### {case} (eco_seq: {seq['wall_median']:.3f} s, IQR {seq['wall_iqr']:.3f}, n={seq['n']})")
        out.append("")
        out.append("| Diseno | " + " | ".join(f"{t} hilos" for t in threads) + " | Sobrecoste a 1 hilo |")
        out.append("|---|" + "---|" * (len(threads) + 1))
        for key, name in ((("pth", "-"), "Pthreads"), (("omp", "adaptive"), "OpenMP adaptativo"),
                          (("omp", "static"), "OpenMP estatico")):
            cells = []
            for t in threads:
                r = next((x for x in st if (x["design"], x["mode"]) == key and x["case"] == case
                          and x["threads"] == t), None)
                if r is None:
                    cells.append("-")
                    continue
                sp = seq["wall_median"] / r["wall_median"]
                cells.append(f"{r['wall_median']:.3f} [{r['wall_iqr']:.3f}] x{sp:.2f} e{sp / t:.2f}")
            one = next(x for x in st if (x["design"], x["mode"]) == key and x["case"] == case
                       and x["threads"] == 1)
            out.append(f"| {name} | " + " | ".join(cells) + f" | {one['overhead_vs_seq'] * 100:+.1f} % |")
        out.append("")
    return os.linesep.replace("\r", "").join(out)


def cmd_tables(a):
    print(markdown_tables(read_csv(a.csv)))


def sh(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout.strip()
    except Exception as e:  # environment info is best effort
        return f"unavailable ({e})"


def ps(command):
    return sh(["powershell", "-NoProfile", "-Command", command])


def build_compiler_info(build):
    """Compiler and flags actually used by the build directory (not whatever g++ is on PATH)."""
    cxx, flags = "g++", "unknown"
    cache = os.path.join(build, "CMakeCache.txt")
    if os.path.exists(cache):
        m = re.search(r"^CMAKE_CXX_COMPILER:\w+=(.+)$", open(cache).read(), re.M)
        if m:
            cxx = m.group(1).strip()
    ninja = os.path.join(build, "build.ninja")
    if os.path.exists(ninja):
        m = re.search(r"^\s*FLAGS = (.+)$", open(ninja).read(), re.M)
        if m:
            flags = m.group(1).strip()
    ver = (sh([cxx, "--version"]).splitlines() or ["unavailable"])[0]
    return os.linesep.replace("\r", "").join(
        [f"compiler: {ver}", f"compiler path: {cxx}", f"compile flags: {flags}"])


def cmd_env(a):
    lines = [f"date: {datetime.datetime.now().isoformat(timespec='seconds')}",
             f"platform: {platform.platform()}", f"machine: {platform.machine()}"]
    if os.name == "nt":
        lines.append("cpu: " + ps("(Get-CimInstance Win32_Processor).Name"))
        lines.append("cores/logical: " + ps('$p=Get-CimInstance Win32_Processor; "$($p.NumberOfCores)/$($p.NumberOfLogicalProcessors)"'))
        lines.append("ram_bytes: " + ps("(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory"))
        lines.append("power plan: " + ps("powercfg /getactivescheme"))
        load = ps("(Get-Counter '\\Processor(_Total)\\% Processor Time' -SampleInterval 1 -MaxSamples 5)"
                  ".CounterSamples | ForEach-Object { [math]::Round($_.CookedValue,1) }")
        lines.append("cpu load before run (5 x 1 s samples, % total): " + load.replace("\n", " "))
    else:
        lines.append("cpu: " + sh(["sh", "-c", "grep -m1 'model name' /proc/cpuinfo"]))
        lines.append("logical cpus: " + sh(["nproc"]))
        lines.append("meminfo: " + sh(["sh", "-c", "grep MemTotal /proc/meminfo"]))
        lines.append("loadavg: " + sh(["cat", "/proc/loadavg"]))
    lines.append(build_compiler_info(a.build))
    lines.append(f"reps: {a.reps}; threads: {DEFAULT_THREADS}; cases: {DEFAULT_CASES}")
    lines.append("order: alternating (forward on odd reps, reversed on even reps)")
    lines.append(f"large world parameters: {LARGE}")
    lines.append("wall = monotonic clock; cpu = process CPU time (Windows resolution ~15.6 ms)")
    with open(a.out, "a" if a.append else "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)
    sp.add_parser("gen-large")
    r = sp.add_parser("run")
    r.add_argument("--build", default=os.path.join(ROOT, "build"))
    r.add_argument("--csv", default=os.path.join(RESULTS, "performance.csv"))
    r.add_argument("--reps", type=int, default=7)
    r.add_argument("--cases", nargs="+", default=DEFAULT_CASES)
    r.add_argument("--threads", nargs="+", type=int, default=DEFAULT_THREADS)
    s = sp.add_parser("summary")
    s.add_argument("--csv", default=os.path.join(RESULTS, "performance.csv"))
    t = sp.add_parser("tables")
    t.add_argument("--csv", default=os.path.join(RESULTS, "performance.csv"))
    e = sp.add_parser("env")
    e.add_argument("--out", default=os.path.join(RESULTS, "environment.txt"))
    e.add_argument("--build", default=os.path.join(ROOT, "build"))
    e.add_argument("--reps", type=int, default=7)
    e.add_argument("--append", action="store_true")
    a = p.parse_args()
    if a.cmd == "gen-large":
        print(gen_large())
    else:
        {"run": cmd_run, "summary": cmd_summary, "tables": cmd_tables, "env": cmd_env}[a.cmd](a)


if __name__ == "__main__":
    main()
