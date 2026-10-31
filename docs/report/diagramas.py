"""Draws the architecture diagrams of the report into figuras/diag_*.png.

They are schematics, except for diag_cortes, which applies the formula of engine/bands.hpp
(fillRowCosts and adaptiveBands) to a real input file.
"""
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FIGS = os.path.join(HERE, "figuras")

INK = "#20303c"
MUTED = "#5d6b75"
BLUE = "#2a78d6"
BLUE_LIGHT = "#d9e8f8"
ORANGE = "#e8622c"
ORANGE_LIGHT = "#fbe3d8"
GREEN = "#1baf7a"
GREEN_LIGHT = "#d6f2e7"
GREY_LIGHT = "#edf0f2"
BAND_COLORS = ["#d9e8f8", "#fbe3d8", "#d6f2e7", "#f6edc9"]
BARRIER = "#20303c"


def canvas(width, height):
    fig, ax = plt.subplots(figsize=(width, height))
    ax.set_xlim(0, width)
    ax.set_ylim(0, height)
    ax.axis("off")
    fig.subplots_adjust(0, 0, 1, 1)
    return fig, ax


def box(ax, x, y, w, h, text, fill=GREY_LIGHT, edge=INK, size=9, weight="normal", color=INK):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.06",
                                linewidth=1.0, edgecolor=edge, facecolor=fill))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=size, color=color,
            fontweight=weight, linespacing=1.35)


def arrow(ax, start, end, text=None, color=INK, size=8, offset=(0, 0.1), style="-|>", rad=0.0):
    ax.add_patch(FancyArrowPatch(start, end, arrowstyle=style, mutation_scale=11, linewidth=1.1,
                                 color=color, connectionstyle="arc3,rad=%g" % rad, shrinkA=0, shrinkB=0))
    if text:
        ax.text((start[0] + end[0]) / 2 + offset[0], (start[1] + end[1]) / 2 + offset[1], text,
                ha="center", va="bottom", fontsize=size, color=color, linespacing=1.25)


def save(fig, name):
    fig.savefig(os.path.join(FIGS, name), dpi=220)
    plt.close(fig)


def diagram_system():
    fig, ax = canvas(7.6, 2.05)
    box(ax, 0.1, 0.55, 1.75, 1.0, "Navegador\nindex.html, app.js\ncanvas", BLUE_LIGHT)
    box(ax, 2.95, 0.55, 1.75, 1.0, "web/server.py\nPython, solo\nbiblioteca estándar", GREEN_LIGHT)
    box(ax, 5.8, 0.55, 1.7, 1.0, "Motor C++\neco_seq --frames\n(proceso aparte)", ORANGE_LIGHT)
    arrow(ax, (1.85, 1.28), (2.95, 1.28), "POST /api/start\nGET /api/frames", size=7.5, offset=(0, 0.04))
    arrow(ax, (2.95, 0.82), (1.85, 0.82), "cuadros binarios", size=7.5, offset=(0, -0.26))
    arrow(ax, (4.7, 1.28), (5.8, 1.28), "stdin: mundo", size=7.5, offset=(0, 0.04))
    arrow(ax, (5.8, 0.82), (4.7, 0.82), "stdout: cuadros", size=7.5, offset=(0, -0.26))
    save(fig, "diag_sistema.png")


def small_grid(ax, x, y, size, label, fill):
    cells = 5
    step = size / cells
    for i in range(cells):
        for j in range(cells):
            ax.add_patch(Rectangle((x + i * step, y + j * step), step, step, facecolor=fill,
                                   edgecolor="white", linewidth=0.8))
    ax.text(x + size / 2, y - 0.08, label, ha="center", va="top", fontsize=8.5, color=INK, linespacing=1.3)


def diagram_subphases():
    fig, ax = canvas(7.6, 2.5)
    y = 0.85
    small_grid(ax, 0.2, y, 1.25, "cur\nestado al empezar G", GREY_LIGHT)
    box(ax, 1.85, y + 0.12, 1.45, 1.0, "Subfase de\nconejos\ndecideRabbit\nmergeRabbit", BLUE_LIGHT, size=8.2)
    small_grid(ax, 3.7, y, 1.25, "next\nconejos ya movidos", BLUE_LIGHT)
    box(ax, 5.35 - 0.0, y + 0.12, 1.45, 1.0, "Subfase de\nzorros\ndecideFox\nmergeFox", ORANGE_LIGHT, size=8.2)
    arrow(ax, (1.45, y + 0.62), (1.85, y + 0.62))
    arrow(ax, (3.3, y + 0.62), (3.7, y + 0.62))
    arrow(ax, (4.95, y + 0.62), (5.35, y + 0.62))
    arrow(ax, (6.8, y + 0.62), (7.3, y + 0.62))
    ax.text(7.32, y + 0.87, "G+1", ha="right", va="bottom", fontsize=8.5, color=INK)
    ax.text(3.8, 2.33, "Cada subfase lee solo el estado anterior y escribe un arreglo nuevo: "
            "el orden en que se procesan los animales no cambia el resultado.",
            ha="center", va="center", fontsize=8, color=MUTED)
    save(fig, "diag_subfases.png")


def diagram_bands():
    fig, ax = canvas(7.6, 3.75)
    ax.text(0.15, 3.6, "Reparto: bandas de filas y buzones", fontsize=9, fontweight="bold", color=INK, va="center")
    left, top, width, height = 0.15, 3.3, 1.75, 2.8
    bands = 4
    for t in range(bands):
        y = top - height * (t + 1) / bands
        ax.add_patch(Rectangle((left, y), width, height / bands, facecolor=BAND_COLORS[t],
                               edgecolor=INK, linewidth=0.8))
        ax.text(left + width / 2, y + height / bands / 2, "banda del hilo %d" % t, ha="center",
                va="center", fontsize=8, color=INK)
    # A move that crosses from band 1 to band 2 goes to a box, not to the grid.
    ax.plot([left + 1.4], [top - height / 2 + 0.17], "o", color=ORANGE, markersize=5)
    box(ax, 2.2, 1.08, 1.1, 0.75, "MoveBox\norigen 1\ndestino 2", ORANGE_LIGHT, size=8)
    arrow(ax, (left + 1.45, top - height / 2 + 0.15), (2.2, 1.6), rad=-0.15, color=ORANGE)
    arrow(ax, (2.2, 1.28), (left + 1.45, top - height / 2 - 0.35), rad=-0.15, color=ORANGE)
    ax.text(2.75, 2.25, "movimiento\nque cruza\nla frontera", ha="center", fontsize=7.8, color=MUTED, va="center")
    ax.text(2.75, 0.75, "se aplica tras\nla barrera", ha="center", fontsize=7.8, color=MUTED, va="center")

    ax.text(3.65, 3.6, "Tiempo de una subfase (esquema, no a escala)", fontsize=9, fontweight="bold", color=INK, va="center")
    x0 = 4.05
    lengths = [(1.18, 0.5), (0.95, 0.42), (1.3, 0.55), (1.05, 0.34)]
    barrier1 = x0 + 1.42
    barrier2 = barrier1 + 0.85
    for t, (local, inbound) in enumerate(lengths):
        y = 2.72 - t * 0.5
        ax.text(x0 - 0.1, y + 0.16, "H%d" % t, ha="right", va="center", fontsize=8, color=INK)
        ax.add_patch(Rectangle((x0, y), local, 0.32, facecolor=BLUE_LIGHT, edgecolor=INK, linewidth=0.7))
        ax.add_patch(Rectangle((barrier1 + 0.08, y), inbound, 0.32, facecolor=GREEN_LIGHT, edgecolor=INK, linewidth=0.7))
        ax.plot([x0 + local, barrier1], [y + 0.16, y + 0.16], color=MUTED, linewidth=0.8, linestyle=":")
        ax.plot([barrier1 + 0.08 + inbound, barrier2], [y + 0.16, y + 0.16], color=MUTED, linewidth=0.8, linestyle=":")
    for x in (barrier1, barrier2):
        ax.plot([x, x], [1.1, 3.17], color=BARRIER, linewidth=2)
        ax.text(x, 3.22, "barrera", ha="center", va="bottom", fontsize=7.5, color=INK)
    ax.add_patch(Rectangle((3.72, 0.62), 0.25, 0.16, facecolor=BLUE_LIGHT, edgecolor=INK, linewidth=0.7))
    ax.text(4.02, 0.7, "pasada local: decide y entrega dentro de la banda", va="center", fontsize=7.8, color=INK)
    ax.add_patch(Rectangle((3.72, 0.34), 0.25, 0.16, facecolor=GREEN_LIGHT, edgecolor=INK, linewidth=0.7))
    ax.text(4.02, 0.42, "pasada de entrada: aplica los buzones dirigidos al hilo", va="center", fontsize=7.8, color=INK)
    ax.plot([3.72, 3.97], [0.14, 0.14], color=MUTED, linewidth=0.8, linestyle=":")
    ax.text(4.02, 0.14, "espera en la barrera", va="center", fontsize=7.8, color=INK)
    save(fig, "diag_bandas.png")


def static_bands(rows, threads):
    cuts = [0]
    next_row = 0
    for t in range(threads):
        next_row += rows // threads + (1 if t < rows % threads else 0)
        cuts.append(next_row)
    return cuts


def adaptive_bands(costs, threads):
    """adaptiveBands of engine/bands.hpp."""
    rows = len(costs)
    remaining = sum(costs)
    if remaining == 0:
        return static_bands(rows, threads)
    next_row = 0
    cuts = [0]
    for t in range(threads):
        left = threads - t
        if left == 1:
            next_row = rows
        elif next_row < rows:
            limit = rows - (left - 1)
            share = remaining / left
            total = costs[next_row]
            next_row += 1
            while next_row < limit and abs(total + costs[next_row] - share) < abs(total - share):
                total += costs[next_row]
                next_row += 1
            remaining -= total
        cuts.append(next_row)
    return cuts


def row_costs(path, weight):
    """fillRowCosts of engine/bands.hpp, on the world of an input file."""
    with open(path) as f:
        head = f.readline().split()
        rows, cols = int(head[4]), int(head[5])
        animals = [0] * rows
        for line in f:
            kind, x, _y = line.split()
            if kind in ("RABBIT", "FOX"):
                animals[int(x)] += 1
    return [cols + weight * a for a in animals]


def diagram_cuts():
    source = os.path.join(ROOT, "ecosystem_examples", "input100x100_unbal01")
    # OmpSimulator::ANIMAL_WEIGHT and 8 threads, as in the bands test of the project.
    costs = row_costs(source, 8)
    threads = 8
    fig, axes = plt.subplots(1, 2, figsize=(7.6, 2.75), sharey=True)
    rows = range(len(costs))
    for ax, cuts, title in ((axes[0], static_bands(len(costs), threads), "staticBands"),
                            (axes[1], adaptive_bands(costs, threads), "adaptiveBands")):
        ax.fill_between(rows, costs, step="mid", color=BLUE_LIGHT, linewidth=0)
        ax.step(rows, costs, where="mid", color=BLUE, linewidth=0.9)
        for cut in cuts[1:-1]:
            ax.axvline(cut - 0.5, color=ORANGE, linewidth=1.1)
        loads = [sum(costs[a:b]) for a, b in zip(cuts, cuts[1:])]
        ax.set_title("%s: banda más cara / media = %.2f" % (title, max(loads) * threads / sum(loads)),
                     fontsize=9, color=INK)
        ax.set_xlabel("Fila", fontsize=8.5, color=INK)
        ax.tick_params(labelsize=8, colors=MUTED)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.set_xlim(0, len(costs))
        ax.set_ylim(bottom=0)
    axes[0].set_ylabel("Coste estimado de la fila", fontsize=8.5, color=INK)
    fig.tight_layout()
    save(fig, "diag_cortes.png")


def make_all():
    diagram_system()
    diagram_subphases()
    diagram_bands()
    diagram_cuts()


if __name__ == "__main__":
    make_all()
