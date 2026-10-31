import math
import os
import random
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "experiments"))
from ecosystem_runs import analyze, remove_fast, CYCLE_THRESHOLD  # noqa: E402


def make(n, rabbit, fox):
    """Series of (gen, rabbits, foxes) rows from two functions of the generation."""
    return [(t, round(rabbit(t)), round(fox(t))) for t in range(n)]


def sine(mean, amp, period, shift=0.0):
    return lambda t: mean + amp * math.sin(2 * math.pi * (t - shift) / period)


class TestAnalyze(unittest.TestCase):
    def test_analyze_detects_sine_period(self):
        series = make(3000, sine(1000, 300, 100), sine(300, 100, 100, shift=25))
        out = analyze(series)
        self.assertTrue(out["coexist"])
        self.assertAlmostEqual(out["rabbit_period"], 100, delta=2)
        self.assertAlmostEqual(out["fox_lag"], 25, delta=2)

    def test_analyze_extinction(self):
        series = [(t, 50 if t < 40 else 0, 20 if t < 70 else 0) for t in range(200)]
        out = analyze(series)
        self.assertEqual(out["extinct_rabbits_gen"], 40)
        self.assertEqual(out["extinct_foxes_gen"], 70)
        self.assertFalse(out["coexist"])
        self.assertIsNone(out["rabbit_period"])

    def test_analyze_survivors_have_no_extinction_gen(self):
        out = analyze(make(500, sine(100, 10, 50), sine(40, 5, 50)))
        self.assertIsNone(out["extinct_rabbits_gen"])
        self.assertIsNone(out["extinct_foxes_gen"])
        self.assertTrue(out["coexist"])

    def test_analyze_flat_no_period(self):
        out = analyze([(t, 100, 30) for t in range(2000)])
        self.assertIsNone(out["rabbit_period"])
        self.assertIsNone(out["fox_period"])
        self.assertIsNone(out["fox_lag"])
        self.assertTrue(out["coexist"])

    def test_analyze_separates_slow_cycle_from_fast_oscillation(self):
        # Slow cycle of period 1000 plus a fast oscillation of period 10 in both populations.
        def rabbit(t):
            return 1500 + 400 * math.sin(2 * math.pi * t / 1000) + 200 * math.sin(2 * math.pi * t / 10)

        def fox(t):
            return 500 + 120 * math.sin(2 * math.pi * (t - 200) / 1000) + 60 * math.sin(2 * math.pi * t / 10)
        out = analyze(make(8000, rabbit, fox))
        self.assertAlmostEqual(out["rabbit_raw_period"], 10, delta=1)
        self.assertAlmostEqual(out["rabbit_period"], 1000, delta=20)
        self.assertAlmostEqual(out["fox_period"], 1000, delta=20)
        self.assertAlmostEqual(out["fox_lag"], 200, delta=10)

    def test_analyze_fast_only_has_no_slow_cycle(self):
        # Only the fast oscillation: the raw period is found, the slow one is not invented.
        series = make(8000, sine(1500, 300, 4), sine(500, 100, 21))
        out = analyze(series)
        self.assertAlmostEqual(out["rabbit_raw_period"], 4, delta=0.5)
        self.assertAlmostEqual(out["fox_raw_period"], 21, delta=0.5)
        self.assertIsNone(out["rabbit_period"])
        self.assertIsNone(out["fox_period"])

    def test_analyze_noise_is_not_a_cycle(self):
        rng = random.Random(7)
        series = [(t, round(1000 + rng.gauss(0, 50)), round(300 + rng.gauss(0, 20))) for t in range(5000)]
        out = analyze(series)
        self.assertIsNone(out["rabbit_period"])
        self.assertIsNone(out["fox_period"])

    def test_analyze_weak_cycle_near_fast_fold_period(self):
        # Exact fast patterns of periods 4 and 21 (fold 84) plus a slow cycle of period 90, close to
        # the fold, at only 6% of the mean: the phase-mean subtraction must not cancel it.
        def rabbit(t):
            return 1500 * (1 + 0.06 * math.sin(2 * math.pi * t / 90)) + 300 * ((t % 4) - 1.5)

        def fox(t):
            return 500 * (1 + 0.06 * math.sin(2 * math.pi * (t - 22) / 90)) + 20 * ((t % 21) - 10)
        out = analyze(make(10000, rabbit, fox))
        self.assertEqual((out["rabbit_raw_period"], out["fox_raw_period"]), (4, 21))
        self.assertEqual(out["fold"], 84)
        self.assertAlmostEqual(out["rabbit_period"], 90, delta=4)
        self.assertAlmostEqual(out["fox_period"], 90, delta=4)
        self.assertAlmostEqual(out["fox_lag"], 22, delta=3)
        self.assertEqual(out["cycle_grade"], "weak")  # amplitude 6% of the mean is below STRONG_AMP

    def test_analyze_large_cycle_is_graded_strong(self):
        out = analyze(make(3000, sine(1000, 300, 100), sine(300, 100, 100, shift=25)))
        self.assertEqual(out["cycle_grade"], "strong")
        self.assertGreater(out["rabbit_amp"], 0.1)

    def test_analyze_no_cycle_grade_none(self):
        self.assertEqual(analyze([(t, 100, 30) for t in range(2000)])["cycle_grade"], "none")

    def test_analyze_red_noise_is_not_a_cycle(self):
        # Slowly wandering series (AR(1), phi = 0.99): autocorrelation decays but never oscillates. In 150 trials of this
        # generator, 0 gave a false cycle at 10000 generations and 4% at 6000 (see the findings).
        for seed in range(5):
            rng = random.Random(seed)
            r = f = 0.0
            series = []
            for t in range(10000):
                r = 0.99 * r + rng.gauss(0, 10)
                f = 0.99 * f + rng.gauss(0, 5)
                series.append((t, round(1000 + r), round(300 + f)))
            out = analyze(series)
            self.assertIsNone(out["rabbit_period"], seed)
            self.assertIsNone(out["fox_period"], seed)

    def test_remove_fast_removes_the_pattern_and_keeps_the_mean(self):
        gens = np.arange(2000)
        x = 100.0 + 20 * ((gens % 4) - 1.5) + 5 * ((gens % 21) - 10)
        y, fold = remove_fast(x, gens, [4, 21])
        self.assertEqual(fold, 84)
        self.assertLess(np.std(y), 1e-9)
        self.assertAlmostEqual(float(y.mean()), float(x.mean()))

    def test_threshold_decides_what_is_a_cycle(self):
        # The same series is a cycle at a low threshold and not at one above its peak.
        series = make(4000, lambda t: 1000 + 40 * math.sin(2 * math.pi * t / 100) + random.Random(t).gauss(0, 60),
                      lambda t: 300 + 10 * math.sin(2 * math.pi * t / 100) + random.Random(t + 1).gauss(0, 15))
        low = analyze(series, threshold=0.05)
        high = analyze(series, threshold=0.99)
        self.assertAlmostEqual(low["rabbit_period"], 100, delta=3)
        self.assertIsNone(high["rabbit_period"])
        self.assertTrue(0 < CYCLE_THRESHOLD < 1)


if __name__ == "__main__":
    unittest.main()
