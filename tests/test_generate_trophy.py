import datetime as dt
import importlib.util
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "generate_trophy.py"


def load_module(test_case: unittest.TestCase):
    test_case.assertTrue(MODULE_PATH.exists())
    spec = importlib.util.spec_from_file_location("generate_trophy", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TrophyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module(self)
        self.stats = {
            "total_stars": 46,
            "total_commits": 1158,
            "followers": 8,
            "public_repositories": 26,
            "private_repositories": 19,
            "created_at": "2023-06-16T04:04:01Z",
        }
        self.releases = {
            "totals": {"downloads": 1576, "releases": 34, "repositories_with_downloads": 8},
        }

    def test_builds_current_metrics_without_external_trophy_service(self) -> None:
        metrics = self.module.build_metrics(self.stats, self.releases, now=dt.date(2026, 9, 3))
        values = {metric["title"]: metric["value"] for metric in metrics}
        self.assertEqual(values["Stars"], 46)
        self.assertEqual(values["Commits"], 1158)
        self.assertEqual(values["Repositories"], 45)
        self.assertEqual(values["Experience"], 3)
        self.assertEqual(values["Downloads"], 1576)

    def test_renders_light_and_dark_trophy_files(self) -> None:
        metrics = self.module.build_metrics(self.stats, self.releases, now=dt.date(2026, 9, 3))
        with tempfile.TemporaryDirectory() as directory:
            light, dark = self.module.write_trophies(pathlib.Path(directory), metrics)
            light_svg = light.read_text(encoding="utf-8")
            dark_svg = dark.read_text(encoding="utf-8")

        self.assertIn("1,576", light_svg)
        self.assertIn("26 public + 19 private", dark_svg)
        self.assertNotIn("github-profile-trophy.vercel.app", light_svg + dark_svg)


if __name__ == "__main__":
    unittest.main()
