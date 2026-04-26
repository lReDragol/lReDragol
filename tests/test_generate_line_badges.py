import datetime as dt
import importlib.util
import pathlib
import unittest
from unittest import mock
from urllib.parse import urlparse


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "generate_line_badges.py"


def load_module():
    spec = importlib.util.spec_from_file_location("generate_line_badges", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def isoformat_z(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def repository_payload(name: str, pushed_at: str) -> dict[str, object]:
    return {
        "name": name,
        "archived": False,
        "pushed_at": pushed_at,
        "owner": {"login": "lReDragol"},
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


class CollectStatsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()
        self.now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        self.recent = isoformat_z(self.now - dt.timedelta(hours=1))
        self.public_repo = repository_payload("public-one", self.recent)
        self.private_repo = repository_payload("private-one", self.recent)

    def fake_request_json(self, url: str, token: str | None):
        path = urlparse(url).path

        if path == "/user/repos":
            self.assertEqual(token, "secret-token")
            return ([self.public_repo, self.private_repo], {})

        if path == "/users/lReDragol/repos":
            return ([self.public_repo], {})

        if path == "/repos/lReDragol/public-one/commits":
            return ([commit_payload("pub-sha", self.recent)], {})

        if path == "/repos/lReDragol/private-one/commits":
            return ([commit_payload("priv-sha", self.recent)], {})

        if path == "/repos/lReDragol/public-one/commits/pub-sha":
            return ({"stats": {"additions": 10, "deletions": 2}}, {})

        if path == "/repos/lReDragol/private-one/commits/priv-sha":
            return ({"stats": {"additions": 30, "deletions": 5}}, {})

        raise AssertionError(f"Unexpected URL: {url}")

    def test_collect_stats_includes_private_repositories_when_token_is_available(self) -> None:
        with mock.patch.object(self.module, "request_json", side_effect=self.fake_request_json):
            stats = self.module.collect_stats("lReDragol", "secret-token")

        self.assertEqual(stats["7d"], (40, 7))
        self.assertEqual(stats["30d"], (40, 7))

    def test_collect_stats_falls_back_to_public_repositories_without_token(self) -> None:
        with mock.patch.object(self.module, "request_json", side_effect=self.fake_request_json):
            stats = self.module.collect_stats("lReDragol", None)

        self.assertEqual(stats["7d"], (10, 2))
        self.assertEqual(stats["30d"], (10, 2))


if __name__ == "__main__":
    unittest.main()
