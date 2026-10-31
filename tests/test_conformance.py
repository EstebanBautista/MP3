"""The sequential engine must reproduce every example from the assignment byte for byte."""
import os
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


if __name__ == "__main__":
    unittest.main()
