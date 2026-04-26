import datetime as dt
import importlib.util
import pathlib
import unittest
from unittest import mock
from urllib.parse import urlparse


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "generate_activity_overview.py"


def load_module(test_case: unittest.TestCase):
    test_case.assertTrue(MODULE_PATH.exists(), f"Missing generator script: {MODULE_PATH}")
    spec = importlib.util.spec_from_file_location("generate_activity_overview", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def isoformat_z(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def repository_payload(name: str, pushed_at: str, *, owner: str = "lReDragol", private: bool = False) -> dict[str, object]:
    return {
        "name": name,
        "archived": False,
        "private": private,
        "pushed_at": pushed_at,
        "owner": {"login": owner},
    }


def commit_payload(sha: str, committed_at: str) -> dict[str, object]:
    return {
        "sha": sha,
        "commit": {
            "author": {
                "date": committed_at,
            }
        },
    }


class CollectActivityOverviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = dt.datetime(2026, 4, 27, 12, 0, tzinfo=dt.timezone.utc)
        self.recent = isoformat_z(self.now - dt.timedelta(hours=1))
        self.public_repo = repository_payload("public-one", self.recent, private=False)
        self.private_repo = repository_payload("private-one", self.recent, private=True)
        self.collab_private_repo = repository_payload("team-secret", self.recent, owner="OtherOrg", private=True)

        self.day0 = isoformat_z(dt.datetime(2026, 4, 14, 10, 0, tzinfo=dt.timezone.utc))
        self.day5a = isoformat_z(dt.datetime(2026, 4, 19, 12, 0, tzinfo=dt.timezone.utc))
        self.day5b = isoformat_z(dt.datetime(2026, 4, 19, 14, 0, tzinfo=dt.timezone.utc))
        self.day13 = isoformat_z(dt.datetime(2026, 4, 27, 9, 0, tzinfo=dt.timezone.utc))

    def fake_request_json(self, url: str, token: str | None):
        path = urlparse(url).path

        if path == "/users/lReDragol":
            return ({"login": "lReDragol", "name": "Drago", "created_at": "2024-06-01T08:00:00Z"}, {})

        if path == "/user/repos":
            self.assertEqual(token, "secret-token")
            return ([self.public_repo, self.private_repo, self.collab_private_repo], {})

        if path == "/repos/lReDragol/public-one/commits":
            return ([commit_payload("pub-day0", self.day0), commit_payload("pub-day5", self.day5a)], {})

        if path == "/repos/lReDragol/private-one/commits":
            return ([commit_payload("priv-day5", self.day5b)], {})

        if path == "/repos/OtherOrg/team-secret/commits":
            return ([commit_payload("collab-day13", self.day13)], {})

        raise AssertionError(f"Unexpected URL: {url}")

    def test_collect_activity_overview_counts_private_repositories_and_daily_commits(self) -> None:
        module = load_module(self)

        with mock.patch.object(module, "request_json", side_effect=self.fake_request_json):
            overview = module.collect_activity_overview(
                "lReDragol",
                "secret-token",
                now=self.now,
                days=14,
                utc_offset_hours=3,
            )

        self.assertEqual(overview["title"], "lReDragol (Drago)")
        self.assertEqual(overview["public_repo_count"], 1)
        self.assertEqual(overview["private_repo_count"], 1)
        self.assertEqual(overview["daily_commit_counts"], [1, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 1])
        self.assertEqual(overview["days"], 14)
        self.assertEqual(overview["date_labels"][:3], ["14.04", "15.04", "16.04"])
        self.assertEqual(overview["date_labels"][-3:], ["25.04", "26.04", "27.04"])

    def test_svg_card_mentions_private_repositories_and_daily_commits(self) -> None:
        module = load_module(self)

        svg = module.render_activity_card(
            {
                "title": "lReDragol (Drago)",
                "public_repo_count": 17,
                "private_repo_count": 5,
                "joined_text": "Joined GitHub 2 years ago",
                "daily_commit_counts": [0, 1, 0, 2, 0, 3, 0, 2, 1, 0, 4, 1, 0, 2],
                "date_labels": [
                    "14.04",
                    "15.04",
                    "16.04",
                    "17.04",
                    "18.04",
                    "19.04",
                    "20.04",
                    "21.04",
                    "22.04",
                    "23.04",
                    "24.04",
                    "25.04",
                    "26.04",
                    "27.04",
                ],
                "days": 14,
            }
        )

        self.assertIn("Private Repos", svg)
        self.assertIn("Daily Commits (14d)", svg)
        self.assertIn("lReDragol (Drago)", svg)
        self.assertIn("Total: 16", svg)
        self.assertIn("Peak: 4", svg)
        self.assertIn("14.04", svg)
        self.assertIn("27.04", svg)
        self.assertIn(">4<", svg)


if __name__ == "__main__":
    unittest.main()
