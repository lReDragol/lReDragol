import importlib.util
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "generate_line_badges.py"


def load_module():
    spec = importlib.util.spec_from_file_location("generate_line_badges", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class DiffBadgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()
        self.data = {
            "days": [
                {"date": f"2026-04-{day:02d}", "additions": day, "deletions": 1}
                for day in range(1, 31)
            ]
        }

    def test_summarizes_last_seven_and_thirty_days(self) -> None:
        self.assertEqual(self.module.summarize_activity(self.data, 7), (189, 7))
        self.assertEqual(self.module.summarize_activity(self.data, 30), (465, 30))

    def test_badges_are_labeled_as_raw_diff(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            stats = self.module.write_badges(pathlib.Path(directory), self.data)
            badge = (pathlib.Path(directory) / "lines-7d.svg").read_text(encoding="utf-8")

        self.assertEqual(stats["7d"], (189, 7))
        self.assertIn("DIFF 7D", badge)
        self.assertIn("raw Git diff", badge)
        self.assertNotIn("LINES 7D", badge)


if __name__ == "__main__":
    unittest.main()
