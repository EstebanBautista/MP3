import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "experiments"))
from ecosystem_runs import analyze, CYCLE_THRESHOLD  # noqa: E402


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

    def test_threshold_is_documented_constant(self):
        self.assertTrue(0 < CYCLE_THRESHOLD < 1)


if __name__ == "__main__":
    unittest.main()
