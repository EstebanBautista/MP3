"""Order of replies during a restart in the page script. Needs Node, but neither a server nor a browser."""
import os
import shutil
import subprocess
import unittest

CHECK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "restart_check.js")
NODE = shutil.which("node")


@unittest.skipUnless(NODE, "Node is not installed")
class TestRestartRaces(unittest.TestCase):
    def check(self, scenario):
        done = subprocess.run([NODE, CHECK, scenario], capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_stale_409_while_start_pending(self):
        self.check("stale_409_while_start_pending")

    def test_stale_409_body_read_after_new_run(self):
        self.check("stale_409_body_read_after_new_run")

    def test_stale_heartbeat_body_read_after_new_run(self):
        self.check("stale_heartbeat_body_read_after_new_run")

    def test_stale_heartbeat_while_start_pending(self):
        self.check("stale_heartbeat_while_start_pending")

    def test_stale_finish_while_start_pending(self):
        self.check("stale_finish_while_start_pending")

    def test_new_run_clears_the_banner(self):
        self.check("new_run_clears_the_banner")

    def test_second_submit_waits_for_the_first(self):
        self.check("second_submit_waits_for_the_first")

    def test_real_failure_is_still_reported(self):
        self.check("real_failure_is_still_reported")

    def test_real_early_finish_is_still_reported(self):
        self.check("real_early_finish_is_still_reported")

    def test_failure_hidden_by_a_rejected_start_comes_back(self):
        self.check("failure_hidden_by_a_rejected_start_comes_back")

    def test_finish_hidden_by_a_rejected_start_comes_back(self):
        self.check("finish_hidden_by_a_rejected_start_comes_back")


if __name__ == "__main__":
    unittest.main()
