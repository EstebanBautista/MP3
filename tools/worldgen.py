"""Generates a random world in the engine's input format."""
import random


def generate_world(seed: int, rows: int, cols: int, rabbits: int, foxes: int, rocks: int,
                   gen_proc_rabbits: int, gen_proc_foxes: int, gen_food_foxes: int, n_gen: int) -> str:
    """Returns the input text. The same arguments always produce the same world."""
    if rows <= 0 or cols <= 0:
        raise ValueError("rows and cols must be positive")
    if min(rabbits, foxes, rocks) < 0:
        raise ValueError("populations cannot be negative")
    total = rabbits + foxes + rocks
    if total > rows * cols:
        raise ValueError(f"{total} objects do not fit in {rows * cols} cells")

    cells = random.Random(seed).sample(range(rows * cols), total)
    kinds = ["ROCK"] * rocks + ["RABBIT"] * rabbits + ["FOX"] * foxes
    lines = [f"{gen_proc_rabbits} {gen_proc_foxes} {gen_food_foxes} {n_gen} {rows} {cols} {total}"]
    lines += [f"{kind} {cell // cols} {cell % cols}" for kind, cell in zip(kinds, cells)]
    return "\n".join(lines) + "\n"
