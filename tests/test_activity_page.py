import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class ActivityPageTests(unittest.TestCase):
    def test_page_loads_aggregate_data_and_supports_hover_metrics(self) -> None:
        html = (ROOT / "activity" / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "activity" / "app.js").read_text(encoding="utf-8")

        self.assertIn("Privacy-safe aggregate", html)
        self.assertIn('data-metric="commits"', html)
        self.assertIn('data-metric="changed"', html)
        self.assertIn('../profile/activity-data.json', javascript)
        self.assertIn("showDetailsTooltip", javascript)
        self.assertIn("Merge commits", javascript)
        self.assertIn("Release Downloads", html)
        self.assertIn('../profile/releases-data.json', javascript)
        self.assertIn("renderReleases", javascript)

    def test_page_does_not_expect_private_identifiers(self) -> None:
        javascript = (ROOT / "activity" / "app.js").read_text(encoding="utf-8")
        for forbidden in ("repo_name", "repository_name", "commit_sha", "commit_message", "file_path"):
            self.assertNotIn(forbidden, javascript)

    def test_private_collection_precedes_pinned_third_party_action(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "profile-widgets.yml").read_text(encoding="utf-8")
        private_collection = workflow.index("Generate activity overview")
        third_party_action = workflow.index("vn7n24fzkq/github-profile-summary-cards@")

        self.assertLess(private_collection, third_party_action)
        action_ref = workflow[third_party_action:].splitlines()[0].split("@", 1)[1]
        self.assertRegex(action_ref, r"^[0-9a-f]{40}$")
        self.assertNotIn("github-profile-trophy.vercel.app", workflow)
        self.assertIn("generate_release_downloads.py", workflow)
        self.assertIn("generate_trophy.py", workflow)


if __name__ == "__main__":
    unittest.main()
