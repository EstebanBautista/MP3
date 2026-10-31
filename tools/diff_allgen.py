#!/usr/bin/env python3
"""Reports the first difference between two allgen files.

Usage: diff_allgen.py <expected> <actual>
Exit code: 0 identical, 1 different, 2 bad usage or unreadable file.
Streams both files, so it works on the 318 MB allgen100x100. Line endings and blank lines at the
end of the files are ignored.
"""
import itertools
import sys

GRIDS = ("entities", "procreation age", "hunger")


def significant_lines(f):
    """Yields lines without line endings, dropping the blank lines at the end of the file."""
    blanks = 0
    for raw in f:
        line = raw.rstrip(b"\r\n")
        if not line:
            blanks += 1
            continue
        for _ in range(blanks):
            yield b""
        blanks = 0
        yield line


def split_grids(line):
    """Splits '|a|   |b| |c|' into the contents of its three grids, or returns None."""
    if not (line.startswith(b"|") and line.endswith(b"|")):
        return None
    first, sep, rest = line[1:-1].partition(b"|   |")
    if not sep:
        return None
    second, sep, third = rest.partition(b"| |")
    return (first, second, third) if sep else None


def number_cells(kinds, text, numbered):
    """Splits a grid of unpadded numbers into one string per cell.

    `numbered` holds the entity letters that show a number in this grid. Adjacent numbers have no
    separator, so within a run of digits a cell takes two digits only if the run has digits to
    spare and its first digit is not 0. That can misplace a value when several two-digit numbers
    touch. It only serves to locate a difference, and the raw rows are always printed as well.
    """
    cells = []
    pos = 0
    y = 0
    while y < len(kinds):
        if kinds[y] not in numbered:
            cells.append(text[pos:pos + 1].decode("latin1"))
            pos += 1
            y += 1
            continue
        end_y = y
        while end_y < len(kinds) and kinds[end_y] in numbered:
            end_y += 1
        end_pos = pos
        while text[end_pos:end_pos + 1].isdigit():
            end_pos += 1
        for cell in range(y, end_y):
            spare = (end_pos - pos) - (end_y - cell)
            width = 2 if spare > 0 and text[pos:pos + 1] != b"0" else 1
            cells.append(text[pos:pos + width].decode("latin1"))
            pos += width
        y = end_y
    return cells


def grid_cells(grids, g):
    if g == 0:
        return [chr(c) for c in grids[0]]
    return number_cells(grids[0], grids[g], b"RF" if g == 1 else b"F")


def report_row_difference(gen, row, expected, actual):
    exp_grids = split_grids(expected)
    act_grids = split_grids(actual)
    if exp_grids is None or act_grids is None:
        print(f"generation {gen}, row {row}: malformed row")
        print(f"expected: {expected!r}")
        print(f"actual:   {actual!r}")
        return
    for g in range(3):
        if exp_grids[g] == act_grids[g]:
            continue
        print(f"generation {gen}, grid {g} ({GRIDS[g]}), row {row}")
        pairs = itertools.zip_longest(grid_cells(exp_grids, g), grid_cells(act_grids, g))
        for y, (e, a) in enumerate(pairs):
            if e != a:
                print(f"cell ({row}, {y}): expected {e!r}, got {a!r}")
                break
        print("expected row: " + exp_grids[g].decode("latin1"))
        print("actual row:   " + act_grids[g].decode("latin1"))
        return


def main(argv):
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        exp_file = open(argv[1], "rb")
        act_file = open(argv[2], "rb")
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    gen = None
    row = -1
    with exp_file, act_file:
        pairs = itertools.zip_longest(significant_lines(exp_file), significant_lines(act_file))
        for number, (expected, actual) in enumerate(pairs, 1):
            if expected is not None and expected.startswith(b"Generation "):
                gen = int(expected.split()[1])
                row = -1
            elif expected is not None and expected.startswith(b"|"):
                row += 1
            if expected == actual:
                continue
            if expected is None or actual is None:
                ended = "actual" if actual is None else "expected"
                print(f"line {number}, generation {gen}: {ended} file ended first")
            elif expected.startswith(b"|") and actual.startswith(b"|"):
                report_row_difference(gen, row, expected, actual)
            else:
                print(f"line {number}, generation {gen}: expected {expected!r}, got {actual!r}")
            return 1
    print("identical")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
