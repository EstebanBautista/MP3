"""Shared helpers for engine tests."""
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")
EXAMPLES = os.path.join(ROOT, "ecosystem_examples")

EXE_SUFFIX = ".exe" if os.name == "nt" else ""
EXE = {name: os.path.join(BUILD, name + EXE_SUFFIX) for name in ("eco_seq", "eco_pth", "eco_omp")}

CASES = (
    "5x5", "10x10", "20x20", "100x100", "200x200",
    "100x100_unbal01", "100x100_unbal02",
)


def case_input(name):
    with open(os.path.join(EXAMPLES, "input" + name), "rb") as f:
        return f.read()


def case_output(name):
    with open(os.path.join(EXAMPLES, "output" + name), "rb") as f:
        return f.read()


def run_engine(exe, input_bytes, threads=None, extra=(), env=None):
    cmd = [exe]
    if threads is not None:
        cmd += ["--threads", str(threads)]
    cmd += list(extra)
    return subprocess.run(cmd, input=input_bytes, capture_output=True, env=env)


def with_generations(input_bytes, generations):
    """The same world with N_GEN, the fourth number of the header, replaced."""
    head, rest = input_bytes.split(b"\n", 1)
    fields = head.split()
    fields[3] = b"%d" % generations
    return b" ".join(fields) + b"\n" + rest


def normalize(data):
    return data.replace(b"\r\n", b"\n")
