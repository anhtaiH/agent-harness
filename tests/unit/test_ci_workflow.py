from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


def matrix_entry(name: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    active = False
    for raw_line in (ROOT / ".github" / "workflows" / "ci.yml").read_text().splitlines():
        line = raw_line.strip()
        if line.startswith("- name: "):
            active = line.removeprefix("- name: ") == name
        elif active and ":" in line:
            key, value = line.split(":", 1)
            fields[key] = value.strip()
    return fields


class CiWorkflowTests(unittest.TestCase):
    def test_macos_arm64_uses_standard_schedulable_runner(self):
        self.assertEqual(
            {
                "os": "macos-15",
                "expected_os": "Darwin",
                "expected_arch": "arm64",
            },
            matrix_entry("macos-arm64"),
        )


if __name__ == "__main__":
    unittest.main()
