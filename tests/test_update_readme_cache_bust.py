from __future__ import annotations

import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "update_readme_cache_bust.py"


def load_module(test_case: unittest.TestCase):
    test_case.assertTrue(MODULE_PATH.exists(), f"Missing cache-bust script: {MODULE_PATH}")
    spec = importlib.util.spec_from_file_location("update_readme_cache_bust", MODULE_PATH)
    test_case.assertIsNotNone(spec)
    test_case.assertIsNotNone(spec.loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class UpdateReadmeCacheBustTests(unittest.TestCase):
    def test_rewrites_all_profile_svg_references_with_new_token(self) -> None:
        module = load_module(self)
        original = """
<img src="./profile/activity-dark.svg">
<img src="./profile/stats.svg?v=old-token">
[![trophy](./profile/trophy.svg)](https://example.com)
<img src="https://example.com/keep.svg">
"""

        updated = module.update_cache_bust_tokens(original, "20260427-233000")

        self.assertIn('./profile/activity-dark.svg?v=20260427-233000', updated)
        self.assertIn('./profile/stats.svg?v=20260427-233000', updated)
        self.assertIn('./profile/trophy.svg?v=20260427-233000', updated)
        self.assertIn('https://example.com/keep.svg', updated)


if __name__ == "__main__":
    unittest.main()
