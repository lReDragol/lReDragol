from __future__ import annotations

import re
import sys
from pathlib import Path


PROFILE_SVG_PATTERN = re.compile(r"(\./profile/[A-Za-z0-9-]+\.svg)(?:\?v=[A-Za-z0-9._-]+)?")


def update_cache_bust_tokens(readme_text: str, token: str) -> str:
    return PROFILE_SVG_PATTERN.sub(lambda match: f"{match.group(1)}?v={token}", readme_text)


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: update_readme_cache_bust.py <README path> <token>", file=sys.stderr)
        return 1

    readme_path = Path(sys.argv[1])
    token = sys.argv[2].strip()
    if not token:
        print("Cache-bust token must not be empty.", file=sys.stderr)
        return 1

    original = readme_path.read_text(encoding="utf-8")
    updated = update_cache_bust_tokens(original, token)
    if updated != original:
        readme_path.write_text(updated, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
