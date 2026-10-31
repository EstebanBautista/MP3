#!/usr/bin/env python3
"""Population-dynamics experiments for the ecosystem simulation.

Subcommands:
  run      run the sweeps with eco_seq, write one CSV per run and the summary table
  summary  (re)build ecosystem_summary.csv from the per-run CSVs
  explore  the exploratory runs used once to pick the base densities
  foxonly  control runs without rabbits
  inject   detection limits: synthetic slow cycles injected into real series
  plot     draw the figures docs/report/figuras/eco_*.png

analyze() is the analysis used by every subcommand. It is pure (no I/O) so it can be tested with
synthetic signals.
"""
import math

import numpy as np

# An autocorrelation peak counts as a cycle only if it reaches this value (and the autocorrelation
# has gone below zero before it). Below it analyze() returns None. 0.3 is a conventional choice, not
# derived; see ecosystem_findings.md for what happens with other values.
CYCLE_THRESHOLD = 0.3
# A cycle is graded "strong" if, besides the threshold, its autocorrelation peak reaches
# STRONG_ACF and its amplitude (std of the series band-passed around the period, as a fraction of
# the mean) reaches STRONG_AMP. Detected but not strong is "weak".
STRONG_ACF = 0.6
STRONG_AMP = 0.10
# Share of the series dropped as transient before any analysis.
TRANSIENT_FRACTION = 0.2
# A raw period up to this many generations is "fast": its pattern is removed before looking for
# the slow cycle. The reproduction periods of the sweeps (GEN_PROC + 1) are below it.
FAST_MAX = 50
# The fast pattern is the mean value per phase modulo the least common multiple of the fast
# periods. If that exceeds MAX_FOLD, or the series does not hold MIN_REPEATS repetitions of it, each
# fast period is removed on its own instead.
MAX_FOLD = 400
MIN_REPEATS = 8
# Light smoothing (moving average, in generations) applied after removing the fast pattern, only to
# calm the residual. It does not cancel any period above ~20 generations.
SMOOTH = 9
# Shortest slow period searched (below this the smoothing distorts the autocorrelation).
MIN_SLOW = 20


def _acf(x):
    """Normalized autocorrelation of x (mean and linear trend removed), lags 0..len(x)-1."""
    n = len(x)
    t = np.arange(n)
    x = x - np.polyval(np.polyfit(t, x, 1), t)
    size = 1 << (2 * n - 1).bit_length()
    f = np.fft.rfft(x, size)
    ac = np.fft.irfft(f * np.conj(f), size)[:n]
    if ac[0] <= 1e-12 * max(1.0, float(np.mean(np.abs(x))) ** 2) * n:
        return None
    return ac / ac[0]


def _peak_lag(ac, threshold, need_zero_cross, min_lag=2):
    """Lag of the first autocorrelation peak that is a local maximum, reaches threshold and is
    within 80% of the highest such peak (so a small bump on the flank of a peak does not win).
    Searches up to a third of the series so that at least three repetitions back the period."""
    if ac is None:
        return None, None
    max_lag = len(ac) // 3
    peaks = [k for k in range(max(min_lag, 2), max_lag)
             if ac[k] > ac[k - 1] and ac[k] >= ac[k + 1] and ac[k] >= threshold]
    if need_zero_cross:
        peaks = [k for k in peaks if ac[1:k].min() < 0]
    if not peaks:
        return None, None
    best = max(ac[k] for k in peaks)
    k = next(k for k in peaks if ac[k] >= 0.8 * best)
    return k, float(ac[k])


def _boxcar(x, w):
    return np.convolve(x, np.ones(w) / w, mode="valid") if w > 1 else x


def _remove_phase_mean(x, gens, period):
    """x minus its mean value at each phase gens mod period."""
    phase = gens % period
    means = np.bincount(phase, weights=x, minlength=period) / np.maximum(np.bincount(phase, minlength=period), 1)
    return x - means[phase]


def _fold_period(periods, n):
    """Period used to remove the fast pattern: the lcm of `periods`, or None if each must be
    removed on its own (lcm too long for the series)."""
    w = 1
    for p in periods:
        w = w * p // math.gcd(w, p)
    return w if w <= MAX_FOLD and n >= MIN_REPEATS * w else None


def remove_fast(x, gens, periods):
    """Series without the periodic pattern of the fast periods. Returns (series, fold) where fold is
    the period used (0 if nothing was removed). The mean is kept."""
    periods = [p for p in periods if len(x) >= MIN_REPEATS * p]
    if not periods:
        return x, 0
    fold = _fold_period(periods, len(x))
    y = x - x.mean()
    if fold:
        y = _remove_phase_mean(y, gens, fold)
    else:
        for p in periods:
            y = _remove_phase_mean(y, gens, p)
        fold = max(periods)
    return y + x.mean(), fold


def _bandpass(x, period, lo=0.7, hi=1.4):
    """x with only the periods between lo*period and hi*period (mean removed)."""
    z = np.fft.rfft(x - x.mean())
    fr = np.fft.rfftfreq(len(x))
    z[(fr < 1.0 / (hi * period)) | (fr > 1.0 / (lo * period))] = 0
    return np.fft.irfft(z, len(x))


def _first_zero(series, col):
    for row in series:
        if row[col] == 0:
            return row[0]
    return None


def _late_cv(x):
    """std/mean over the second half of x with its linear trend removed (drift left out)."""
    x = x[len(x) // 2:]
    t = np.arange(len(x))
    return float(np.std(x - np.polyval(np.polyfit(t, x, 1), t)) / np.mean(x))


def analyze(series, threshold=CYCLE_THRESHOLD, transient=TRANSIENT_FRACTION, fast_max=FAST_MAX):
    """series: rows (gen, rabbits, foxes), as in the engine's --stats-file.

    Returns a dict:
      extinct_rabbits_gen, extinct_foxes_gen  first generation with 0 animals, or None
      coexist                                 both species alive in the last generation
      rabbit_raw_period, fox_raw_period       first autocorrelation peak >= threshold of the raw
                                              series (this is the fast oscillation if there is one)
      fold                                    period of the fast pattern that was subtracted (the
                                              lcm of the fast periods; 0 = none)
      rabbit_period, fox_period               period of the slow cycle: first autocorrelation peak
                                              >= threshold of the series after subtracting the mean
                                              per phase (mod `fold`) and smoothing SMOOTH
                                              generations; the autocorrelation must have been
                                              negative before it. None if there is none
      rabbit_acf, fox_acf                     height of that peak (None if no cycle)
      rabbit_amp, fox_amp                     std of the series band-passed around the slow period,
                                              as a fraction of the mean (None if no cycle)
      cycle_grade                             "none", "weak" or "strong" (see STRONG_ACF/STRONG_AMP),
                                              the best of the two species
      fox_lag, fox_lag_corr                   generations by which the foxes' slow component trails
                                              the rabbits' (cross-correlation maximum of the two
                                              band-passed series; negative = foxes lead) and the
                                              correlation there. None unless a slow period was found
      rabbit_cv, fox_cv                       std/mean of the series without the fast pattern, over
                                              the second half with linear trend removed (residual
                                              variation at every time scale)
      rabbit_slowcv, fox_slowcv               the same after a moving average of `fold` generations:
                                              variation slower than the fast pattern
    The first `transient` of the series is discarded. Without coexistence the periods are None.
    """
    rows = list(series)
    out = dict(extinct_rabbits_gen=_first_zero(rows, 1), extinct_foxes_gen=_first_zero(rows, 2),
               coexist=bool(rows) and rows[-1][1] > 0 and rows[-1][2] > 0,
               rabbit_raw_period=None, fox_raw_period=None, fold=0, rabbit_period=None, fox_period=None,
               rabbit_acf=None, fox_acf=None, rabbit_amp=None, fox_amp=None, cycle_grade="none",
               fox_lag=None, fox_lag_corr=None, rabbit_cv=None, fox_cv=None, rabbit_slowcv=None, fox_slowcv=None)
    if not out["coexist"]:
        return out
    cut = int(len(rows) * transient)
    g = np.array([x[0] for x in rows[cut:]], dtype=int)
    r = np.array([x[1] for x in rows[cut:]], dtype=float)
    f = np.array([x[2] for x in rows[cut:]], dtype=float)
    if len(r) < 12:
        return out

    raw = {}
    for name, x in (("rabbit", r), ("fox", f)):
        raw[name], _ = _peak_lag(_acf(x), threshold, need_zero_cross=False)
        out[name + "_raw_period"] = raw[name]
    fast = sorted({p for p in raw.values() if p is not None and p <= fast_max})

    clean, found = {}, {}
    for name, x in (("rabbit", r), ("fox", f)):
        y, out["fold"] = remove_fast(x, g, fast)
        clean[name] = y
        out[name + "_cv"] = _late_cv(y)
        out[name + "_slowcv"] = _late_cv(_boxcar(y, out["fold"])) if out["fold"] > 1 else out[name + "_cv"]
        p, acf = _peak_lag(_acf(_boxcar(y, SMOOTH)), threshold, need_zero_cross=True, min_lag=MIN_SLOW)
        out[name + "_period"], out[name + "_acf"] = p, acf
        if p is not None:
            amp = float(np.std(_bandpass(y, p)) / np.mean(x))
            out[name + "_amp"] = amp
            found[name] = (p, acf, amp)

    if found:
        grade = "weak"
        if any(acf >= STRONG_ACF and amp >= STRONG_AMP for _, acf, amp in found.values()):
            grade = "strong"
        out["cycle_grade"] = grade
        period = int(round(sum(v[0] for v in found.values()) / len(found)))
        a, b = _bandpass(clean["rabbit"], period), _bandpass(clean["fox"], period)
        best_lag, best = None, -2.0
        for lag in range(-(period // 2), period // 2 + 1):
            x, y = (a[:len(a) - lag], b[lag:]) if lag >= 0 else (a[-lag:], b[:len(b) + lag])
            c = float(np.dot(x, y) / (np.linalg.norm(x) * np.linalg.norm(y)))
            if c > best:
                best_lag, best = lag, c
        out["fox_lag"], out["fox_lag_corr"] = best_lag, best
    return out


# ---------------------------------------------------------------------------------------------
# Experiments: sweeps, summary table and figures. Everything below needs the built engine.
# ---------------------------------------------------------------------------------------------
import argparse  # noqa: E402
import csv  # noqa: E402
import os  # noqa: E402
import random  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from tools.worldgen import generate_world  # noqa: E402

RUNS_DIR = os.path.join(ROOT, "experiments", "results", "ecosystem")
SUMMARY = os.path.join(ROOT, "experiments", "results", "ecosystem_summary.csv")
FIGS = os.path.join(ROOT, "docs", "report", "figuras")

SIZE = 100
SEEDS = [1, 2, 3]
# Base configuration. The initial densities (1500 rabbits = 15%, 150 foxes = 1.5%, 500 rocks = 5%
# of the 100x100 cells) were chosen once from a small exploratory run (10 combinations of rabbits
# 700..3000, foxes 70..300, 3000 generations, seed 1: all kept both species alive) and not
# changed afterwards. The periods and hunger limit are those of the course example inputs.
BASE = dict(rabbits=1500, foxes=150, rocks=500, gpr=3, gpf=20, gff=10, n_gen=10000)
LONG_GEN = 20000
SWEEPS = [  # (parameter, values), one parameter varied at a time from BASE
    ("gpr", [2, 3, 5, 8]),
    ("gpf", [5, 10, 20, 40]),
    ("gff", [3, 6, 10, 20]),
    ("rocks", [0, 500, 1500, 3000]),  # 0%, 5%, 15%, 30% of the cells
]


def configs():
    """Unique (sweep, param, value, config) tuples; the base is listed once as sweep 'base'."""
    out = [("base", None, None, dict(BASE))]
    for param, values in SWEEPS:
        for v in values:
            if v == BASE[param]:
                continue
            c = dict(BASE)
            c[param] = v
            out.append((param, param, v, c))
    # Longer runs (2x generations) of the base and of the one configuration whose 10000-generation
    # runs showed a weak slow oscillation, to see whether it persists. Same seeds.
    for extra in ({}, {"gpf": 10}):
        out.append(("long", "n_gen", LONG_GEN, dict(BASE, n_gen=LONG_GEN, **extra)))
    return out


def run_name(c, seed):
    return "r{rabbits}_f{foxes}_k{rocks}_pr{gpr}_pf{gpf}_hf{gff}_n{n_gen}_s{seed}".format(seed=seed, **c)


def load_series(path):
    with open(path) as fh:
        next(fh)
        return [tuple(int(v) for v in line.split(",")) for line in fh if line.strip()]


def run_engine(c, seed, build):
    path = os.path.join(RUNS_DIR, run_name(c, seed) + ".csv")
    world = generate_world(seed, SIZE, SIZE, c["rabbits"], c["foxes"], c["rocks"],
                           c["gpr"], c["gpf"], c["gff"], c["n_gen"])
    exe = os.path.join(build, "eco_seq" + (".exe" if os.name == "nt" else ""))
    r = subprocess.run([exe, "--stats-file", path], input=world.encode(), capture_output=True)
    if r.returncode != 0:
        raise SystemExit("eco_seq failed: " + r.stderr.decode(errors="replace"))
    return path


FIELDS = ["sweep", "param", "value", "seed", "rabbits0", "foxes0", "rocks", "gpr", "gpf", "gff", "n_gen",
          "generations", "extinct_rabbits_gen", "extinct_foxes_gen", "coexist",
          "rabbit_raw_period", "fox_raw_period", "rabbit_period", "fox_period", "rabbit_acf", "fox_acf",
          "rabbit_amp", "fox_amp", "cycle_grade", "fox_lag", "fox_lag_corr", "fold", "rabbit_cv", "fox_cv",
          "rabbit_slowcv", "fox_slowcv", "rabbit_mean", "fox_mean", "file"]


def summary_row(sweep, param, value, c, seed):
    name = run_name(c, seed) + ".csv"
    series = load_series(os.path.join(RUNS_DIR, name))
    a = analyze(series)
    tail = series[int(len(series) * TRANSIENT_FRACTION):]
    row = dict(sweep=sweep, param=param or "", value="" if value is None else value, seed=seed,
               rabbits0=c["rabbits"], foxes0=c["foxes"], rocks=c["rocks"], gpr=c["gpr"], gpf=c["gpf"],
               gff=c["gff"], n_gen=c["n_gen"], generations=len(series) - 1,
               rabbit_mean=round(sum(r[1] for r in tail) / len(tail), 1),
               fox_mean=round(sum(r[2] for r in tail) / len(tail), 1), file=name)
    for k in ("extinct_rabbits_gen", "extinct_foxes_gen", "coexist", "rabbit_raw_period", "fox_raw_period",
              "rabbit_period", "fox_period", "cycle_grade", "fox_lag", "fold"):
        row[k] = a[k]
    for k in ("rabbit_acf", "fox_acf", "rabbit_amp", "fox_amp", "fox_lag_corr", "rabbit_cv", "fox_cv", "rabbit_slowcv", "fox_slowcv"):
        row[k] = "" if a[k] is None else round(a[k], 4)
    return {k: ("" if v is None else v) for k, v in row.items()}


def read_summary():
    with open(SUMMARY, newline="") as fh:
        return list(csv.DictReader(fh))


def cmd_summary(_args=None):
    rows = [summary_row(s, p, v, c, seed) for s, p, v, c in configs() for seed in SEEDS]
    with open(SUMMARY, "w", newline="") as fh:
        w = csv.DictWriter(fh, FIELDS)
        w.writeheader()
        w.writerows(rows)
    return rows


def cmd_run(args):
    os.makedirs(RUNS_DIR, exist_ok=True)
    for s, p, v, c in configs():
        for seed in SEEDS:
            path = os.path.join(RUNS_DIR, run_name(c, seed) + ".csv")
            if os.path.exists(path) and not args.force:
                continue
            run_engine(c, seed, args.build)
            print("ran", os.path.basename(path), flush=True)
    rows = cmd_summary()
    print("summary:", len(rows), "rows ->", SUMMARY)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--build", default=os.path.join(ROOT, "build"))
    r.add_argument("--force", action="store_true", help="rerun even if the CSV exists")
    r.set_defaults(fn=cmd_run)
    sub.add_parser("summary").set_defaults(fn=cmd_summary)
    for name, fn in (("explore", cmd_explore), ("foxonly", cmd_foxonly)):
        q = sub.add_parser(name)
        q.add_argument("--build", default=os.path.join(ROOT, "build"))
        q.add_argument("--force", action="store_true")
        q.set_defaults(fn=fn)
    sub.add_parser("inject").set_defaults(fn=cmd_inject)
    sub.add_parser("sensitivity").set_defaults(fn=cmd_sensitivity)
    sub.add_parser("plot").set_defaults(fn=lambda a: cmd_plot())
    args = ap.parse_args()
    args.fn(args)


RABBIT_COLOR, FOX_COLOR = "#2a78d6", "#eb6834"  # palette slots 1 and 2, fixed per species
MUTED_INK = "#52514e"
GREY = "#898781"


def _series_for(c, seed):
    return load_series(os.path.join(RUNS_DIR, run_name(c, seed) + ".csv"))


def _plot_style():
    import matplotlib
    matplotlib.use("Agg")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import plot_performance
    plot_performance.style()
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 10, "axes.titlesize": 10.5, "legend.fontsize": 9})
    return plt


def clean_series(series, col):
    """(generations, values) for display: one species smoothed with a moving average of `fold`
    generations (the lcm of the fast periods), which cancels the fast pattern exactly. None if there
    is no fast pattern or a species is extinct. Display only: analyze() uses the phase-mean
    subtraction, which does not smear the slow band."""
    fold = analyze(series)["fold"]
    if fold <= 1:
        return None
    x = np.array([r[col] for r in series], dtype=float)
    y = _boxcar(x, fold)
    return np.arange(len(y)) + (fold - 1) / 2, y


def _fmt_int(ax, axis="y"):
    import matplotlib.ticker as mt
    f = mt.FuncFormatter(lambda v, _: f"{v:,.0f}".replace(",", "."))
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(f)


def _panel(ax, series, title):
    """Both species in one panel on a log axis (same unit, very different sizes): the raw series
    faint and the series without the fast pattern in full color."""
    a = analyze(series)
    g = np.array([r[0] for r in series])
    for col, color in ((1, RABBIT_COLOR), (2, FOX_COLOR)):
        y = np.array([r[col] for r in series], dtype=float)
        ax.plot(g, np.maximum(y, 0.8), color=color, lw=0.5, alpha=0.28)
        clean = clean_series(series, col)
        if clean is not None:
            ax.plot(clean[0], np.maximum(clean[1], 0.8), color=color, lw=1.8)
    ax.set_yscale("log")
    ax.set_ylim(0.7, 8000)
    ax.set_title(title, loc="left")
    ax.set_xlabel("Generación")
    ax.set_xticks([0, 5000, 10000])
    _fmt_int(ax, "x")
    _fmt_int(ax)
    for name, gen, ypos, color in (("conejos", a["extinct_rabbits_gen"], 0.62, RABBIT_COLOR),
                                   ("zorros", a["extinct_foxes_gen"], 0.45, FOX_COLOR)):
        if gen is not None:
            ax.plot([gen], [0.8], marker="X", color=color, ms=8, mec="black", mew=0.8, zorder=5)
            ax.text(0.97, ypos, f"extinción de {name}:\ngen. {gen}", transform=ax.transAxes, ha="right",
                    fontsize=8.5, color=MUTED_INK)


def _legend(fig):
    from matplotlib.lines import Line2D
    handles = [Line2D([], [], color=RABBIT_COLOR, lw=1.8, label="Conejos"),
               Line2D([], [], color=FOX_COLOR, lw=1.8, label="Zorros"),
               Line2D([], [], color=GREY, lw=0.6, alpha=0.6, label="Serie cruda"),
               Line2D([], [], color=GREY, lw=1.8, label="Media móvil de un periodo del patrón rápido (lo cancela)")]
    fig.legend(handles=handles, loc="lower center", ncol=2, frameon=False, bbox_to_anchor=(0.5, -0.01))


def plot_base(plt):
    series = _series_for(dict(BASE), 1)
    g = np.array([r[0] for r in series])
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.2), gridspec_kw=dict(width_ratios=[2.2, 1]))
    for row, (col, name, color) in enumerate(((1, "Conejos", RABBIT_COLOR), (2, "Zorros", FOX_COLOR))):
        y = np.array([r[col] for r in series], dtype=float)
        ax, z = axes[row]
        ax.plot(g, y, color=color, lw=0.5, alpha=0.3)
        x, s = clean_series(series, col)
        ax.plot(x, s, color=color, lw=1.8)
        ax.set_title(f"{name}: toda la corrida", loc="left")
        ax.set_ylabel("Individuos")
        ax.set_ylim(0, None)
        lo, hi = 2000, 2100
        z.plot(g[lo:hi], y[lo:hi], color=color, lw=1.4, marker="o", ms=2.5)
        z.set_title(f"{name}: gen. {lo}-{hi}", loc="left")
        z.set_xlim(lo, hi)
        z.set_xticks([lo, lo + 50, hi])
        for a_ in (ax, z):
            _fmt_int(a_)
            _fmt_int(a_, "x")
        if row == 1:
            ax.set_xlabel("Generación")
            z.set_xlabel("Generación")
    from matplotlib.lines import Line2D
    fig.legend(handles=[Line2D([], [], color=GREY, lw=0.6, alpha=0.6, label="Serie cruda"),
                        Line2D([], [], color=GREY, lw=1.8, label="Media móvil de un periodo del patrón rápido (lo cancela)")],
               loc="lower center", ncol=2, frameon=False, bbox_to_anchor=(0.5, -0.005))
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(os.path.join(FIGS, "eco_base_serie.png"))
    plt.close(fig)


def plot_grid(plt, items, ncols, name, size):
    nrows = (len(items) + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=size, squeeze=False, sharey=True)
    for ax, (title, c, seed) in zip(axes.flat, items):
        _panel(ax, _series_for(c, seed), title)
        ax.tick_params(labelleft=True)
    for ax in axes[:, 0]:
        ax.set_ylabel("Individuos (escala log)")
    _legend(fig)
    fig.tight_layout(rect=(0, 0.09, 1, 1))
    fig.savefig(os.path.join(FIGS, name))
    plt.close(fig)


def plot_stability(plt):
    """One column per swept parameter. Top: seeds (of 3) where both species are alive at the end.
    Bottom: relative amplitude (std/mean) of the series without the fast periods, one dot per
    seed; a black ring marks a slow cycle found by analyze()."""
    rows = [r for r in read_summary() if r["sweep"] != "long"]
    sweeps = [("gpr", "Periodo de conejos\n(GEN_PROC_RABBITS)", [2, 3, 5, 8]),
              ("gpf", "Periodo de zorros\n(GEN_PROC_FOXES)", [5, 10, 20, 40]),
              ("gff", "Hambre de zorros\n(GEN_FOOD_FOXES)", [3, 6, 10, 20]),
              ("rocks", "Rocas\n(% de las celdas)", [0, 500, 1500, 3000])]
    fig, axes = plt.subplots(2, 4, figsize=(7.6, 5.4), gridspec_kw=dict(height_ratios=[1, 1.5]))
    for k, (p, label, vals) in enumerate(sweeps):
        top, bot = axes[0, k], axes[1, k]
        for i, v in enumerate(vals):
            sel = [r for r in rows if (r["param"] == p and int(r["value"]) == v) or
                   (r["sweep"] == "base" and BASE[p] == v)]
            alive = sum(r["coexist"] == "True" for r in sel)
            top.bar(i, alive, color=GREY if alive < 3 else "#1baf7a", width=0.6)
            if alive == 0:
                top.text(i, 0.12, "0", ha="center", fontsize=10, color=MUTED_INK)
            for off, col, color, pcol in ((-0.12, "rabbit_slowcv", RABBIT_COLOR, "rabbit_period"),
                                          (0.12, "fox_slowcv", FOX_COLOR, "fox_period")):
                for r in sel:
                    if r[col] == "":
                        continue
                    cyc = r[pcol] != ""
                    bot.plot(i + off + (int(r["seed"]) - 2) * 0.05, float(r[col]), "o", color=color, ms=5.5,
                             mec="black" if cyc else color, mew=1.6 if cyc else 0)
        shown = [f"{v * 100 // 10000}%" for v in vals] if p == "rocks" else [str(v) for v in vals]
        for ax in (top, bot):
            ax.set_xticks(range(len(vals)))
            ax.set_xticklabels(shown)
            ax.set_xlim(-0.6, len(vals) - 0.4)
        top.set_ylim(0, 3.4)
        top.set_yticks([0, 1, 2, 3])
        top.set_title(label, fontsize=9.5)
        bot.set_yscale("log")
        bot.set_ylim(0.002, 2)
        if k == 0:
            top.set_ylabel("Semillas con\ncoexistencia (de 3)")
            bot.set_ylabel("Variación lenta, 2.ª mitad (desv./media)")
        else:
            bot.tick_params(labelleft=False)
            top.tick_params(labelleft=False)
    from matplotlib.lines import Line2D
    fig.legend(handles=[Line2D([], [], marker="o", ls="", color=RABBIT_COLOR, label="Conejos"),
                        Line2D([], [], marker="o", ls="", color=FOX_COLOR, label="Zorros"),
                        Line2D([], [], marker="o", ls="", color="white", mec="black", mew=1.6,
                               label="Oscilación lenta débil detectada")],
               loc="lower center", ncol=3, frameon=False, bbox_to_anchor=(0.5, -0.005))
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(os.path.join(FIGS, "eco_estabilidad.png"))
    plt.close(fig)


EXPLORE_DIR = os.path.join(ROOT, "experiments", "results", "ecosystem_explore")
EXPLORE_CSV = os.path.join(ROOT, "experiments", "results", "ecosystem_explore.csv")
FOXONLY_DIR = os.path.join(ROOT, "experiments", "results", "ecosystem_foxonly")
FOXONLY_CSV = os.path.join(ROOT, "experiments", "results", "ecosystem_foxonly.csv")
INJECT_CSV = os.path.join(ROOT, "experiments", "results", "ecosystem_injection.csv")
SENS_CSV = os.path.join(ROOT, "experiments", "results", "ecosystem_sensitivity.csv")

# Exploratory runs used once to pick the base densities: 100x100, 500 rocks, seed 1, 3000 generations.
EXPLORE_POPS = [(700, 70), (1500, 150), (2000, 100), (1000, 300), (3000, 300)]
EXPLORE_PARAMS = [(3, 20, 10), (3, 9, 6)]  # (gpr, gpf, gff) of the course example inputs
EXPLORE_GEN = 3000


def _run_free(c, seed, path, build):
    """Like run_engine, with the output path given."""
    world = generate_world(seed, SIZE, SIZE, c["rabbits"], c["foxes"], c["rocks"],
                           c["gpr"], c["gpf"], c["gff"], c["n_gen"])
    exe = os.path.join(build, "eco_seq" + (".exe" if os.name == "nt" else ""))
    r = subprocess.run([exe, "--stats-file", path], input=world.encode(), capture_output=True)
    if r.returncode != 0:
        raise SystemExit("eco_seq failed: " + r.stderr.decode(errors="replace"))


def _write_rows(path, fields, rows):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fields)
        w.writeheader()
        w.writerows(rows)


def cmd_explore(args):
    os.makedirs(EXPLORE_DIR, exist_ok=True)
    rows = []
    for rabbits, foxes in EXPLORE_POPS:
        for gpr, gpf, gff in EXPLORE_PARAMS:
            c = dict(rabbits=rabbits, foxes=foxes, rocks=500, gpr=gpr, gpf=gpf, gff=gff, n_gen=EXPLORE_GEN)
            name = run_name(c, 1) + ".csv"
            path = os.path.join(EXPLORE_DIR, name)
            if not os.path.exists(path) or args.force:
                _run_free(c, 1, path, args.build)
            s = load_series(path)
            rows.append(dict(rabbits0=rabbits, foxes0=foxes, gpr=gpr, gpf=gpf, gff=gff, seed=1, generations=len(s) - 1,
                             rabbits_end=s[-1][1], foxes_end=s[-1][2], rabbits_max=max(r[1] for r in s),
                             foxes_max=max(r[2] for r in s), coexist=s[-1][1] > 0 and s[-1][2] > 0, file=name))
    _write_rows(EXPLORE_CSV, list(rows[0]), rows)
    print("explore:", len(rows), "rows ->", EXPLORE_CSV)


def cmd_foxonly(args):
    """Foxes with no rabbits: 150 foxes, 500 rocks, seed 1, GEN_PROC_RABBITS=3, 3000 generations."""
    os.makedirs(FOXONLY_DIR, exist_ok=True)
    rows = []
    for gpf, gff in ((5, 10), (10, 10), (20, 10), (9, 6)):
        c = dict(rabbits=0, foxes=150, rocks=500, gpr=3, gpf=gpf, gff=gff, n_gen=3000)
        name = run_name(c, 1) + ".csv"
        path = os.path.join(FOXONLY_DIR, name)
        if not os.path.exists(path) or args.force:
            _run_free(c, 1, path, args.build)
        s = load_series(path)
        at = {g: s[g][2] for g in (0, 10, 20, 50, 500, 2999)}
        gone = next((r[0] for r in s if r[2] == 0), "")
        rows.append(dict(gpf=gpf, gff=gff, foxes_gen0=at[0], foxes_gen10=at[10], foxes_gen20=at[20], foxes_gen50=at[50],
                         foxes_gen500=at[500], foxes_gen2999=at[2999], extinct_foxes_gen=gone, file=name))
    _write_rows(FOXONLY_CSV, list(rows[0]), rows)
    print("foxonly:", len(rows), "rows ->", FOXONLY_CSV)


# Detection limits: a slow cycle of known period and relative amplitude is multiplied into real
# series (rabbits by 1 + a*sin(2*pi*g/P), foxes by 1 + a*sin(2*pi*(g - P/4)/P), so the foxes trail by
# P/4) and analyze() is asked whether it finds it. A detection counts if either species reports a
# period within 15% of P.
INJECT_CONFIGS = [("base", {}), ("gff6", {"gff": 6}), ("gpr5", {"gpr": 5}), ("rocks0", {"rocks": 0})]
INJECT_PERIODS = [40, 60, 84, 100, 150, 300, 600, 1000, 2000]
INJECT_AMPS = [0.02, 0.05, 0.10, 0.20]


def cmd_inject(_args=None):
    rows = []
    for label, extra in INJECT_CONFIGS:
        c = dict(BASE, **extra)
        for seed in SEEDS:
            series = _series_for(c, seed)
            for per in INJECT_PERIODS:
                for amp in INJECT_AMPS:
                    mod = [(g, max(0, round(r * (1 + amp * math.sin(2 * math.pi * g / per)))),
                            max(0, round(f * (1 + amp * math.sin(2 * math.pi * (g - per / 4) / per)))))
                           for g, r, f in series]
                    a = analyze(mod)
                    hits = [p for p in (a["rabbit_period"], a["fox_period"]) if p and abs(p - per) <= 0.15 * per]
                    rows.append(dict(config=label, seed=seed, period=per, amp=amp, detected=int(bool(hits)),
                                     found_rabbit=a["rabbit_period"] or "", found_fox=a["fox_period"] or "",
                                     fox_lag=a["fox_lag"] if a["fox_lag"] is not None else "", expected_lag=per // 4,
                                     lag_ok=int(a["fox_lag"] is not None and
                                                abs(a["fox_lag"] - per / 4) <= max(3, 0.15 * per / 4))))
    _write_rows(INJECT_CSV, list(rows[0]), rows)
    print("injection (detected / total over %d configs x %d seeds):" % (len(INJECT_CONFIGS), len(SEEDS)))
    print("period \\ amp " + " ".join(f"{int(a * 100):>5}%" for a in INJECT_AMPS))
    for per in INJECT_PERIODS:
        cells = []
        for amp in INJECT_AMPS:
            sel = [r for r in rows if r["period"] == per and r["amp"] == amp]
            cells.append(f"{sum(r['detected'] for r in sel):>2}/{len(sel)}")
        print(f"{per:>12} " + " ".join(f"{c:>6}" for c in cells))
    det = [r for r in rows if r["detected"] and r["amp"] >= 0.10]
    print("lag within 15%% of the injected one (or 3 generations), detections with amp >= 10%%: %d of %d"
          % (sum(r["lag_ok"] for r in det), len(det)))
    return rows


def cmd_sensitivity(_args=None):
    """How many sweep runs report a slow period at other thresholds."""
    rows = []
    for _s, p, v, c in configs():
        if _s == "long":
            continue
        for seed in SEEDS:
            series = _series_for(c, seed)
            for th in (0.5, 0.3, 0.2, 0.1):
                a = analyze(series, threshold=th)
                rows.append(dict(threshold=th, param=p or "base", value="" if v is None else v, seed=seed,
                                 rabbit_period=a["rabbit_period"] or "", fox_period=a["fox_period"] or "",
                                 fox_lag=a["fox_lag"] if a["fox_lag"] is not None else ""))
    _write_rows(SENS_CSV, list(rows[0]), rows)
    for th in (0.5, 0.3, 0.2, 0.1):
        sel = [r for r in rows if r["threshold"] == th]
        print(f"threshold {th}: {sum(bool(r['rabbit_period'] or r['fox_period']) for r in sel)} of {len(sel)} runs")
    # False-positive rate on red noise (AR(1), phi 0.99), the kind of series most likely to fake a cycle.
    for n in (6000, 10000):
        fp = 0
        for seed in range(150):
            rng = random.Random(seed)
            r = f = 0.0
            ser = []
            for t in range(n):
                r, f = 0.99 * r + rng.gauss(0, 10), 0.99 * f + rng.gauss(0, 5)
                ser.append((t, round(1000 + r), round(300 + f)))
            a = analyze(ser)
            fp += bool(a["rabbit_period"] or a["fox_period"])
        print(f"red noise, {n} generations: {fp} of 150 series report a slow cycle")


def plot_transient(plt):
    """First 400 generations of three runs (the overshoot after the start)."""
    items = [("Base (semilla 1)", dict(BASE)), ("Hambre 20 (semilla 1)", dict(BASE, gff=20)),
             ("Sin rocas (semilla 1)", dict(BASE, rocks=0))]
    fig, axes = plt.subplots(1, 3, figsize=(7.6, 3.4), sharey=False)
    for ax, (title, c) in zip(axes, items):
        series = _series_for(c, 1)[:401]
        g = np.array([r[0] for r in series])
        for col, color in ((1, RABBIT_COLOR), (2, FOX_COLOR)):
            y = np.array([r[col] for r in series], dtype=float)
            ax.plot(g, y, color=color, lw=0.5, alpha=0.3)
            w = 21  # display only: spans one period of the foxes and five of the rabbits
            s = _boxcar(y, w)
            ax.plot(g[:len(s)] + (w - 1) / 2, s, color=color, lw=1.8)
        ax.set_yscale("log")
        ax.set_ylim(80, 6000)
        ax.set_title(title, loc="left", fontsize=9.5)
        ax.set_xlabel("Generación")
        ax.set_xticks([0, 200, 400])
        _fmt_int(ax)
    axes[0].set_ylabel("Individuos (escala log)")
    from matplotlib.lines import Line2D
    fig.legend(handles=[Line2D([], [], color=RABBIT_COLOR, lw=1.8, label="Conejos"),
                        Line2D([], [], color=FOX_COLOR, lw=1.8, label="Zorros"),
                        Line2D([], [], color=GREY, lw=0.6, alpha=0.6, label="Serie cruda"),
                        Line2D([], [], color=GREY, lw=1.8, label="Media móvil de 21 gen. (solo para ver)")],
               loc="lower center", ncol=4, frameon=False, bbox_to_anchor=(0.5, -0.01))
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.savefig(os.path.join(FIGS, "eco_transitorio.png"))
    plt.close(fig)


def cmd_plot():
    plt = _plot_style()
    os.makedirs(FIGS, exist_ok=True)
    plot_base(plt)

    def cfg(**kw):
        return dict(BASE, **kw)
    plot_grid(plt, [("Sin rocas (0 %)", cfg(rocks=0), 1), ("5 % de rocas (base)", cfg(), 1),
                    ("15 % de rocas", cfg(rocks=1500), 1), ("30 % de rocas", cfg(rocks=3000), 1)],
              2, "eco_series_rocas.png", (7.2, 6.0))
    plot_grid(plt, [("Periodo de conejos 5", cfg(gpr=5), 1), ("Periodo de conejos 8", cfg(gpr=8), 1),
                    ("Periodo de zorros 5", cfg(gpf=5), 1), ("Periodo de zorros 10", cfg(gpf=10), 1),
                    ("Periodo de zorros 40", cfg(gpf=40), 1), ("Hambre 3", cfg(gff=3), 1)],
              3, "eco_series_parametros.png", (7.6, 5.4))
    plot_stability(plt)
    plot_transient(plt)
    print("figures ->", FIGS)


if __name__ == "__main__":
    main()
