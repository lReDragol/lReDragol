from __future__ import annotations

import importlib.util
import pathlib
import unittest
from unittest import mock


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "generate_profile_stats.py"


def load_module(test_case: unittest.TestCase):
    test_case.assertTrue(MODULE_PATH.exists(), f"Missing generator script: {MODULE_PATH}")
    spec = importlib.util.spec_from_file_location("generate_profile_stats", MODULE_PATH)
    test_case.assertIsNotNone(spec)
    test_case.assertIsNotNone(spec.loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def repo_payload(name: str, *, owner: str, private: bool, stars: int) -> dict[str, object]:
    return {
        "name": name,
        "private": private,
        "archived": False,
        "stargazers_count": stars,
        "owner": {"login": owner},
    }


def commit_payload(sha: str) -> dict[str, object]:
    return {
        "sha": sha,
        "commit": {"author": {"date": "2026-04-27T00:00:00Z"}},
    }


class GenerateProfileStatsTests(unittest.TestCase):
    def test_collect_profile_stats_counts_private_owned_stars_and_accessible_contributions(self) -> None:
        module = load_module(self)

        repositories = [
            repo_payload("public-one", owner="lReDragol", private=False, stars=5),
            repo_payload("private-one", owner="lReDragol", private=True, stars=7),
            repo_payload("team-tool", owner="OtherOrg", private=True, stars=99),
        ]

        responses = {
            "https://api.github.com/user/repos?visibility=all&affiliation=owner%2Ccollaborator%2Corganization_member&sort=updated&per_page=100&page=1": repositories,
            "https://api.github.com/repos/lReDragol/public-one/commits?author=lReDragol&per_page=100&page=1": [
                commit_payload("a1"),
                commit_payload("a2"),
            ],
            "https://api.github.com/repos/lReDragol/private-one/commits?author=lReDragol&per_page=100&page=1": [
                commit_payload("b1"),
            ],
            "https://api.github.com/repos/OtherOrg/team-tool/commits?author=lReDragol&per_page=100&page=1": [
                commit_payload("c1"),
            ],
            "https://api.github.com/search/issues?q=author%3AlReDragol+is%3Apr&per_page=1": {"total_count": 4},
            "https://api.github.com/search/issues?q=author%3AlReDragol+is%3Aissue&per_page=1": {"total_count": 6},
        }

        def fake_request(url: str, token: str | None):
            self.assertEqual(token, "secret-token")
            self.assertIn(url, responses, f"Unexpected URL: {url}")
            return responses[url], {}

        with mock.patch.object(module, "request_json", side_effect=fake_request):
            stats = module.collect_profile_stats("lReDragol", "secret-token")

        self.assertEqual(
            stats,
            {
                "total_stars": 12,
                "total_commits": 4,
                "total_prs": 4,
                "total_issues": 6,
                "contributed_to": 3,
            },
        )

    def test_render_stats_card_mentions_private_repositories(self) -> None:
        module = load_module(self)

        svg = module.render_stats_card(
            {
                "total_stars": 39,
                "total_commits": 242,
                "total_prs": 1,
                "total_issues": 1,
                "contributed_to": 33,
            },
            theme="dark",
        )

        self.assertIn("Total Stars", svg)
        self.assertIn("242", svg)
        self.assertIn("Contributed to", svg)
        self.assertIn("Includes private repos", svg)


if __name__ == "__main__":
    unittest.main()
