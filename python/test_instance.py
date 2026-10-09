#!/usr/bin/env python3
"""One Cinema Player per session, and a later launch raises that window."""

import os
import sys
import tempfile
import textwrap
import time
import unittest

sys.path.insert(0, os.path.dirname(__file__))

import cinema_player as player


class SingleInstanceTests(unittest.TestCase):
    def test_second_launch_wakes_the_running_player(self):
        runtime = tempfile.mkdtemp(prefix="cinema-player-instance-")
        seen = []
        self.addCleanup(lambda: os.path.exists(runtime) and None)
        self.assertTrue(player.claim_single_instance(runtime))
        player.set_instance_activate(lambda: seen.append("raise"))
        self.assertTrue(player.signal_running_instance(runtime, attempts=10))
        deadline = time.monotonic() + 1
        while not seen and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(seen, ["raise"])

    def test_a_second_process_does_not_take_the_lock(self):
        runtime = tempfile.mkdtemp(prefix="cinema-player-instance-")
        self.assertTrue(player.claim_single_instance(runtime))
        script = textwrap.dedent(
            """
            import sys
            sys.path.insert(0, sys.argv[1])
            import cinema_player as player
            claimed = player.claim_single_instance(sys.argv[2])
            print("claimed" if claimed else "busy")
            """
        )
        import subprocess
        completed = subprocess.run(
            [sys.executable, "-c", script, os.path.dirname(__file__), runtime],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("busy", completed.stdout)
