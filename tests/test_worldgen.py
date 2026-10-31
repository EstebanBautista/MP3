import unittest

from tools.worldgen import generate_world

ARGS = dict(rows=10, cols=12, rabbits=20, foxes=5, rocks=7,
            gen_proc_rabbits=3, gen_proc_foxes=9, gen_food_foxes=6, n_gen=50)


class TestWorldgen(unittest.TestCase):
    def test_same_seed_same_world(self):
        self.assertEqual(generate_world(seed=42, **ARGS), generate_world(seed=42, **ARGS))
        self.assertNotEqual(generate_world(seed=42, **ARGS), generate_world(seed=43, **ARGS))

    def test_format_matches_engine_input(self):
        lines = generate_world(seed=1, **ARGS).splitlines()
        self.assertEqual(lines[0], "3 9 6 50 10 12 32")
        objects = [line.split() for line in lines[1:]]
        self.assertEqual(len(objects), 32)
        kinds = [o[0] for o in objects]
        self.assertEqual((kinds.count("RABBIT"), kinds.count("FOX"), kinds.count("ROCK")), (20, 5, 7))
        cells = {(int(o[1]), int(o[2])) for o in objects}
        self.assertEqual(len(cells), 32)
        self.assertTrue(all(0 <= r < 10 and 0 <= c < 12 for r, c in cells))

    def test_too_many_objects(self):
        with self.assertRaises(ValueError):
            generate_world(seed=1, **{**ARGS, "rabbits": 100, "foxes": 15, "rocks": 6})

    def test_full_world_is_allowed(self):
        text = generate_world(seed=1, **{**ARGS, "rabbits": 100, "foxes": 15, "rocks": 5})
        self.assertEqual(len(text.splitlines()), 121)

    def test_negative_population_rejected(self):
        with self.assertRaises(ValueError):
            generate_world(seed=1, **{**ARGS, "foxes": -1})


if __name__ == "__main__":
    unittest.main()
