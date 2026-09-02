import datetime as dt
import importlib.util
import pathlib
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "generate_release_downloads.py"


def load_module(test_case: unittest.TestCase):
    test_case.assertTrue(MODULE_PATH.exists())
    spec = importlib.util.spec_from_file_location("generate_release_downloads", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def repository(name: str, *, owner: str = "lReDragol", private: bool = False) -> dict[str, object]:
    return {
        "name": name,
        "private": private,
        "html_url": f"https://github.com/{owner}/{name}",
        "owner": {"login": owner},
    }


class ReleaseDownloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module(self)

    def test_public_repository_listing_excludes_private_and_other_owners(self) -> None:
        values = [repository("public"), repository("secret", private=True), repository("team", owner="OtherOrg")]
        with mock.patch.object(self.module, "paginated_list", return_value=values):
            repositories = self.module.list_public_repositories("lReDragol", "token")
        self.assertEqual([item["name"] for item in repositories], ["public"])

    def test_collects_only_published_release_assets_and_preserves_history(self) -> None:
        releases = [
            {
                "draft": True,
                "id": 1,
                "tag_name": "draft",
                "published_at": None,
                "assets": [{"name": "secret.zip", "download_count": 999}],
            },
            {
                "draft": False,
                "id": 2,
                "tag_name": "v2",
                "published_at": "2026-09-01T12:00:00Z",
                "assets": [
                    {
                        "name": "tool.exe",
                        "download_count": 12,
                        "size": 1024,
                        "updated_at": "2026-09-01T12:00:00Z",
                        "browser_download_url": "https://github.com/lReDragol/tool/releases/download/v2/tool.exe",
                    },
                    {
                        "name": "notes.txt",
                        "download_count": 3,
                        "size": 20,
                        "updated_at": "2026-09-01T12:00:00Z",
                        "browser_download_url": "https://example.com/not-published",
                    },
                ],
            },
        ]
        cached = {"history": [{"date": "2026-09-02", "downloads": 10}]}
        with (
            mock.patch.object(self.module, "list_public_repositories", return_value=[repository("tool")]),
            mock.patch.object(self.module, "list_releases", return_value=releases),
            mock.patch.object(self.module, "list_release_assets", return_value=releases[1]["assets"]),
        ):
            data = self.module.collect_release_downloads(
                "lReDragol",
                "token",
                now=dt.datetime(2026, 9, 3, 9, 0, tzinfo=dt.timezone.utc),
                cached_data=cached,
            )

        self.assertEqual(
            data["totals"],
            {"downloads": 15, "releases": 1, "assets": 2, "repositories": 1, "repositories_with_downloads": 1},
        )
        self.assertEqual(data["repositories"][0]["latest_release"], "v2")
        self.assertEqual(data["assets"][0]["name"], "tool.exe")
        self.assertEqual(data["assets"][1]["url"], "")
        self.assertEqual(data["history"], [{"date": "2026-09-02", "downloads": 10}, {"date": "2026-09-03", "downloads": 15}])
        self.assertNotIn("secret.zip", str(data))

    def test_render_card_uses_summary_tiles_and_escapes_names(self) -> None:
        data = {
            "totals": {"downloads": 100, "releases": 2, "assets": 3, "repositories_with_downloads": 1},
            "repositories": [{"name": "repo<script>", "downloads": 100}],
            "history": [{"date": "2026-09-03", "downloads": 100}],
        }
        svg = self.module.render_release_card(data)
        self.assertIn("TOTAL DOWNLOADS", svg)
        self.assertIn("MOST DOWNLOADED PROJECTS", svg)
        self.assertIn("LATEST CHANGE", svg)
        self.assertIn("repo&lt;script&gt;", svg)
        self.assertNotIn("repo<script>", svg)


if __name__ == "__main__":
    unittest.main()
