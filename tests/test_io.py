import unittest

from tests.helpers import EXE, run_engine


def run(text):
    return run_engine(EXE["eco_seq"], text.encode())


class TestIO(unittest.TestCase):
    def assert_rejected(self, text):
        r = run(text)
        self.assertEqual(r.returncode, 2)
        self.assertTrue(r.stderr)
        self.assertEqual(r.stdout, b"")

    def test_roundtrip(self):
        data = "2 4 3 0 5 5 2\nROCK 0 0\nFOX 4 3\n"
        r = run(data)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, data.encode())

    def test_crlf_input(self):
        r = run("2 4 3 0 5 5 2\r\nROCK 0 0\r\nFOX 4 3\r\n")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, b"2 4 3 0 5 5 2\nROCK 0 0\nFOX 4 3\n")

    def test_output_sorted(self):
        r = run("2 4 3 0 5 5 3\nFOX 4 3\nRABBIT 0 2\nROCK 0 1\n")
        self.assertEqual(r.stdout, b"2 4 3 0 5 5 3\nROCK 0 1\nRABBIT 0 2\nFOX 4 3\n")

    def test_out_of_range(self):
        self.assert_rejected("2 4 3 0 5 5 1\nROCK 5 0\n")

    def test_unknown_object(self):
        self.assert_rejected("2 4 3 0 5 5 1\nWOLF 1 1\n")

    def test_duplicate_cell(self):
        self.assert_rejected("2 4 3 0 5 5 2\nROCK 1 1\nFOX 1 1\n")

    def test_too_few_lines(self):
        self.assert_rejected("2 4 3 0 5 5 3\nROCK 1 1\n")


if __name__ == "__main__":
    unittest.main()
