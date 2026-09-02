import datetime as dt
import importlib.util
import json
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
        "full_name": f"{owner}/{name}",
        "archived": False,
        "private": private,
        "pushed_at": pushed_at,
        "owner": {"login": owner},
    }


def commit_payload(sha: str, committed_at: str, *, parents: int = 1) -> dict[str, object]:
    return {
        "sha": sha,
        "parents": [{"sha": f"parent-{index}"} for index in range(parents)],
        "commit": {"author": {"date": committed_at}},
    }


class CollectActivityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module(self)
        self.now = dt.datetime(2026, 4, 27, 12, 0, tzinfo=dt.timezone.utc)
        self.recent = isoformat_z(self.now - dt.timedelta(hours=1))
        self.public_repo = repository_payload("public-one", self.recent)
        self.private_repo = repository_payload("private-one", self.recent, private=True)
        self.collab_repo = repository_payload("team-secret", self.recent, owner="OtherOrg", private=True)

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
            return ([self.public_repo, self.private_repo, self.collab_repo], {})
        if path == "/repos/lReDragol/public-one/commits":
            return ([commit_payload("pub-day0", self.day0), commit_payload("pub-day5", self.day5a)], {})
        if path == "/repos/lReDragol/private-one/commits":
            return ([commit_payload("priv-day5", self.day5b)], {})
        if path == "/repos/OtherOrg/team-secret/commits":
            return ([commit_payload("collab-day13", self.day13, parents=2)], {})

        stats = {
            "/repos/lReDragol/public-one/commits/pub-day0": (10, 2),
            "/repos/lReDragol/public-one/commits/pub-day5": (3, 1),
            "/repos/lReDragol/private-one/commits/priv-day5": (30, 5),
            "/repos/OtherOrg/team-secret/commits/collab-day13": (2, 8),
        }
        if path in stats:
            additions, deletions = stats[path]
            return ({"stats": {"additions": additions, "deletions": deletions}}, {})
        raise AssertionError(f"Unexpected URL: {url}")

    def test_collects_private_activity_as_daily_aggregates_only(self) -> None:
        with mock.patch.object(self.module, "request_json", side_effect=self.fake_request_json):
            data = self.module.collect_activity_data(
                "lReDragol",
                "secret-token",
                now=self.now,
                days=14,
                refresh_days=14,
                utc_offset_hours=3,
            )

        self.assertEqual(data["title"], "lReDragol (Drago)")
        self.assertEqual(data["repository_counts"], {"public": 1, "private": 1})
        self.assertEqual(data["days"][0], {"date": "2026-04-14", "commits": 1, "additions": 10, "deletions": 2, "changed": 12, "merges": 0})
        self.assertEqual(data["days"][5], {"date": "2026-04-19", "commits": 2, "additions": 33, "deletions": 6, "changed": 39, "merges": 0})
        self.assertEqual(data["days"][13], {"date": "2026-04-27", "commits": 1, "additions": 2, "deletions": 8, "changed": 10, "merges": 1})

        published = json.dumps(data)
        for private_value in ("private-one", "team-secret", "priv-day5", "collab-day13"):
            self.assertNotIn(private_value, published)

    def test_cached_history_is_preserved_outside_refresh_window(self) -> None:
        cached = {
            "schema_version": 1,
            "days": [
                {"date": "2026-04-24", "commits": 7, "additions": 20, "deletions": 4, "changed": 999, "merges": 1},
                {"date": "2026-04-25", "commits": 2, "additions": 5, "deletions": 1, "changed": 6, "merges": 0},
                {"date": "2026-04-26", "commits": 99, "additions": 99, "deletions": 99, "changed": 198, "merges": 0},
            ],
        }
        profile = {"login": "lReDragol", "created_at": "2024-06-01T08:00:00Z"}
        with (
            mock.patch.object(self.module, "request_json", return_value=(profile, {})),
            mock.patch.object(self.module, "list_repositories", return_value=[]),
        ):
            data = self.module.collect_activity_data(
                "lReDragol",
                "secret-token",
                now=self.now,
                days=4,
                refresh_days=2,
                cached_data=cached,
            )

        self.assertEqual(data["days"][0]["changed"], 24)
        self.assertEqual(data["days"][1]["commits"], 2)
        self.assertEqual(data["days"][2]["commits"], 0)
        self.assertEqual(data["days"][3]["commits"], 0)

    def test_profile_repository_can_be_excluded_from_activity(self) -> None:
        profile_repo = repository_payload("lReDragol", self.recent)
        profile = {"login": "lReDragol", "created_at": "2024-06-01T08:00:00Z"}
        with (
            mock.patch.object(self.module, "request_json", return_value=(profile, {})),
            mock.patch.object(self.module, "list_repositories", return_value=[profile_repo]),
            mock.patch.object(self.module, "list_commits") as list_commits,
        ):
            self.module.collect_activity_data(
                "lReDragol",
                "secret-token",
                now=self.now,
                days=14,
                excluded_repositories={"lReDragol/lReDragol"},
            )
        list_commits.assert_not_called()

    def test_svg_explains_interactive_raw_diff_view(self) -> None:
        data = {
            "username": "lReDragol",
            "title": "lReDragol (Drago)",
            "joined_text": "Joined GitHub 2 years ago",
            "period": {"days": 2},
            "repository_counts": {"public": 17, "private": 5},
            "days": [
                {"date": "2026-04-26", "commits": 2, "additions": 30, "deletions": 4, "changed": 34, "merges": 0},
                {"date": "2026-04-27", "commits": 4, "additions": 70, "deletions": 6, "changed": 76, "merges": 1},
            ],
        }
        svg = self.module.render_activity_card(data)
        self.assertIn("Activity Overview", svg)
        self.assertIn("6 authored commits", svg)
        self.assertIn("+100", svg)
        self.assertIn("-10", svg)
        self.assertIn("17 public + 5 private repos", svg)
        self.assertIn("Click for interactive daily commits and raw diff details", svg)


if __name__ == "__main__":
    unittest.main()
