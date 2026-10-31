"""Edge cases and the command line contract of the engine."""
import os
import re
import struct
import subprocess
import sys
import tempfile
import unittest

from tests.helpers import BUILD, EXE, EXE_SUFFIX, ROOT, case_input, run_engine

SEQ = EXE["eco_seq"]
TIME_LINE = re.compile(
    rb"^time wall=\d+\.\d+ cpu=\d+\.\d+ threads=\d+ imbalance=\d+\.\d+\r?\n", re.M
)


def run(text, extra=()):
    return run_engine(SEQ, text.encode(), extra=extra)


class TestWorldEdgeCases(unittest.TestCase):
    def test_no_animals(self):
        data = "2 4 3 10 3 3 2\nROCK 0 1\nROCK 2 2\n"
        r = run(data)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, b"2 4 3 0 3 3 2\nROCK 0 1\nROCK 2 2\n")

    def test_extinction(self):
        # Born with hunger 0, it has hunger 1 after one generation and starves in the second.
        r = run("2 4 2 5 3 3 1\nFOX 1 1\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, b"2 4 2 0 3 3 0\n")

    def test_fox_starves_exactly_at_gen_food(self):
        # GEN_FOOD_FOXES=3: survives generations 0 and 1 and dies in generation 2.
        r = run("9 9 3 2 1 5 1\nFOX 0 0\n")
        self.assertEqual(r.stdout, b"9 9 3 0 1 5 1\nFOX 0 2\n")
        r = run("9 9 3 3 1 5 1\nFOX 0 0\n")
        self.assertEqual(r.stdout, b"9 9 3 0 1 5 0\n")

    def test_surrounded_rabbit_stays(self):
        # P=0 must not reach the modulo.
        data = "1 4 3 5 3 3 5\nROCK 0 1\nROCK 1 0\nRABBIT 1 1\nROCK 1 2\nROCK 2 1\n"
        r = run(data)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(
            r.stdout,
            b"1 4 3 0 3 3 5\nROCK 0 1\nROCK 1 0\nRABBIT 1 1\nROCK 1 2\nROCK 2 1\n",
        )

    def test_surrounded_fox_starves_in_place(self):
        data = "9 9 2 2 3 3 5\nROCK 0 1\nROCK 1 0\nFOX 1 1\nROCK 1 2\nROCK 2 1\n"
        r = run(data)
        self.assertEqual(
            r.stdout, b"9 9 2 0 3 3 4\nROCK 0 1\nROCK 1 0\nROCK 1 2\nROCK 2 1\n"
        )

    def test_rabbit_procreates_only_when_it_moves(self):
        # GEN_PROC_RABBITS=1: age 0 in generation 0 (moves alone), age 1 in generation 1 (child).
        r = run("1 9 9 2 1 4 1\nRABBIT 0 0\n")
        self.assertEqual(r.stdout, b"1 9 9 0 1 4 2\nRABBIT 0 1\nRABBIT 0 2\n")

    def test_zero_generations(self):
        data = "2 4 3 0 2 2 1\nFOX 0 0\n"
        self.assertEqual(run(data).stdout, data.encode())


class TestCommandLine(unittest.TestCase):
    def test_time_line_on_stderr_only(self):
        r = run("2 4 3 1 2 2 1\nROCK 0 0\n")
        self.assertRegex(r.stderr, TIME_LINE)
        self.assertNotIn(b"time", r.stdout)

    def test_seq_reports_one_thread_and_balance_one(self):
        r = run("2 4 3 1 2 2 1\nROCK 0 0\n", extra=["--threads", "4"])
        self.assertEqual(r.returncode, 0)
        self.assertIn(b"threads=1 imbalance=1", r.stderr)

    def test_bad_arguments(self):
        for extra in (
            ["--threads"],
            ["--threads", "0"],
            ["--threads", "x"],
            ["--nope"],
            ["--stats-file"],
            ["--stats-file", "--frames"],
            ["--frames", "--dump-all"],
        ):
            with self.subTest(extra=extra):
                r = run("2 4 3 1 2 2 0\n", extra=extra)
                self.assertEqual(r.returncode, 2)
                self.assertEqual(r.stdout, b"")
                self.assertTrue(r.stderr)

    def test_unwritable_stats_file(self):
        r = run("2 4 3 1 2 2 0\n", extra=["--stats-file", os.path.join(BUILD, "no", "dir", "x")])
        self.assertEqual(r.returncode, 2)
        self.assertEqual(r.stdout, b"")

    def test_frames(self):
        # The rabbit moves from column 0 to 1; the rock stays.
        r = run("9 9 9 1 1 3 2\nRABBIT 0 0\nROCK 0 2\n", extra=["--frames"])
        self.assertEqual(r.returncode, 0, r.stderr)
        expected = struct.pack("<4i", 0, 1, 0, 1) + bytes([2, 0, 1])
        expected += struct.pack("<4i", 1, 1, 0, 1) + bytes([0, 2, 1])
        self.assertEqual(r.stdout, expected)

    def test_frames_count_on_real_case(self):
        data = case_input("5x5")
        r = run_engine(SEQ, data, extra=["--frames"])
        self.assertEqual(len(r.stdout), 7 * (16 + 25))
        gen, rabbits, foxes, rocks = struct.unpack_from("<4i", r.stdout, 0)
        self.assertEqual((gen, rabbits, foxes, rocks), (0, 3, 4, 2))
        # Last generation of allgen5x5: one rabbit, two foxes.
        gen, rabbits, foxes, rocks = struct.unpack_from("<4i", r.stdout, 6 * 41)
        self.assertEqual((gen, rabbits, foxes, rocks), (6, 1, 2, 2))

    def test_stats_file_with_final_world(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "stats.csv")
            r = run_engine(SEQ, case_input("5x5"), extra=["--stats-file", path])
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(r.stdout.startswith(b"2 4 3 0 5 5 5\n"))
            with open(path, "rb") as f:
                lines = f.read().split(b"\n")
        self.assertEqual(lines[0], b"gen,rabbits,foxes")
        self.assertEqual(lines[1], b"0,3,4")
        self.assertEqual(lines[7], b"6,1,2")
        self.assertEqual(lines[8:], [b""])


class TestDiffAllgen(unittest.TestCase):
    TOOL = os.path.join(ROOT, "tools", "diff_allgen.py")

    def diff(self, expected, actual):
        with tempfile.TemporaryDirectory() as d:
            paths = [os.path.join(d, "a"), os.path.join(d, "b")]
            for path, data in zip(paths, (expected, actual)):
                with open(path, "wb") as f:
                    f.write(data)
            return subprocess.run(
                [sys.executable, self.TOOL] + paths, capture_output=True, text=True
            )

    def test_identical_ignoring_line_endings_and_trailing_blank_lines(self):
        data = run_engine(SEQ, case_input("5x5"), extra=["--dump-all"]).stdout
        r = self.diff(data, data.replace(b"\n", b"\r\n") + b"\r\n")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_reports_first_difference(self):
        data = run_engine(SEQ, case_input("5x5"), extra=["--dump-all"]).stdout
        lines = data.split(b"\n")
        target = lines.index(b"Generation 3") + 3  # Row 1 of generation 3.
        self.assertEqual(lines[target], b"|     |   |     | |     |")
        changed = list(lines)
        changed[target] = b"|  R  |   |  1  | |  R  |"
        r = self.diff(data, b"\n".join(changed))
        self.assertEqual(r.returncode, 1)
        self.assertIn("generation 3, grid 0 (entities), row 1", r.stdout)
        self.assertIn("cell (1, 2): expected ' ', got 'R'", r.stdout)

    def test_two_digit_number_cell(self):
        head = b"Generation 0\n"
        r = self.diff(
            head + b"|F R|   |10 2| |0 R|\n", head + b"|F R|   |11 2| |0 R|\n"
        )
        self.assertEqual(r.returncode, 1)
        self.assertIn("cell (0, 0): expected '10', got '11'", r.stdout)

    def test_shorter_file(self):
        r = self.diff(b"Generation 0\n", b"")
        self.assertEqual(r.returncode, 1)
        self.assertIn("actual file ended first", r.stdout)


class TestRulesUnit(unittest.TestCase):
    def test_merge_rules(self):
        # Native test of the merge functions: commutativity, winners and fox over rabbit.
        r = subprocess.run([os.path.join(BUILD, "rules_test" + EXE_SUFFIX)], capture_output=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
