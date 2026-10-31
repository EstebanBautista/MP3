#!/usr/bin/env python3
"""Performance figures (Spanish labels) from the measurement CSVs.

Usage: plot_performance.py [--csv performance.csv] [--suffix ""] [--platform "Windows 10 nativo"]
Writes docs/report/figuras/perf_<name><suffix>.png. Barrier figure: --barriers barriers.csv.
"""
import argparse
import csv
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from measure import LARGE_NAME, quartiles, read_csv, summarize  # noqa: E402

RESULTS = os.path.join(HERE, "results")
FIGS = os.path.join(os.path.dirname(HERE), "docs", "report", "figuras")

# Categorical palette for a light surface, fixed order per series.
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e1e0d9", "#fcfcfb"
SERIES = {  # key -> (label, color, marker)
    ("seq", "-"): ("Secuencial", "#2a78d6", "o"),
    ("pth", "-"): ("Pthreads", "#eb6834", "s"),
    ("omp", "adaptive"): ("OpenMP adaptativo", "#1baf7a", "^"),
    ("omp", "static"): ("OpenMP estático", "#eda100", "D"),
}
CASE_TITLES = {
    "20x20": "Mundo 20x20", "100x100": "Mundo 100x100", "200x200": "Mundo 200x200",
    "100x100_unbal01": "100x100 desequil. 01", "100x100_unbal02": "100x100 desequil. 02",
    LARGE_NAME: "Mundo 1000x1000",
}
THREADS = [1, 2, 4, 8, 16]
PHYSICAL = 8


def style():
    plt.rcParams.update({
        "font.size": 9, "axes.titlesize": 10, "axes.labelsize": 9, "legend.fontsize": 8,
        "axes.facecolor": SURFACE, "figure.facecolor": "white", "axes.edgecolor": "#c3c2b7",
        "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
        "axes.spines.top": False, "axes.spines.right": False, "lines.linewidth": 1.8,
        "lines.markersize": 5.5, "savefig.dpi": 200,
    })


def cores_marker(ax):
    """Dotted line at 8 physical cores; named in the legend so no text sits over the data."""
    ax.axvline(PHYSICAL, color="#898781", lw=1, ls=":", label="8 núcleos físicos")


def thread_axis(ax):
    ax.set_xscale("log", base=2)
    ax.set_xticks(THREADS)
    ax.set_xticklabels([str(t) for t in THREADS])
    ax.minorticks_off()
    ax.set_xlabel("Hilos (9 a 16 son lógicos, SMT)")


def grid_figure(cases, title):
    cols = 3 if len(cases) > 3 else len(cases)
    rows = (len(cases) + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(7.2, 2.5 * rows + 0.8), squeeze=False)
    fig.suptitle(title, fontsize=11, fontweight="bold")
    flat = [a for r in axes for a in r]
    for ax in flat[len(cases):]:
        ax.axis("off")
    return fig, flat


def legend(fig, handles_from, ncol=5):
    h, l = handles_from.get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=ncol, frameon=False)


def get(stats, key, case):
    rows = [s for s in stats if (s["design"], s["mode"]) == key and s["case"] == case]
    return sorted(rows, key=lambda s: s["threads"])


def present_cases(stats, wanted):
    have = {s["case"] for s in stats}
    return [c for c in wanted if c in have]


def fig_speedup(stats, cases, platform, path):
    fig, axes = grid_figure(cases, f"Aceleración respecto a eco_seq — {platform}")
    for ax, case in zip(axes, cases):
        seq = get(stats, ("seq", "-"), case)
        if not seq:
            continue
        s0 = seq[0]["wall_median"]
        ax.plot(THREADS, THREADS, color="#898781", ls="--", lw=1.2, label="Ideal")
        for key in (("pth", "-"), ("omp", "adaptive"), ("omp", "static")):
            rows = get(stats, key, case)
            lab, col, mk = SERIES[key]
            ax.plot([r["threads"] for r in rows], [s0 / r["wall_median"] for r in rows],
                    color=col, marker=mk, label=lab)
        cores_marker(ax)
        thread_axis(ax)
        ax.set_yscale("log", base=2)
        low = min(s0 / r["wall_median"] for k in (("pth", "-"), ("omp", "adaptive"), ("omp", "static"))
                  for r in get(stats, k, case))
        ticks = [t for t in (0.03, 0.06, 0.125, 0.25, 0.5, 1, 2, 4, 8, 16) if t >= min(0.4, low / 1.5) / 1.1]
        ax.set_yticks(ticks)
        ax.set_yticklabels([f"{t:g}".replace(".", ",") for t in ticks])
        ax.set_ylim(min(0.4, low / 1.5), 18)
        ax.set_title(CASE_TITLES.get(case, case))
        ax.set_ylabel("Aceleración (T_seq / T)")
    legend(fig, axes[0])
    fig.tight_layout(rect=(0, 0.06, 1, 0.93))
    fig.savefig(path)
    plt.close(fig)


def fig_efficiency(stats, cases, platform, path):
    fig, axes = grid_figure(cases, f"Eficiencia respecto a eco_seq — {platform}")
    for ax, case in zip(axes, cases):
        seq = get(stats, ("seq", "-"), case)
        if not seq:
            continue
        s0 = seq[0]["wall_median"]
        ax.axhline(1.0, color="#898781", ls="--", lw=1.2, label="Ideal")
        for key in (("pth", "-"), ("omp", "adaptive"), ("omp", "static")):
            rows = get(stats, key, case)
            lab, col, mk = SERIES[key]
            ax.plot([r["threads"] for r in rows], [s0 / r["wall_median"] / r["threads"] for r in rows],
                    color=col, marker=mk, label=lab)
        cores_marker(ax)
        thread_axis(ax)
        ax.set_ylim(0, 1.15)
        ax.set_title(CASE_TITLES.get(case, case))
        ax.set_ylabel("Eficiencia (aceleración / hilos)")
    legend(fig, axes[0])
    fig.tight_layout(rect=(0, 0.06, 1, 0.93))
    fig.savefig(path)
    plt.close(fig)


def fig_wall_cpu(stats, cases, platform, path):
    fig, axes = grid_figure(cases, f"Tiempo total frente a tiempo de CPU — {platform}")
    for ax, case in zip(axes, cases):
        for key in (("pth", "-"), ("omp", "adaptive"), ("omp", "static")):
            rows = get(stats, key, case)
            lab, col, mk = SERIES[key]
            xs = [r["threads"] for r in rows]
            ax.plot(xs, [r["wall_median"] for r in rows], color=col, marker=mk, label=lab + " (total)")
            ax.plot(xs, [r["cpu_median"] for r in rows], color=col, marker=mk, ls="--", lw=1.2,
                    markerfacecolor="white", label=lab + " (CPU)")
        cores_marker(ax)
        thread_axis(ax)
        ax.set_yscale("log")
        ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}".replace(".", ",")))
        ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
        ax.set_title(CASE_TITLES.get(case, case))
        ax.set_ylabel("Segundos (escala log.)")
    legend(fig, axes[0], ncol=4)
    fig.tight_layout(rect=(0, 0.1, 1, 0.95), w_pad=1.5)
    fig.savefig(path)
    plt.close(fig)


def fig_imbalance(stats, cases, platform, path):
    fig, axes = grid_figure(cases, f"Desequilibrio, estático frente a adaptativo — {platform}")
    for ax, case in zip(axes, cases):
        for key in (("omp", "static"), ("omp", "adaptive")):
            rows = [r for r in get(stats, key, case) if r["threads"] > 1]
            lab, col, mk = SERIES[key]
            ax.plot([r["threads"] for r in rows], [r["imbalance_median"] for r in rows],
                    color=col, marker=mk, label=lab)
        ax.axhline(1.0, color="#898781", ls="--", lw=1.2, label="Equilibrio perfecto")
        cores_marker(ax)
        thread_axis(ax)
        ax.set_title(CASE_TITLES.get(case, case))
        ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.2f}".replace(".", ",")))
        ax.set_xlim(1.6, 18)
        ax.set_ylabel("Desequilibrio")
    legend(fig, axes[0], ncol=4)
    fig.tight_layout(rect=(0, 0.06, 1, 0.93))
    fig.savefig(path)
    plt.close(fig)


def fig_barriers(path_csv, path):
    rows = read_csv(path_csv)
    fig, ax = plt.subplots(figsize=(5.2, 3.4))
    for design, (lab, col, mk) in (("pth", SERIES[("pth", "-")]), ("omp", SERIES[("omp", "adaptive")])):
        label = "Pthreads (pthread_barrier)" if design == "pth" else "OpenMP (omp barrier)"
        by = {}
        for r in rows:
            if r["design"] == design:
                by.setdefault(int(r["threads"]), []).append(float(r["us_per_barrier"]))
        ts = sorted(by)
        med = [quartiles(by[t])[1] for t in ts]
        lo = [min(by[t]) for t in ts]
        hi = [max(by[t]) for t in ts]
        ax.errorbar(ts, med, yerr=[[m - a for m, a in zip(med, lo)], [b - m for m, b in zip(med, hi)]],
                    color=col, marker=mk, capsize=3, label=label)
    cores_marker(ax)
    thread_axis(ax)
    ax.set_xticks([2, 4, 8, 16])
    ax.set_xticklabels(["2", "4", "8", "16"])
    ax.set_ylabel("Microsegundos por barrera")
    ax.set_title("Coste de una barrera vacía (mediana, mín–máx)")
    ax.legend(frameon=False)
    ax.set_ylim(bottom=0)
    ax.set_xlim(1.6, 18)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default=os.path.join(RESULTS, "performance.csv"))
    p.add_argument("--barriers", default=os.path.join(RESULTS, "barriers.csv"))
    p.add_argument("--suffix", default="")
    p.add_argument("--platform", default="Windows 10 nativo")
    p.add_argument("--only", nargs="*", default=None, help="subset: speedup efficiency wall imbalance barriers")
    a = p.parse_args()
    style()
    os.makedirs(FIGS, exist_ok=True)
    want = lambda n: a.only is None or n in a.only  # noqa: E731
    out = lambda n: os.path.join(FIGS, f"perf_{n}{a.suffix}.png")  # noqa: E731
    if os.path.exists(a.csv):
        stats = summarize(read_csv(a.csv))
        order = ["20x20", "100x100", "200x200", "100x100_unbal01", "100x100_unbal02", LARGE_NAME]
        cases = present_cases(stats, order)
        if want("speedup"):
            fig_speedup(stats, cases, a.platform, out("aceleracion"))
        if want("efficiency"):
            fig_efficiency(stats, cases, a.platform, out("eficiencia"))
        if want("wall"):
            fig_wall_cpu(stats, cases, a.platform, out("tiempo_cpu"))
        if want("imbalance"):
            icases = present_cases(stats, ["100x100_unbal01", "100x100_unbal02", "200x200", LARGE_NAME])
            fig_imbalance(stats, icases, a.platform, out("desequilibrio"))
    if want("barriers") and os.path.exists(a.barriers) and not a.suffix:
        fig_barriers(a.barriers, out("barreras"))


if __name__ == "__main__":
    main()
