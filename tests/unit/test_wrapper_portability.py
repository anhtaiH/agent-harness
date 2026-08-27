import os
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
WRAPPERS = (
    ("ah-codex", "codex"),
    ("ah-claude", "claude"),
    ("ah-cursor", "cursor-agent"),
)


class WrapperPortabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        root = pathlib.Path(self.temp_dir.name)
        fake_bin = root / "bin"
        fake_bin.mkdir()
        for _, executable in WRAPPERS:
            path = fake_bin / executable
            path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            path.chmod(0o755)
        self.env = os.environ.copy()
        self.env.update({"HOME": str(root / "home"), "PATH": f"{fake_bin}:/usr/bin:/bin"})
        for name in (
            "AGENT_HARNESS_ROOT",
            "AGENT_HARNESS_SOURCE",
            "AGENT_HARNESS_REQUIRE_EVIDENCE",
            "AGENT_HARNESS_SKIP_STOP_GATE",
            "AGENT_HARNESS_TASK_ID",
        ):
            self.env.pop(name, None)

    def run_wrapper(self, wrapper, *args):
        return subprocess.run(
            ["/bin/bash", str(ROOT / "runtime" / "bin" / wrapper), *args],
            env=self.env,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )

    def test_task_bound_wrappers_accept_no_forwarded_arguments(self):
        for wrapper, _ in WRAPPERS:
            for mode in ("run", "plan", "yolo"):
                with self.subTest(wrapper=wrapper, mode=mode):
                    result = self.run_wrapper(
                        wrapper,
                        "--task",
                        "wrapper-probe",
                        "--harness-mode",
                        mode,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_wrappers_without_task_report_task_requirement(self):
        for wrapper, _ in WRAPPERS:
            with self.subTest(wrapper=wrapper):
                result = self.run_wrapper(wrapper)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("requires --task", result.stderr)


if __name__ == "__main__":
    unittest.main()
