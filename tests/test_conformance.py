"""Every engine must reproduce every example from the assignment byte for byte."""
import os
import random
import re
import struct
import tempfile
import unittest

from tests.helpers import CASES, EXAMPLES, EXE, case_input, case_output, normalize, run_engine


def allgen(name):
    with open(os.path.join(EXAMPLES, "allgen" + name), "rb") as f:
        return f.read()


class TestFinalWorld(unittest.TestCase):
    def check(self, name):
        r = run_engine(EXE["eco_seq"], case_input(name))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(normalize(r.stdout), normalize(case_output(name)))


def _add_case(name):
    def test(self):
        self.check(name)

    setattr(TestFinalWorld, "test_seq_" + name, test)


for _name in CASES:
    _add_case(_name)


class TestDumpAll(unittest.TestCase):
    def check(self, name):
        r = run_engine(EXE["eco_seq"], case_input(name), extra=["--dump-all"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(normalize(r.stdout), normalize(allgen(name)))

    def test_dump_5x5(self):
        self.check("5x5")

    def test_dump_10x10(self):
        self.check("10x10")

    def test_dump_20x20(self):
        self.check("20x20")


THREAD_COUNTS = (1, 2, 4, 8, 16)
PTH = EXE["eco_pth"]
SEQ = EXE["eco_seq"]


class TestPthreads(unittest.TestCase):
    def check_final(self, name, threads):
        r = run_engine(PTH, case_input(name), threads=threads)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(normalize(r.stdout), normalize(case_output(name)))
        self.assertIn(b"threads=%d " % threads, r.stderr)

    def test_pth_no_animals_16(self):
        r = run_engine(PTH, b"2 4 3 10 3 3 2\nROCK 0 1\nROCK 2 2\n", threads=16)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(normalize(r.stdout), b"2 4 3 0 3 3 2\nROCK 0 1\nROCK 2 2\n")

    def test_pth_repeat_20x20(self):
        expected = normalize(case_output("20x20"))
        for i in range(20):
            r = run_engine(PTH, case_input("20x20"), threads=8)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(normalize(r.stdout), expected, "run %d" % i)

    def test_pth_zero_generations(self):
        data = b"2 4 3 0 2 2 1\nFOX 0 0\n"
        r = run_engine(PTH, data, threads=4)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(normalize(r.stdout), data)
        self.assertIn(b"threads=4 imbalance=1.000", r.stderr)

    def test_pth_dump_all(self):
        for name in ("5x5", "10x10", "20x20"):
            for threads in (1, 3, 8):
                with self.subTest(name=name, threads=threads):
                    r = run_engine(PTH, case_input(name), threads=threads, extra=["--dump-all"])
                    self.assertEqual(r.returncode, 0, r.stderr)
                    self.assertEqual(normalize(r.stdout), normalize(allgen(name)))

    def test_pth_frames_match_seq(self):
        data = case_input("10x10")
        seq = run_engine(SEQ, data, extra=["--frames"])
        pth = run_engine(PTH, data, threads=4, extra=["--frames"])
        self.assertEqual(pth.returncode, 0, pth.stderr)
        self.assertEqual(pth.stdout, seq.stdout)
        self.assertEqual(len(pth.stdout), 101 * (16 + 100))
        self.assertEqual(struct.unpack_from("<i", pth.stdout, 100 * 116)[0], 100)

    def test_pth_stats_file_matches_seq(self):
        data = case_input("10x10")
        with tempfile.TemporaryDirectory() as d:
            contents = []
            for exe, threads in ((SEQ, None), (PTH, 4)):
                path = os.path.join(d, "stats.csv")
                r = run_engine(exe, data, threads=threads, extra=["--stats-file", path])
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(normalize(r.stdout), normalize(case_output("10x10")))
                with open(path, "rb") as f:
                    contents.append(f.read())
        self.assertEqual(contents[0], contents[1])

    def test_pth_imbalance_at_least_one(self):
        r = run_engine(PTH, case_input("100x100_unbal01"), threads=4)
        match = re.search(rb"threads=4 imbalance=(\d+\.\d+)", r.stderr)
        self.assertIsNotNone(match, r.stderr)
        self.assertGreaterEqual(float(match.group(1)), 1.0)

    def test_pth_empty_bands_raise_imbalance(self):
        # 2 rows and 16 threads: 14 workers own nothing, so the maximum is far from the mean.
        rabbits = "".join("RABBIT %d %d\n" % (x, y) for x in range(2) for y in range(0, 400, 2))
        data = ("3 20 10 200 2 400 400\n" + rabbits).encode()
        r = run_engine(PTH, data, threads=16)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(normalize(r.stdout), normalize(run_engine(SEQ, data).stdout))
        match = re.search(rb"imbalance=(\d+\.\d+)", r.stderr)
        self.assertGreater(float(match.group(1)), 2.0)

    def test_pth_dense_thin_worlds_match_seq(self):
        # Narrow bands make most moves cross a border, conflicts included, and the boxes must grow
        # past their first capacity. Every generation is compared, not only the last one.
        rng = random.Random(20261031)
        shapes = ((1, 300), (300, 1), (2, 300), (3, 200), (9, 40), (40, 9), (64, 64))
        for rows, cols in shapes:
            cells = [(x, y) for x in range(rows) for y in range(cols)]
            objects = []
            for x, y in rng.sample(cells, len(cells) * 3 // 5):
                kind = rng.choices(("RABBIT", "FOX", "ROCK"), (6, 3, 1))[0]
                objects.append("%s %d %d\n" % (kind, x, y))
            head = "2 3 4 40 %d %d %d\n" % (rows, cols, len(objects))
            data = (head + "".join(objects)).encode()
            expected = run_engine(SEQ, data, extra=["--dump-all"]).stdout
            for threads in (2, 3, 5, 16):
                with self.subTest(rows=rows, cols=cols, threads=threads):
                    r = run_engine(PTH, data, threads=threads, extra=["--dump-all"])
                    self.assertEqual(r.returncode, 0, r.stderr)
                    self.assertEqual(r.stdout, expected)


def _add_pth_case(name, threads):
    def test(self):
        self.check_final(name, threads)

    setattr(TestPthreads, "test_pth_%s_%d" % (name, threads), test)


for _name in CASES:
    for _threads in THREAD_COUNTS:
        _add_pth_case(_name, _threads)


if __name__ == "__main__":
    unittest.main()
