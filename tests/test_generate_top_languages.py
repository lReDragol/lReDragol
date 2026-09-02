from __future__ import annotations

import datetime as dt
import importlib.util
import json
import pathlib
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "generate_top_languages.py"


def load_module(test_case: unittest.TestCase):
    test_case.assertTrue(MODULE_PATH.exists())
    spec = importlib.util.spec_from_file_location("generate_top_languages", MODULE_PATH)
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def repository(name: str, *, owner: str = "lReDragol", private: bool = False, fork: bool = False) -> dict[str, object]:
    return {
        "name": name,
        "private": private,
        "fork": fork,
        "owner": {"login": owner},
    }


class TopLanguagesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module(self)

    def test_aggregates_owned_public_and_private_repository_languages(self) -> None:
        repositories = [
            repository("public-one"),
            repository("private-one", private=True),
            repository("forked", fork=True),
            repository("collab", owner="OtherOrg", private=True),
        ]

        def fake_languages(owner: str, name: str, token: str | None) -> dict[str, int]:
            self.assertEqual(token, "secret-token")
            return {
                "public-one": {"Python": 900, "JavaScript": 100, "Jupyter Notebook": 5000},
                "private-one": {"Python": 100, "C#": 1000},
            }[name]

        with (
            mock.patch.object(self.module, "list_repositories", return_value=repositories),
            mock.patch.object(self.module, "repository_languages", side_effect=fake_languages),
        ):
            data = self.module.collect_top_languages(
                "lReDragol",
                "secret-token",
                excluded_languages={"Jupyter Notebook"},
                now=dt.datetime(2026, 9, 3, tzinfo=dt.timezone.utc),
            )

        self.assertEqual(data["repository_count"], 2)
        self.assertEqual(data["total_bytes"], 2100)
        self.assertEqual([item["name"] for item in data["languages"]], ["C#", "Python", "JavaScript"])
        published = json.dumps(data)
        self.assertNotIn("private-one", published)
        self.assertNotIn("public-one", published)

    def test_renders_current_language_totals_without_repository_names(self) -> None:
        data = {
            "repository_count": 40,
            "total_bytes": 1000,
            "languages": [
                {"name": "Python", "bytes": 880, "percent": 88.0, "color": "#3572A5"},
                {"name": "Lua", "bytes": 120, "percent": 12.0, "color": "#000080"},
            ],
        }
        svg = self.module.render_top_languages(data, theme="dark")
        self.assertIn("Top Languages", svg)
        self.assertIn("By code size", svg)
        self.assertIn("88.00%", svg)
        self.assertIn("40 owned repos", svg)


if __name__ == "__main__":
    unittest.main()
