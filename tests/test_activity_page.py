import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class ActivityPageTests(unittest.TestCase):
    def test_page_loads_aggregate_data_and_supports_hover_metrics(self) -> None:
        html = (ROOT / "activity" / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "activity" / "app.js").read_text(encoding="utf-8")

        self.assertNotIn("Privacy-safe aggregate", html)
        self.assertNotIn("Private repository names, commit IDs", html)
        self.assertIn('data-metric="commits"', html)
        self.assertIn('data-metric="changed"', html)
        self.assertIn('../profile/activity-data.json', javascript)
        self.assertIn("showDetailsTooltip", javascript)
        self.assertIn("Merge commits", javascript)
        self.assertIn("Release Downloads", html)
        self.assertIn('../profile/releases-data.json', javascript)
        self.assertIn("renderReleases", javascript)
        self.assertIn('id="repository-list"', html)
        self.assertIn("aggregateRepositories", javascript)
        self.assertIn("renderRepositoryActivity", javascript)
        self.assertIn('cell.addEventListener("click"', javascript)
        self.assertIn('cell.addEventListener("mouseenter"', javascript)

    def test_page_does_not_expect_private_identifiers(self) -> None:
        javascript = (ROOT / "activity" / "app.js").read_text(encoding="utf-8")
        for forbidden in ("repo_name", "repository_name", "commit_sha", "commit_message", "file_path"):
            self.assertNotIn(forbidden, javascript)

    def test_private_collection_and_top_languages_use_local_generators(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "profile-widgets.yml").read_text(encoding="utf-8")
        private_collection = workflow.index("Generate activity overview")
        languages_collection = workflow.index("Generate top languages")

        self.assertLess(private_collection, languages_collection)
        self.assertNotIn("github-profile-summary-cards@", workflow)
        self.assertNotIn("github-profile-trophy.vercel.app", workflow)
        self.assertIn("generate_release_downloads.py", workflow)
        self.assertIn("generate_trophy.py", workflow)
        self.assertIn("generate_top_languages.py", workflow)
        self.assertIn("profile/languages-data.json", workflow)


if __name__ == "__main__":
    unittest.main()
