import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "experiments"))
from measure import parse_time_line, summarize, quartiles  # noqa: E402


def row(design, mode, case, threads, wall, cpu=None, imbalance=1.0, rep=1):
    return dict(design=design, mode=mode, case=case, threads=threads, rep=rep,
                wall=wall, cpu=wall if cpu is None else cpu, imbalance=imbalance)


class TestMeasure(unittest.TestCase):
    def test_parse_time_line(self):
        err = "noise\ntime wall=3.997457 cpu=4.000000 threads=8 imbalance=1.250\n"
        self.assertEqual(parse_time_line(err),
                         dict(wall=3.997457, cpu=4.0, threads=8, imbalance=1.25))

    def test_parse_time_line_missing_raises(self):
        with self.assertRaises(ValueError):
            parse_time_line("nothing here\n")

    def test_quartiles(self):
        self.assertEqual(quartiles([1, 2, 3, 4, 5]), (2.0, 3.0, 4.0))

    def test_summarize_speedup(self):
        rows = [row("omp", "adaptive", "c", 1, 10.0), row("omp", "adaptive", "c", 4, 4.0)]
        out = {r["threads"]: r for r in summarize(rows)}
        self.assertAlmostEqual(out[4]["speedup"], 2.5)
        self.assertAlmostEqual(out[4]["efficiency"], 0.625)
        self.assertAlmostEqual(out[1]["speedup"], 1.0)

    def test_summarize_median_iqr_and_seq_overhead(self):
        rows = [row("seq", "-", "c", 1, w) for w in (10, 10, 10)]
        rows += [row("pth", "-", "c", 1, w) for w in (11, 12, 20)]
        out = {r["design"]: r for r in summarize(rows)}
        self.assertEqual(out["pth"]["wall_median"], 12)
        self.assertEqual(out["pth"]["n"], 3)
        self.assertEqual(out["pth"]["wall_q3"] - out["pth"]["wall_q1"], out["pth"]["wall_iqr"])
        self.assertAlmostEqual(out["pth"]["overhead_vs_seq"], 0.2)
        self.assertAlmostEqual(out["pth"]["speedup_vs_seq"], 10 / 12)


if __name__ == "__main__":
    unittest.main()
