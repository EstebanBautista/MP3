"""Builds docs/report/informe.pdf from docs/report/informe.md.

    python docs/report/build_report.py

To fill in the team names or the video link, edit TEAM and VIDEO_URL below and run it again.

Every measured value of the report is a {{...}} marker in informe.md. resolve_markers() replaces it
with the value read from experiments/results (or from the sources, for sizes of the code), so a
figure cannot drift from its data. An unknown marker stops the build.
"""
import csv
from decimal import ROUND_HALF_UP, Decimal
import glob
import math
import os
import re
import statistics
import subprocess
import sys

import matplotlib
import numpy as np
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, Image, KeepTogether, NextPageTemplate, PageBreak,
                                PageTemplate, Paragraph, Preformatted, Spacer, Table, TableStyle)

# Fill these in when known. A value that does not start with http stays visible as plain text.
TEAM = ["[NOMBRE INTEGRANTE 1]", "[NOMBRE INTEGRANTE 2]"]
VIDEO_URL = "[ENLACE VIDEO]"
COURSE = "300CIP013 Programación Paralela, 2026-II"
REPO_URL = "https://github.com/EstebanBautista/MP3"
BRANCHES = {
    "Diseño 1, secuencial": "diseno-1-secuencial",
    "Diseño 2, estático": "diseno-2-estatico",
    "Diseño 3, adaptativo": "diseno-3-adaptativo",
}

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
RESULTS = os.path.join(ROOT, "experiments", "results")
EXAMPLES = os.path.join(ROOT, "ecosystem_examples")
SOURCE = os.path.join(HERE, "informe.md")
OUTPUT = os.path.join(HERE, "informe.pdf")

# Markers resolved at layout time, when numbers and pages of sections are known.
LAYOUT_MARKERS = ("ref:", "num:", "page:", "fig:", "tab:")
CELL_BREAK = "¦"  # Line break inside a table cell.

DESIGNS = {"seq": ("seq", "-"), "pth": ("pth", "-"), "omp_a": ("omp", "adaptive"), "omp_s": ("omp", "static")}
DESIGN_NAMES = {"pth": "Pthreads (D2)", "omp_a": "OpenMP adaptativo (D3)", "omp_s": "OpenMP estático (control)"}
THREADS = (1, 2, 4, 8, 16)
WIN_CASES = ("20x20", "100x100", "100x100_unbal01", "100x100_unbal02", "200x200", "large1000x1000")
LINUX_CASES = ("200x200", "large1000x1000")
CASE_NAMES = {"20x20": "20x20", "100x100": "100x100", "100x100_unbal01": "100x100 unbal01",
              "100x100_unbal02": "100x100 unbal02", "200x200": "200x200", "large1000x1000": "1000x1000"}


# ------------------------------------------------------------------------------------------------
# Numbers
# ------------------------------------------------------------------------------------------------

def num(value, decimals=3):
    return ("%.*f" % (decimals, value)).replace(".", ",")


def read_rows(name):
    with open(os.path.join(RESULTS, name), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_text(name):
    with open(os.path.join(RESULTS, name), encoding="utf-8", errors="replace") as f:
        return f.read()


_cache = {}


def cached(key, loader):
    if key not in _cache:
        _cache[key] = loader()
    return _cache[key]


def perf_table(platform):
    def load():
        groups = {}
        for row in read_rows("performance.csv" if platform == "win" else "performance_linux.csv"):
            groups.setdefault((row["design"], row["mode"], row["case"], int(row["threads"])), []).append(row)
        return groups
    return cached("perf" + platform, lambda: load())


def perf_values(platform, case, design, threads):
    key = DESIGNS[design] + (case, int(threads))
    rows = perf_table(platform).get(key)
    if not rows:
        raise KeyError("no measurements for %s" % (key,))
    return rows


def median_of(rows, field):
    return statistics.median(float(r[field]) for r in rows)


def perf_metric(platform, case, design, threads, metric):
    """A value of the performance tables, unformatted."""
    rows = perf_values(platform, case, design, threads)
    wall = median_of(rows, "wall")
    if metric == "wall":
        return wall
    if metric == "cpu":
        return median_of(rows, "cpu")
    if metric == "imb":
        return median_of(rows, "imbalance")
    if metric == "iqr":
        q = statistics.quantiles([float(r["wall"]) for r in rows], n=4, method="inclusive")
        return q[2] - q[0]
    if metric == "min":
        return min(float(r["wall"]) for r in rows)
    if metric == "max":
        return max(float(r["wall"]) for r in rows)
    seq = median_of(perf_values(platform, case, "seq", 1), "wall")
    if metric == "speedup":
        return seq / wall
    if metric == "eff":
        return seq / wall / int(threads)
    if metric == "over":
        return (wall / seq - 1) * 100
    if metric == "self":
        return median_of(perf_values(platform, case, design, 1), "wall") / wall
    if metric == "pergen":
        return wall / n_gen(case) * 1e6
    raise KeyError(metric)


PERF_DECIMALS = {"wall": 3, "cpu": 3, "imb": 3, "iqr": 3, "min": 3, "max": 3, "speedup": 2, "eff": 2,
                 "over": 1, "self": 2, "pergen": 0}


def resolve_perf(platform, case, design, threads, metric):
    return num(perf_metric(platform, case, design, threads, metric), PERF_DECIMALS[metric])


def n_gen(case):
    if case.startswith("large"):
        return int(re.search(r"'n_gen': (\d+)", read_text("environment.txt")).group(1))
    with open(os.path.join(EXAMPLES, "input" + case)) as f:
        return int(f.readline().split()[3])


def barrier_us(platform, design, threads):
    rows = read_rows("barriers.csv" if platform == "win" else "barriers_linux.csv")
    values = [float(r["us_per_barrier"]) for r in rows if r["design"] == design and r["threads"] == str(threads)]
    if not values:
        raise KeyError("barrier %s %s" % (design, threads))
    return statistics.median(values)


def eco_key(row):
    if row["sweep"] == "long":
        return "long_gpf10" if row["gpf"] == "10" else "long_base"
    if row["sweep"] == "base":
        return "base"
    return row["sweep"] + row["value"]


def eco_rows(key):
    def load():
        groups = {}
        for row in read_rows("ecosystem_summary.csv"):
            groups.setdefault(eco_key(row), {})[row["seed"]] = row
        return groups
    groups = cached("eco", load)
    if key not in groups:
        raise KeyError("ecosystem configuration %s" % key)
    return groups[key]


def eco_format(field, value):
    if value == "":
        return "-"
    if field.endswith("_amp"):
        return num(float(value) * 100, 1)
    if field.endswith(("_cv", "cv")) or field.endswith("_acf") or field == "fox_lag_corr":
        # Half up from the stored decimal text, as in the findings; binary rounding would turn 0.0135 into 0.013.
        places = Decimal("0.001") if "slowcv" in field else Decimal("0.01")
        return str(Decimal(value).quantize(places, rounding=ROUND_HALF_UP)).replace(".", ",")
    if field.endswith("_mean"):
        return str(round(float(value)))
    return value


def eco_range(key, field):
    values = [float(r[field]) for r in eco_rows(key).values() if r[field] != ""]
    if not values:
        return "-"
    low, high = min(values), max(values)
    low_s, high_s = eco_format(field, repr(low)), eco_format(field, repr(high))
    return low_s if low_s == high_s else "%s a %s" % (low_s, high_s)


def series(key, seed):
    def load():
        name = eco_rows(key)[seed]["file"]
        with open(os.path.join(RESULTS, "ecosystem", name), newline="") as f:
            rows = list(csv.DictReader(f))
        return {c: np.array([int(r[c]) for r in rows], dtype=float) for c in ("rabbits", "foxes")}
    return cached(("series", key, seed), load)


def resolve_series(key, seed, column, function, *args):
    x = series(key, seed)[column]
    if function == "at":
        return str(int(x[int(args[0])]))
    if function == "ma":  # Centered moving average of 21 generations, as in eco_transitorio.png.
        g = int(args[0])
        return str(round(float(x[max(0, g - 10):g + 11].mean())))
    if function == "max":
        return str(int(x.max()))
    if function == "argmax":
        return str(int(x.argmax()))
    if function == "rawcv":
        tail = x[len(x) // 5:]
        return num(float(tail.std() / tail.mean()), 2)
    if function == "pct":
        return str(round(float(np.percentile(x[len(x) // 5:], float(args[0])))))
    if function == "win":
        low, high = int(args[0]), int(args[1])
        return "%d a %d" % (int(x[low:high + 1].min()), int(x[low:high + 1].max()))
    raise KeyError(function)


def raw_acf_at(lag):
    """Autocorrelation at `lag` of the long base runs: transient dropped and trend removed."""
    values = []
    for seed in ("1", "2", "3"):
        for column in ("rabbits", "foxes"):
            x = series("long_base", seed)[column]
            x = x[len(x) // 5:]
            t = np.arange(len(x))
            x = x - np.polyval(np.polyfit(t, x, 1), t)
            values.append(float(np.dot(x[:-lag], x[lag:]) / np.dot(x, x)))
    return min(values), max(values)


def injection_count(period, amp):
    rows = [r for r in read_rows("ecosystem_injection.csv")
            if r["period"] == str(period) and float(r["amp"]) == float(amp)]
    if not rows:
        raise KeyError("injection %s %s" % (period, amp))
    return "%d de %d" % (sum(int(r["detected"]) for r in rows), len(rows))


def sensitivity_count(threshold):
    runs = set()
    seen = False
    for r in read_rows("ecosystem_sensitivity.csv"):
        if float(r["threshold"]) == float(threshold):
            seen = True
            if r["rabbit_period"] or r["fox_period"]:
                runs.add((r["param"], r["value"], r["seed"]))
    if not seen:
        raise KeyError("threshold %s" % threshold)
    return str(len(runs))


def sensitivity_period(threshold, param, value, seed, field):
    for r in read_rows("ecosystem_sensitivity.csv"):
        if (float(r["threshold"]) == float(threshold) and r["param"] == param and r["value"] == value
                and r["seed"] == seed):
            return r[field] or "-"
    raise KeyError("sensitivity row")


def foxonly(gpf, field):
    for r in read_rows("ecosystem_foxonly.csv"):
        if r["gpf"] == gpf:
            return r[field] or "-"
    raise KeyError("foxonly %s" % gpf)


TSAN_FILES = {"pth": "tsan_pth.txt", "omp": "tsan_omp.txt", "archer": "tsan_omp_archer.txt"}


def resolve_tsan(which, what, *args):
    text = read_text(TSAN_FILES[which])
    if what == "total":
        return re.search(r"^overall: (\d+) TSan warnings", text, re.M).group(1)
    if what == "runs":
        return re.search(r"TSan warnings in (\d+) runs", text).group(1)
    if what == "distinct":
        section = text.split("=== distinct SUMMARY lines over all")[1].split("overall:")[0]
        return str(len(re.findall(r"SUMMARY:", section)))
    if what == "pairs":
        section = text.split("=== distinct pairs of conflicting accesses")[1].split("overall:")[0]
        return str(len(re.findall(r" <- ", section)))
    if what == "warnlist":
        return ", ".join(re.findall(r"TSan warnings: (\d+);", text))
    if what == "identical":
        return "sí" if re.search(r"outputs identical to sequential in all runs: yes", text) else "no"
    if what == "fnda":
        return re.search(r"FNDA:(\d+),\S*%s" % args[0], text).group(1)
    if what == "control":
        match = re.search(r"%s: exit code (\d+), TSan warnings (\d+)" % args[0], text)
        return match.group(2)
    if what == "gens":
        return re.search(r"unbal01 generations: (\d+)", text).group(1)
    if what == "compiler":
        return re.search(r"^compiler: (.+)$", text, re.M).group(1).strip()
    raise KeyError(what)


def resolve_env(platform, field):
    text = read_text("environment.txt" if platform == "win" else "environment_linux.txt")
    patterns = {
        "compiler": r"^compiler: .*?(\d+\.\d+\.\d+)\s*$",
        "flags": r"^compile flags: (.+)$",
        "reps": r"^reps: (\d+)",
        "cpu": r"^cpu: (?:model name\s*: )?(.+)$",
        "load": r"^cpu load before run .*: (\d+)",
        "kernel": r"^platform: Linux-(\S+?)-x86_64",
        "cpumax": r"^cgroup cpu\.max: (.+)$",
        "logical": r"^logical cpus: (\d+)",
        "cores": r"^cores/logical: (\d+)/",
        "threadslogical": r"^cores/logical: \d+/(\d+)",
        "seed": r"'seed': (\d+)",
        "rabbits": r"'rabbits': (\d+)",
        "foxes": r"'foxes': (\d+)",
        "rocks": r"'rocks': (\d+)",
        "ngen": r"'n_gen': (\d+)",
    }
    if field == "ramgb":
        return str(round(int(re.search(r"^ram_bytes: (\d+)", text, re.M).group(1)) / 1024 ** 3))
    if field not in patterns:
        raise KeyError(field)
    return re.search(patterns[field], text, re.M).group(1).strip()


def resolve_decision(key, field):
    for r in read_rows("rule_decisions.csv"):
        if r["key"] == key:
            return r[field]
    raise KeyError(key)


def loc(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return sum(1 for _ in f)


def count_in(path, pattern):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return len(re.findall(re.escape(pattern), f.read()))


def test_count():
    def load():
        code = ("import sys,unittest;sys.path.insert(0,'.');"
                "print(unittest.defaultTestLoader.discover('tests',top_level_dir='.').countTestCases())")
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True)
        return out.stdout.strip().splitlines()[-1]
    return cached("tests", load)


# ------------------------------------------------------------------------------------------------
# Generated tables, as pipe tables
# ------------------------------------------------------------------------------------------------

def pipe_table(header, rows):
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def overhead_range(platform, cases=None):
    """Smallest and largest one-thread overhead of the parallel engines, in percent."""
    values = [perf_metric(platform, case, design, 1, "over") for case in (cases or (WIN_CASES if platform == "win" else LINUX_CASES))
              for design in DESIGN_NAMES]
    return min(values), max(values)


def table_perf(platform, case):
    header = ["Diseño"] + ["%d hilo%s" % (t, "" if t == 1 else "s") for t in THREADS] + ["Extra a 1 hilo"]
    rows = []
    for design, name in DESIGN_NAMES.items():
        cells = [name]
        for t in THREADS:
            cells.append("%s [%s]%s×%s, e %s" % (
                resolve_perf(platform, case, design, t, "wall"), resolve_perf(platform, case, design, t, "iqr"),
                CELL_BREAK, resolve_perf(platform, case, design, t, "speedup"),
                resolve_perf(platform, case, design, t, "eff")))
        cells.append("+%s %%" % resolve_perf(platform, case, design, 1, "over"))
        rows.append(cells)
    return pipe_table(header, rows)


def table_best():
    rows = []
    for case in WIN_CASES:
        options = [(perf_metric("win", case, d, t, "wall"), d, t)
                   for d in ("pth", "omp_a", "omp_s") for t in THREADS]
        seq = perf_metric("win", case, "seq", 1, "wall")
        best = {}
        for wall, design, threads in options:
            label = "omp" if design != "pth" else "pth"
            if label not in best or wall < best[label][0]:
                best[label] = (wall, design, threads)
        cell = lambda b: "%s s con %d hilo%s (×%s)%s" % (
            num(b[0]), b[2], "" if b[2] == 1 else "s", num(seq / b[0], 2), ", control estático" if b[1] == "omp_s" else "")
        rows.append([CASE_NAMES[case], num(seq) + " s", cell(best["pth"]), cell(best["omp"])])
    return pipe_table(["Mundo", "eco_seq (D1)", "Mejor Pthreads (D2)", "Mejor OpenMP (D3 o control)"], rows)


def table_barriers():
    rows = []
    for threads in (2, 4, 8, 16):
        rows.append(["%d" % threads, num(barrier_us("win", "pth", threads), 1), num(barrier_us("win", "omp", threads), 1),
                     num(barrier_us("linux", "pth", threads), 1), num(barrier_us("linux", "omp", threads), 1)])
    return pipe_table(["Hilos", "Windows, Pthreads", "Windows, OpenMP", "Contenedor, Pthreads", "Contenedor, OpenMP"], rows)


def table_grain():
    """Time per generation at 16 threads against four empty barriers, on Windows."""
    rows = []
    for case in ("20x20", "100x100", "200x200", "large1000x1000"):
        rows.append([CASE_NAMES[case], "%s µs" % resolve_perf("win", case, "pth", 16, "pergen"),
                     "%s µs" % resolve_perf("win", case, "omp_s", 16, "pergen"),
                     "%s µs" % num(perf_metric("win", case, "seq", 1, "pergen"), 0)])
    return pipe_table(["Mundo", "Pthreads, 16 hilos", "OpenMP estático, 16 hilos", "eco_seq"], rows)


def table_adaptive():
    rows = []
    for case, threads in (("20x20", 2), ("20x20", 4), ("100x100_unbal01", 8), ("100x100_unbal01", 16), ("100x100_unbal02", 8),
                          ("100x100_unbal02", 16), ("200x200", 8), ("large1000x1000", 8), ("large1000x1000", 16)):
        cell = lambda d, m: resolve_perf("win", case, d, threads, m)
        rows.append([CASE_NAMES[case], threads, cell("omp_s", "imb"), cell("omp_a", "imb"),
                     "%s [%s]" % (cell("omp_s", "wall"), cell("omp_s", "iqr")),
                     "%s [%s]" % (cell("omp_a", "wall"), cell("omp_a", "iqr"))])
    return pipe_table(["Mundo", "Hilos", "Deseq. estático", "Deseq. adaptativo", "Tiempo estático (s)", "Tiempo adaptativo (s)"], rows)


SWEEP_ROWS = [("base", "Base: 3/20/10, 5 % de rocas"), ("gpr2", "`GEN_PROC_RABBITS`=2"), ("gpr5", "`GEN_PROC_RABBITS`=5"),
              ("gpr8", "`GEN_PROC_RABBITS`=8"), ("gpf5", "`GEN_PROC_FOXES`=5"), ("gpf10", "`GEN_PROC_FOXES`=10"),
              ("gpf40", "`GEN_PROC_FOXES`=40"), ("gff3", "`GEN_FOOD_FOXES`=3"), ("gff6", "`GEN_FOOD_FOXES`=6"),
              ("gff20", "`GEN_FOOD_FOXES`=20"), ("rocks0", "Rocas 0 %"), ("rocks1500", "Rocas 15 %"),
              ("rocks3000", "Rocas 30 %")]


def table_eco_sweep():
    rows = []
    for key, label in SWEEP_ROWS:
        seeds = eco_rows(key)
        coexist = sum(r["coexist"] == "True" for r in seeds.values())
        ext = []
        for field, who in (("extinct_rabbits_gen", "conejos"), ("extinct_foxes_gen", "zorros")):
            gens = [seeds[s][field] for s in sorted(seeds)]
            if any(gens):
                ext.append("%s: %s" % (who, " / ".join(g or "-" for g in gens)))
        slow = "%s / %s" % (eco_range(key, "rabbit_slowcv"), eco_range(key, "fox_slowcv"))
        rows.append([label, "%d de 3" % coexist, eco_range(key, "rabbit_mean"), eco_range(key, "fox_mean"),
                     "-" if coexist == 0 else slow, "; ".join(ext) or "ninguna"])
    return pipe_table(["Configuración", "Coexisten", "Conejos (media)", "Zorros (media)",
                       "`slowcv` conejos / zorros", "Extinción: generación, semillas 1/2/3"], rows)


def table_eco_injection():
    amps = ("0.02", "0.05", "0.1", "0.2")
    rows = []
    for period in (40, 60, 84, 100, 150, 300, 600, 1000, 2000):
        rows.append([period] + [injection_count(period, a) for a in amps])
    return pipe_table(["Periodo inyectado", "Amplitud 2 %", "Amplitud 5 %", "Amplitud 10 %", "Amplitud 20 %"], rows)


def table_eco_weak():
    rows = []
    for key, runs in (("gpf10", "10 000"), ("long_gpf10", "20 000")):
        for seed, r in sorted(eco_rows(key).items()):
            acf = "%s / %s" % (eco_format("rabbit_acf", r["rabbit_acf"]), eco_format("fox_acf", r["fox_acf"]))
            amp = "%s / %s" % (eco_format("rabbit_amp", r["rabbit_amp"]), eco_format("fox_amp", r["fox_amp"]))
            rows.append(["%s, semilla %s" % (runs, seed), r["rabbit_period"] or "-", r["fox_period"] or "-",
                         acf, amp, {"weak": "débil", "none": "ninguno", "strong": "fuerte"}[r["cycle_grade"]], r["fox_lag"] or "-"])
    return pipe_table(["Corrida", "Periodo conejos", "Periodo zorros", "Pico de autocorrelación", "Amplitud (% de la media)",
                       "Grado", "Desfase zorros"], rows)


def table_constants():
    rows = read_rows("constants_sweep.csv")

    def row_for(weight, period):
        cells = {}
        for r in rows:
            if r["weight"] == weight and r["period"] == period:
                cells[r["case"]] = r
        return [num(float(cells[c]["median_wall"]), 3) + " / " + num(float(cells[c]["median_imbalance"]), 3)
                for c in ("unbal01", "unbal02")]

    table = [["Estático, sin rebalanceo"] + row_for("-", "-")]
    table += [["Peso %s, cada 10" % w] + row_for(w, "10") for w in ("1", "2", "4", "8", "16", "32", "64")]
    table += [["Peso 8, cada %s" % p] + row_for("8", p) for p in ("1", "5", "25", "50", "100", "500", "1000")]
    return pipe_table(["Configuración", "unbal01: tiempo (s) / desequilibrio", "unbal02: tiempo (s) / desequilibrio"], table)


def table_rules():
    rows = []
    for r in read_rows("rule_decisions.csv"):
        if r["key"].startswith("variant_"):
            rows.append([r["label"], r["allgen5x5"], r["allgen10x10"], r["allgen20x20"], r["allgen100x100"], r["outputs"]])
    return pipe_table(["Variante", "allgen5x5", "allgen10x10", "allgen20x20", "allgen100x100", "4 salidas mayores"], rows)


def table_loc():
    rows = []
    for path, role in (("engine/world.hpp", "Modelo común"), ("engine/rules.hpp", "Reglas comunes"),
                       ("engine/sim_seq.cpp", "D1"), ("engine/bands.hpp", "D2 y D3"),
                       ("engine/sim_pth.cpp", "D2"), ("engine/sim_omp.cpp", "D3")):
        rows.append(["`%s`" % path, role, loc(path)])
    return pipe_table(["Archivo", "Usado por", "Líneas (con comentarios)"], rows)


TABLES = {"best": table_best, "barriers": table_barriers, "grain": table_grain, "adaptive": table_adaptive,
          "eco_sweep": table_eco_sweep, "eco_injection": table_eco_injection, "eco_weak": table_eco_weak,
          "constants": table_constants, "rules": table_rules, "loc": table_loc}


# ------------------------------------------------------------------------------------------------
# Markers
# ------------------------------------------------------------------------------------------------

def resolve_one(body):
    if body.startswith(LAYOUT_MARKERS):
        return "{{%s}}" % body
    head, *args = body.split(":")
    if head == "perf":
        return resolve_perf(*args)
    if head == "overr":
        low, high = overhead_range(args[0], args[1:] or None)
        return "%s % % a %s % %".replace("% %", "%%") % (num(low, 1), num(high, 1))
    if head == "bar":
        return num(barrier_us(*args), 1)
    if head == "bar4":
        return num(barrier_us(*args) * 4, 0)
    if head == "ngen":
        return str(n_gen(args[0]))
    if head == "eco":
        return eco_format(args[2], eco_rows(args[0])[args[1]][args[2]])
    if head == "ecor":
        return eco_range(args[0], args[1])
    if head == "ecorh":
        return eco_range(args[0], args[1]).replace(" a ", "-")
    if head == "branchloc":
        out = subprocess.run(["git", "show", "%s:%s" % (args[0], args[1])], cwd=ROOT, capture_output=True, text=True, check=True)
        return str(len(out.stdout.splitlines()))
    if head == "ser":
        return resolve_series(*args)
    if head == "acf":
        low, high = raw_acf_at(int(args[0]))
        return "%s a %s" % (num(low, 2), num(high, 2))
    if head == "inj":
        return injection_count(args[0], args[1])
    if head == "sens":
        return sensitivity_count(args[0])
    if head == "sensp":
        return sensitivity_period(*args)
    if head == "fox":
        return foxonly(*args)
    if head == "tsan":
        return resolve_tsan(*args)
    if head == "env":
        return resolve_env(*args)
    if head == "dec":
        return resolve_decision(*args)
    if head == "loc":
        return str(loc(args[0]))
    if head == "count":
        return str(count_in(args[0], args[1]))
    if head == "tests":
        return test_count()
    if head == "table":
        if args[0] == "perf":
            return table_perf(args[1], args[2])
        return TABLES[args[0]]()
    raise ValueError("unknown marker: %s" % body)


def resolve_markers(text):
    return re.sub(r"\{\{(.+?)\}\}", lambda m: resolve_one(m.group(1)), text)


# ------------------------------------------------------------------------------------------------
# Styles
# ------------------------------------------------------------------------------------------------

INK = colors.HexColor("#1d2b36")
ACCENT = colors.HexColor("#17557f")
MUTED = colors.HexColor("#5d6b75")
RULE = colors.HexColor("#c6ced4")
HEAD_FILL = colors.HexColor("#e7edf1")
CALLOUT_FILL = colors.HexColor("#f2f6f8")
LINK = "#17557f"


def register_fonts():
    folder = os.path.join(matplotlib.get_data_path(), "fonts", "ttf")
    for name, filename in (("Body", "DejaVuSans.ttf"), ("Body-Bold", "DejaVuSans-Bold.ttf"),
                           ("Body-Italic", "DejaVuSans-Oblique.ttf"), ("Body-BoldItalic", "DejaVuSans-BoldOblique.ttf"),
                           ("Mono", "DejaVuSansMono.ttf")):
        pdfmetrics.registerFont(TTFont(name, os.path.join(folder, filename)))
    pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-Bold", italic="Body-Italic", boldItalic="Body-BoldItalic")


def make_styles():
    body = ParagraphStyle("body", fontName="Body", fontSize=9.3, leading=13.6, textColor=INK, alignment=TA_LEFT,
                          spaceAfter=6.5, splitLongWords=1)
    return {
        "body": body,
        "h1": ParagraphStyle("h1", parent=body, fontName="Body-Bold", fontSize=15, leading=19, textColor=ACCENT,
                             spaceBefore=15, spaceAfter=8, keepWithNext=1),
        "h2": ParagraphStyle("h2", parent=body, fontName="Body-Bold", fontSize=11.3, leading=15, textColor=ACCENT,
                             spaceBefore=11, spaceAfter=5, keepWithNext=1),
        "h3": ParagraphStyle("h3", parent=body, fontName="Body-Bold", fontSize=9.6, leading=13, textColor=INK,
                             spaceBefore=7, spaceAfter=3, keepWithNext=1),
        "bullet": ParagraphStyle("bullet", parent=body, leftIndent=13, bulletIndent=2, spaceAfter=3.5),
        "caption": ParagraphStyle("caption", parent=body, fontSize=8, leading=10.8, textColor=MUTED, spaceBefore=3, spaceAfter=10),
        "tabcap": ParagraphStyle("tabcap", parent=body, fontSize=8.2, leading=11, textColor=MUTED, spaceBefore=6, spaceAfter=3,
                                 keepWithNext=1),
        "cell": ParagraphStyle("cell", parent=body, fontSize=7.8, leading=10.3, spaceAfter=0),
        "cellhead": ParagraphStyle("cellhead", parent=body, fontName="Body-Bold", fontSize=7.8, leading=10.3, spaceAfter=0),
        "code": ParagraphStyle("code", fontName="Mono", fontSize=7.8, leading=10.6, textColor=INK, backColor=CALLOUT_FILL,
                               borderPadding=(4, 5, 4, 5), spaceBefore=4, spaceAfter=9, leftIndent=5, rightIndent=5),
        "callout": ParagraphStyle("callout", parent=body, spaceAfter=0),
        "title": ParagraphStyle("title", parent=body, fontName="Body-Bold", fontSize=25, leading=31, textColor=ACCENT, spaceAfter=8),
        "subtitle": ParagraphStyle("subtitle", parent=body, fontSize=12.5, leading=18, textColor=MUTED, spaceAfter=30),
        "cover": ParagraphStyle("cover", parent=body, fontSize=10.3, leading=16, spaceAfter=3),
        "toc1": ParagraphStyle("toc1", parent=body, fontName="Body-Bold", fontSize=9, leading=11.6, spaceAfter=0),
        "toc2": ParagraphStyle("toc2", parent=body, fontSize=8.4, leading=11, leftIndent=14, spaceAfter=0),
        "tocpage": ParagraphStyle("tocpage", parent=body, fontSize=8.4, leading=11, alignment=2, spaceAfter=0),
    }


# ------------------------------------------------------------------------------------------------
# Markdown subset
# ------------------------------------------------------------------------------------------------

def escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Layout:
    """Numbers of sections, figures and tables, and the page of each anchor."""

    def __init__(self):
        self.sections = {}
        self.figures = {}
        self.tables = {}
        self.pages = {}


def inline(text, layout):
    """Inline markdown to reportlab markup."""
    held = []

    def hold(markup):
        held.append(markup)
        return "\x00%d\x00" % (len(held) - 1)

    def layout_marker(match):
        kind, key = match.group(1), match.group(2)
        if kind == "ref":
            return hold('<a href="#%s" color="%s">sección\u00a0%s</a>' % (key, LINK, layout.sections[key]))
        if kind == "num":
            return hold('<a href="#%s" color="%s">%s</a>' % (key, LINK, layout.sections[key]))
        if kind == "page":
            return hold('<a href="#%s" color="%s">%s</a>' % (key, LINK, layout.pages.get(key, 0)))
        if kind == "fig":
            return hold('<a href="#%s" color="%s">figura %s</a>' % (key, LINK, layout.figures[key]))
        return hold('<a href="#%s" color="%s">tabla %s</a>' % (key, LINK, layout.tables[key]))

    text = re.sub(r"\{\{(ref|num|page|fig|tab):(.+?)\}\}", layout_marker, text)
    text = re.sub(r"`([^`]+)`", lambda m: hold('<font name="Mono" size="-0.6">%s</font>' % escape(m.group(1))), text)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
                  lambda m: hold('<a href="%s" color="%s">%s</a>' % (escape(m.group(2)), LINK, escape(m.group(1)))), text)
    text = escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", text)
    text = text.replace(CELL_BREAK, "<br/>")
    return re.sub(r"\x00(\d+)\x00", lambda m: held[int(m.group(1))], text)


def parse_blocks(text):
    """The blocks of the markdown subset used by informe.md."""
    blocks = []
    lines = text.split("\n")
    i = 0
    pending_table = None
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("```"):
            i += 1
            code = []
            while not lines[i].startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            blocks.append(("code", "\n".join(code)))
            continue
        heading = re.match(r"(#{1,3}) (.+?)(?: \{#(.+)\})?$", line)
        if heading:
            blocks.append(("h%d" % len(heading.group(1)), heading.group(2), heading.group(3)))
            i += 1
            continue
        image = re.match(r"!\[(.+?)\|(.+?)\|(.+)\]\((.+)\)$", line)
        if image:
            blocks.append(("figure", image.group(1), float(image.group(2)), image.group(3), image.group(4)))
            i += 1
            continue
        if line.startswith(":::pagebreak"):
            blocks.append(("pagebreak",))
            i += 1
            continue
        if line.startswith(":::table "):
            key, widths, caption = line[len(":::table "):].split("|", 2)
            pending_table = (key, [float(w) for w in widths.split(",")] if widths else None, caption)
            i += 1
            continue
        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                if not re.match(r"^\|[-:| ]+\|$", lines[i]):
                    rows.append([c.strip() for c in lines[i].strip().strip("|").split(" | ")])
                i += 1
            blocks.append(("table", rows, pending_table))
            pending_table = None
            continue
        if line.startswith("> "):
            quote = []
            while i < len(lines) and lines[i].startswith("> "):
                quote.append(lines[i][2:])
                i += 1
            blocks.append(("callout", " ".join(quote)))
            continue
        if line.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(lines[i][2:])
                i += 1
            blocks.append(("bullets", items))
            continue
        if re.match(r"\d+\. ", line):
            items = []
            while i < len(lines) and re.match(r"\d+\. ", lines[i]):
                items.append(lines[i].split(". ", 1)[1])
                i += 1
            blocks.append(("numbers", items))
            continue
        para = []
        while i < len(lines) and lines[i].strip() and not re.match(r"(#{1,3} |!\[|:::|\||> |- |\d+\. |```)", lines[i]):
            para.append(lines[i])
            i += 1
        blocks.append(("para", " ".join(para)))
    return blocks


def number_blocks(blocks):
    """Assigns the numbers of sections, figures and tables, and an anchor to every heading."""
    layout = Layout()
    counters = [0, 0]
    figure = table = auto = 0
    toc = []
    for index, block in enumerate(blocks):
        kind = block[0]
        if kind in ("h1", "h2", "h3"):
            auto += 1
            key = block[2] or "sec%d" % auto
            label = ""
            if kind == "h1":
                counters = [counters[0] + 1, 0]
                label = str(counters[0])
            elif kind == "h2":
                counters[1] += 1
                label = "%d.%d" % tuple(counters)
            layout.sections[key] = label
            blocks[index] = (kind, block[1], key, label)
            if kind != "h3":
                toc.append((kind, label, block[1], key))
        elif kind == "figure":
            figure += 1
            layout.figures[block[1]] = figure
        elif kind == "table" and block[2]:
            table += 1
            layout.tables[block[2][0]] = table
    return layout, toc


# ------------------------------------------------------------------------------------------------
# PDF
# ------------------------------------------------------------------------------------------------

class Heading(Paragraph):
    def __init__(self, text, style, key, level, plain):
        super().__init__(text, style)
        self.anchor_key = key
        self.level = level
        self.plain = plain


class Doc(BaseDocTemplate):
    def __init__(self, path, layout):
        super().__init__(path, pagesize=A4, leftMargin=2.3 * cm, rightMargin=2.3 * cm, topMargin=2.2 * cm, bottomMargin=2.1 * cm,
                         title="Simulación de ecosistema: informe del proyecto", author=", ".join(TEAM), subject=COURSE)
        self.layout_info = layout
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="main", leftPadding=0, rightPadding=0,
                      topPadding=0, bottomPadding=0)
        self.addPageTemplates([PageTemplate(id="cover", frames=[frame], onPage=lambda c, d: None),
                               PageTemplate(id="page", frames=[frame], onPage=self.decorate)])

    def decorate(self, canvas, doc):
        canvas.saveState()
        width, height = A4
        canvas.setFont("Body", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(self.leftMargin, height - 1.45 * cm, "Simulación de ecosistema: zorros, conejos y rocas")
        canvas.drawRightString(width - self.rightMargin, height - 1.45 * cm, "300CIP013 Programación Paralela")
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.5)
        canvas.line(self.leftMargin, height - 1.6 * cm, width - self.rightMargin, height - 1.6 * cm)
        canvas.setFont("Body", 8.5)
        canvas.drawCentredString(width / 2, 1.15 * cm, str(doc.page))
        canvas.restoreState()

    def afterFlowable(self, flowable):
        if isinstance(flowable, Heading):
            self.layout_info.pages[flowable.anchor_key] = self.page
            self.canv.bookmarkPage(flowable.anchor_key)
            if flowable.level < 2:
                self.canv.addOutlineEntry(flowable.plain, flowable.anchor_key, level=flowable.level, closed=False)


def cover(styles):
    video = VIDEO_URL if not VIDEO_URL.startswith("http") else '<a href="%s" color="%s">%s</a>' % (VIDEO_URL, LINK, VIDEO_URL)
    link = lambda url: '<a href="%s" color="%s">%s</a>' % (url, LINK, url)
    story = [Spacer(1, 3.6 * cm), Paragraph("Simulación de ecosistema", styles["title"]),
             Paragraph("Zorros, conejos y rocas: tres diseños en memoria compartida, secuencial, Pthreads y OpenMP. "
                       "Informe del proyecto.", styles["subtitle"]),
             Paragraph("<b>Curso:</b> " + COURSE, styles["cover"]), Spacer(1, 8), Paragraph("<b>Integrantes</b>", styles["cover"])]
    story += [Paragraph(name, styles["cover"]) for name in TEAM]
    story += [Spacer(1, 18), Paragraph("<b>Repositorio:</b> " + link(REPO_URL), styles["cover"]), Spacer(1, 8)]
    story += [Paragraph("<b>%s:</b><br/>%s" % (name, link("%s/tree/%s" % (REPO_URL, branch))), styles["cover"])
              for name, branch in BRANCHES.items()]
    story += [Spacer(1, 8), Paragraph("<b>Video:</b> " + video, styles["cover"])]
    return story


def toc_story(toc, layout, styles):
    rows = []
    for kind, label, title, key in toc:
        style = styles["toc1"] if kind == "h1" else styles["toc2"]
        rows.append([Paragraph('<a href="#%s">%s&nbsp;&nbsp;%s</a>' % (key, label, inline(title, layout)), style),
                     Paragraph('<a href="#%s">%s</a>' % (key, layout.pages.get(key, 0)), styles["tocpage"])])
    table = Table(rows, colWidths=[14.9 * cm, 1.5 * cm], splitByRow=1)
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 0.7), ("BOTTOMPADDING", (0, 0), (-1, -1), 0.7),
             ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]
    for row, entry in enumerate(toc):
        if entry[0] == "h1" and row:
            style.append(("TOPPADDING", (0, row), (-1, row), 4.5))
    table.setStyle(TableStyle(style))
    return [Paragraph("Índice", styles["h1"]), table, PageBreak()]


def make_table(block, layout, styles, width):
    rows, meta = block[1], block[2]
    columns = len(rows[0])
    weights = meta[1] if meta and meta[1] else [1] * columns
    if len(weights) != columns:
        raise ValueError("table %s: %d widths for %d columns" % (meta[0], len(weights), columns))
    widths = [width * w / sum(weights) for w in weights]
    data = []
    for r, row in enumerate(rows):
        if len(row) != columns:
            raise ValueError("table row has %d cells, expected %d: %s" % (len(row), columns, row))
        style = styles["cellhead"] if r == 0 else styles["cell"]
        data.append([Paragraph(inline(c, layout), style) for c in row])
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEAD_FILL), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE), ("LINEABOVE", (0, 0), (-1, 0), 0.6, MUTED),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3.5), ("RIGHTPADDING", (0, 0), (-1, -1), 3.5)]))
    if meta:
        anchor = '<a name="%s"/>' % meta[0]
        caption = Paragraph(anchor + "<b>Tabla %d.</b> %s" % (layout.tables[meta[0]], inline(meta[2], layout)), styles["tabcap"])
        return [caption, table, Spacer(1, 9)]
    return [table, Spacer(1, 9)]


def render(blocks, layout, toc, styles, width):
    story = cover(styles) + [NextPageTemplate("page"), PageBreak()] + toc_story(toc, layout, styles)
    for block in blocks:
        kind = block[0]
        if kind in ("h1", "h2", "h3"):
            title, key, label = block[1], block[2], block[3]
            text = '<a name="%s"/>%s%s' % (key, label + "&nbsp;&nbsp;" if label else "", inline(title, layout))
            story.append(Heading(text, styles[kind], key, int(kind[1]) - 1, ("%s %s" % (label, title.replace("`", ""))).strip()))
        elif kind == "para":
            story.append(Paragraph(inline(block[1], layout), styles["body"]))
        elif kind == "bullets":
            story += [Paragraph(inline(item, layout), styles["bullet"], bulletText="•") for item in block[1]]
            story.append(Spacer(1, 3))
        elif kind == "numbers":
            story += [Paragraph(inline(item, layout), styles["bullet"], bulletText="%d." % (n + 1)) for n, item in enumerate(block[1])]
            story.append(Spacer(1, 3))
        elif kind == "code":
            story.append(Preformatted(block[1], styles["code"]))
        elif kind == "callout":
            inner = Table([[Paragraph(inline(block[1], layout), styles["callout"])]], colWidths=[width])
            inner.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), CALLOUT_FILL), ("LINEBEFORE", (0, 0), (0, -1), 2.2, ACCENT),
                                       ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                                       ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
            story += [inner, Spacer(1, 8)]
        elif kind == "figure":
            key, fraction, caption, path = block[1], block[2], block[3], block[4]
            image_path = os.path.join(HERE, path)
            pixels = ImageReader(image_path).getSize()
            w = width * fraction
            image = Image(image_path, width=w, height=w * pixels[1] / pixels[0])
            image.hAlign = "CENTER"
            text = '<a name="%s"/><b>Figura %d.</b> %s' % (key, layout.figures[key], inline(caption, layout))
            story.append(KeepTogether([image, Paragraph(text, styles["caption"])]))
        elif kind == "table":
            parts = make_table(block, layout, styles, width)
            if len(block[1]) <= 8:
                story.append(KeepTogether(parts))
            else:
                story += parts
        elif kind == "pagebreak":
            story.append(PageBreak())
    return keep_headings_with_blocks(story)


def keep_headings_with_blocks(story):
    """A heading must stay with the figure or table after it; keepWithNext does not reach inside KeepTogether."""
    merged = []
    for item in story:
        headings = []
        while isinstance(item, KeepTogether) and merged and isinstance(merged[-1], Heading):
            headings.insert(0, merged.pop())
        merged.append(KeepTogether(headings + item._content) if headings else item)
    return merged


def read_source():
    with open(SOURCE, encoding="utf-8") as f:
        return f.read()


def build(path=OUTPUT):
    register_fonts()
    styles = make_styles()
    text = re.sub(r"(?<=\d) %", "\u00a0%", resolve_markers(read_source()))
    blocks = parse_blocks(text)
    layout, toc = number_blocks(blocks)
    pages = None
    for _ in range(6):  # Page numbers appear in the text, so repeat until they settle.
        doc = Doc(path, layout)
        doc.build(render(blocks, layout, toc, styles, doc.width))
        if layout.pages == pages:
            return
        pages = dict(layout.pages)
    raise RuntimeError("page numbers did not settle")


if __name__ == "__main__":
    build()
    print("written", OUTPUT)
