#!/usr/bin/env python3
"""Population-dynamics experiments for the ecosystem simulation.

Subcommands:
  run      run the sweeps with eco_seq, write one CSV per run and the summary table
  summary  (re)build ecosystem_summary.csv from the per-run CSVs
  plot     draw the figures docs/report/figuras/eco_*.png

analyze() is the analysis used by every subcommand. It is pure (no I/O) so it can be tested with
synthetic signals.
"""
import math

import numpy as np

# An autocorrelation peak counts as a cycle only if it reaches this value (and, for the slow cycle,
# the autocorrelation has gone below zero before it). Below it analyze() returns None.
CYCLE_THRESHOLD = 0.3
# Share of the series dropped as transient before any analysis.
TRANSIENT_FRACTION = 0.2
# A raw period up to this many generations is "fast": it is removed (by a moving average) before
# looking for the slow cycle. The reproduction periods of the sweeps (GEN_PROC + 1) are below it.
FAST_MAX = 50
# Longest moving-average window used to remove the fast periods.
MAX_WINDOW = 200


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


def _peak_lag(ac, threshold, need_zero_cross):
    """Lag of the first autocorrelation peak that is a local maximum, reaches threshold and is
    within 80% of the highest such peak (so a small bump on the flank of a peak does not win).
    Searches up to a third of the series so that at least three repetitions back the period."""
    if ac is None:
        return None, None
    max_lag = len(ac) // 3
    peaks = [k for k in range(2, max_lag) if ac[k] > ac[k - 1] and ac[k] >= ac[k + 1] and ac[k] >= threshold]
    if need_zero_cross:
        peaks = [k for k in peaks if ac[1:k].min() < 0]
    if not peaks:
        return None, None
    best = max(ac[k] for k in peaks)
    k = next(k for k in peaks if ac[k] >= 0.8 * best)
    return k, float(ac[k])


def _boxcar(x, w):
    return np.convolve(x, np.ones(w) / w, mode="valid") if w > 1 else x


def _lcm_window(periods):
    w = 1
    for p in periods:
        w = w * p // math.gcd(w, p)
    if w > MAX_WINDOW:
        m = max(periods)
        w = m * max(1, MAX_WINDOW // m)
    return w


def _first_zero(series, col):
    for row in series:
        if row[col] == 0:
            return row[0]
    return None


def analyze(series, threshold=CYCLE_THRESHOLD, transient=TRANSIENT_FRACTION, fast_max=FAST_MAX):
    """series: rows (gen, rabbits, foxes), as in the engine's --stats-file.

    Returns a dict:
      extinct_rabbits_gen, extinct_foxes_gen  first generation with 0 animals, or None
      coexist                                 both species alive in the last generation
      rabbit_raw_period, fox_raw_period       first autocorrelation peak >= threshold of the raw
                                              series (this is the fast oscillation if there is one)
      rabbit_period, fox_period               period of the slow cycle: the same on the series
                                              after the fast periods are removed with a moving
                                              average, and the autocorrelation must have been
                                              negative before the peak. None if no peak >= threshold
      rabbit_acf, fox_acf                     height of that slow peak (None if no cycle)
      fox_lag                                 generations by which the foxes' slow cycle trails the
                                              rabbits' (cross-correlation maximum), None unless both
                                              species have a slow cycle
      fast_window                             moving-average window used (1 = none)
      rabbit_cv, fox_cv                       std/mean of the smoothed series (cycle amplitude)
    The first `transient` of the series is discarded. Without coexistence the periods are None.
    """
    rows = list(series)
    out = dict(extinct_rabbits_gen=_first_zero(rows, 1), extinct_foxes_gen=_first_zero(rows, 2),
               coexist=bool(rows) and rows[-1][1] > 0 and rows[-1][2] > 0,
               rabbit_raw_period=None, fox_raw_period=None, rabbit_period=None, fox_period=None,
               rabbit_acf=None, fox_acf=None, fox_lag=None, fast_window=1, rabbit_cv=None, fox_cv=None)
    if not out["coexist"]:
        return out
    cut = int(len(rows) * transient)
    r = np.array([x[1] for x in rows[cut:]], dtype=float)
    f = np.array([x[2] for x in rows[cut:]], dtype=float)
    if len(r) < 12:
        return out

    raw = {}
    for name, x in (("rabbit", r), ("fox", f)):
        raw[name], _ = _peak_lag(_acf(x), threshold, need_zero_cross=False)
        out[name + "_raw_period"] = raw[name]

    fast = sorted({p for p in raw.values() if p is not None and p <= fast_max})
    w = _lcm_window(fast) if fast else 1
    out["fast_window"] = w
    rs, fs = _boxcar(r, w), _boxcar(f, w)
    if len(rs) < 12:
        return out
    for name, x in (("rabbit", rs), ("fox", fs)):
        out[name + "_period"], out[name + "_acf"] = _peak_lag(_acf(x), threshold, need_zero_cross=True)
        out[name + "_cv"] = float(np.std(x) / np.mean(x))

    if out["rabbit_period"] is not None and out["fox_period"] is not None:
        a, b = rs - rs.mean(), fs - fs.mean()
        half = out["rabbit_period"] // 2
        best_lag, best = None, -2.0
        for lag in range(-half, half + 1):
            x, y = (a[:len(a) - lag], b[lag:]) if lag >= 0 else (a[-lag:], b[:len(b) + lag])
            c = float(np.dot(x, y) / (np.linalg.norm(x) * np.linalg.norm(y)))
            if c > best:
                best_lag, best = lag, c
        out["fox_lag"] = best_lag
    return out


# ---------------------------------------------------------------------------------------------
# Experiments: sweeps, summary table and figures. Everything below needs the built engine.
# ---------------------------------------------------------------------------------------------
import argparse  # noqa: E402
import csv  # noqa: E402
import os  # noqa: E402
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
          "fox_lag", "fast_window", "rabbit_cv", "fox_cv", "rabbit_mean", "fox_mean", "file"]


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
              "rabbit_period", "fox_period", "fox_lag", "fast_window"):
        row[k] = a[k]
    for k in ("rabbit_acf", "fox_acf", "rabbit_cv", "fox_cv"):
        row[k] = "" if a[k] is None else round(a[k], 4)
    return {k: ("" if v is None else v) for k, v in row.items()}


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


def _smoothed(series, col, w):
    x = np.array([r[col] for r in series], dtype=float)
    s = _boxcar(x, w)
    return np.arange(len(s)) + (w - 1) / 2, s


def _fmt_int(ax, axis="y"):
    import matplotlib.ticker as mt
    f = mt.FuncFormatter(lambda v, _: f"{v:,.0f}".replace(",", "."))
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(f)


def _panel(ax, series, title):
    """Both species in one panel on a log axis (same unit, very different sizes): the raw series
    faint and the series without the fast periods (moving average) in full color."""
    a = analyze(series)
    w = a["fast_window"]
    g = np.array([r[0] for r in series])
    for col, color in ((1, RABBIT_COLOR), (2, FOX_COLOR)):
        y = np.array([r[col] for r in series], dtype=float)
        ax.plot(g, np.maximum(y, 0.8), color=color, lw=0.5, alpha=0.28)
        if w > 1 and len(y) > w:
            x, s = _smoothed(series, col, w)
            ax.plot(x, np.maximum(s, 0.8), color=color, lw=1.8)
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
               Line2D([], [], color=GREY, lw=1.8, label="Sin periodos cortos (media móvil)")]
    fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False, bbox_to_anchor=(0.5, -0.01))


def plot_base(plt):
    series = _series_for(dict(BASE), 1)
    w = analyze(series)["fast_window"]
    g = np.array([r[0] for r in series])
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.2), gridspec_kw=dict(width_ratios=[2.2, 1]))
    for row, (col, name, color) in enumerate(((1, "Conejos", RABBIT_COLOR), (2, "Zorros", FOX_COLOR))):
        y = np.array([r[col] for r in series], dtype=float)
        ax, z = axes[row]
        ax.plot(g, y, color=color, lw=0.5, alpha=0.3)
        x, s = _smoothed(series, col, w)
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
                        Line2D([], [], color=GREY, lw=1.8, label=f"Media móvil de {w} gen. (sin periodos cortos)")],
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
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(os.path.join(FIGS, name))
    plt.close(fig)


def plot_stability(plt):
    """One column per swept parameter. Top: seeds (of 3) where both species are alive at the end.
    Bottom: relative amplitude (std/mean) of the series without the fast periods, one dot per
    seed; a black ring marks a slow cycle found by analyze()."""
    rows = [r for r in csv.DictReader(open(SUMMARY)) if r["sweep"] != "long"]
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
            for off, col, color, pcol in ((-0.12, "rabbit_cv", RABBIT_COLOR, "rabbit_period"),
                                          (0.12, "fox_cv", FOX_COLOR, "fox_period")):
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
            bot.set_ylabel("Amplitud relativa (desv./media)")
        else:
            bot.tick_params(labelleft=False)
            top.tick_params(labelleft=False)
    from matplotlib.lines import Line2D
    fig.legend(handles=[Line2D([], [], marker="o", ls="", color=RABBIT_COLOR, label="Conejos"),
                        Line2D([], [], marker="o", ls="", color=FOX_COLOR, label="Zorros"),
                        Line2D([], [], marker="o", ls="", color="white", mec="black", mew=1.6,
                               label="Ciclo lento detectado")],
               loc="lower center", ncol=3, frameon=False, bbox_to_anchor=(0.5, -0.005))
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(os.path.join(FIGS, "eco_estabilidad.png"))
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
    print("figures ->", FIGS)


if __name__ == "__main__":
    main()
