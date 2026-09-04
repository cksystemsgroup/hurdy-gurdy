"""The sealed runner (KERNEL.md §6, §10): own process, empty
environment, scratch working directory, wall cap; determinism
measured by running twice. The seal is what makes reaching for an
existing tool loud."""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import unittest

from kernel import runner


def _script(tmp: str, name: str, body: str) -> str:
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    return path


class TheSeal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_environment_is_empty(self):
        s = _script(self.tmp, "env.py",
                    "import json, os\nprint(json.dumps(dict(os.environ)))\n")
        res = runner.run_exe(s, [])
        self.assertTrue(res.ok, res.err)
        env = json.loads(res.out)
        # nothing but the blank PATH reaches the child — Python itself
        # adds its locale coercion (LC_CTYPE), and macOS may add its
        # CoreFoundation marker; neither names a tool
        self.assertEqual({k for k in env if not k.startswith("__CF_")
                          and k != "LC_CTYPE"}, {"PATH"})
        self.assertEqual(env["PATH"], "")
        self.assertNotIn("HOME", env)

    def test_working_directory_is_scratch_and_gone_afterwards(self):
        s = _script(self.tmp, "cwd.py", "import os\nprint(os.getcwd())\n")
        res = runner.run_exe(s, [])
        cwd = res.out.decode().strip()
        self.assertNotEqual(os.path.realpath(cwd), os.path.realpath(os.getcwd()))
        self.assertFalse(os.path.exists(cwd))

    def test_no_tool_can_be_found(self):
        # not even on the platform default path: an unset PATH would
        # let libc and subprocess search /bin:/usr/bin, where macOS
        # keeps a python3 — the blank PATH is what closes that
        s = _script(self.tmp, "tool.py",
                    "import shutil, subprocess\n"
                    "print(shutil.which('python3'))\n"
                    "subprocess.run(['python3', '-c', 'print(1)'])\n")
        res = runner.run_exe(s, [])
        self.assertFalse(res.ok)
        self.assertTrue(res.out.startswith(b"None"), res.out)
        self.assertIn(b"FileNotFoundError", res.err)

    def test_determinism_is_measured_not_declared(self):
        det = _script(self.tmp, "det.py", "print(42)\n")
        _, same = runner.run_twice(det, [])
        self.assertTrue(same)
        rnd = _script(self.tmp, "rnd.py",
                      "import os\nprint(os.urandom(8).hex())\n")
        _, same = runner.run_twice(rnd, [])
        self.assertFalse(same)

    def test_wall_is_a_result_not_an_exception(self):
        slow = _script(self.tmp, "slow.py", "import time\ntime.sleep(5)\n")
        res = runner.run_exe(slow, [], wall_s=0.5)
        self.assertTrue(res.timed_out)
        self.assertIsNone(res.rc)
        self.assertFalse(res.ok)
        _, same = runner.run_twice(slow, [], wall_s=0.5)
        self.assertFalse(same)

    def test_stdin_and_args_reach_the_program(self):
        s = _script(self.tmp, "io.py",
                    "import sys\nprint(sys.argv[1:], sys.stdin.read())\n")
        res = runner.run_exe(s, ["a", "b"])
        self.assertIn(b"['a', 'b']", res.out)
        res = runner.run([sys.executable, s], stdin=b"hello")
        self.assertIn(b"hello", res.out)

    def test_non_python_runs_directly_as_an_accelerator_would(self):
        exe = _script(self.tmp, "acc", "#!/bin/sh\necho fast\n")
        os.chmod(exe, os.stat(exe).st_mode | stat.S_IXUSR)
        res = runner.run_exe(exe, [])
        self.assertTrue(res.ok, res.err)
        self.assertEqual(res.out, b"fast\n")
