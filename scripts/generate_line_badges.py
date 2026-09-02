from __future__ import annotations

import json
import os
import sys
from pathlib import Path


SVG_WIDTH = 360
SVG_HEIGHT = 36


def normalized_day(value: object) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    try:
        return {
            "additions": max(int(value.get("additions", 0) or 0), 0),
            "deletions": max(int(value.get("deletions", 0) or 0), 0),
        }
    except (TypeError, ValueError):
        return None


def summarize_activity(data: dict[str, object], period_days: int) -> tuple[int, int]:
    raw_days = data.get("days")
    if not isinstance(raw_days, list):
        raise ValueError("activity data must contain a days list")
    days = [day for raw in raw_days if (day := normalized_day(raw))]
    selected = days[-period_days:]
    return (
        sum(day["additions"] for day in selected),
        sum(day["deletions"] for day in selected),
    )


def format_number(value: int) -> str:
    return f"{value:,}"


def svg_badge(label: str, additions: int, deletions: int) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_WIDTH}" height="{SVG_HEIGHT}" viewBox="0 0 {SVG_WIDTH} {SVG_HEIGHT}" role="img" aria-label="{label} raw Git diff: +{additions} / -{deletions}">
  <rect width="{SVG_WIDTH}" height="{SVG_HEIGHT}" rx="10" fill="#161b22"/>
  <rect x="1" y="1" width="{SVG_WIDTH - 2}" height="{SVG_HEIGHT - 2}" rx="9" fill="#161b22" stroke="#30363d"/>
  <rect x="1" y="1" width="104" height="{SVG_HEIGHT - 2}" rx="9" fill="#0d1117"/>
  <text x="18" y="23" fill="#f0f6fc" font-family="Segoe UI, DejaVu Sans, Arial, sans-serif" font-size="13" font-weight="700">{label}</text>
  <text x="126" y="23" fill="#3fb950" font-family="Segoe UI, DejaVu Sans, Arial, sans-serif" font-size="13" font-weight="700">+{format_number(additions)}</text>
  <text x="236" y="23" fill="#8b949e" font-family="Segoe UI, DejaVu Sans, Arial, sans-serif" font-size="13" font-weight="700">/</text>
  <text x="258" y="23" fill="#f85149" font-family="Segoe UI, DejaVu Sans, Arial, sans-serif" font-size="13" font-weight="700">-{format_number(deletions)}</text>
</svg>
"""


def write_badges(output_dir: Path, data: dict[str, object]) -> dict[str, tuple[int, int]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stats = {"7d": summarize_activity(data, 7), "30d": summarize_activity(data, 30)}
    (output_dir / "lines-7d.svg").write_text(svg_badge("DIFF 7D", *stats["7d"]), encoding="utf-8")
    (output_dir / "lines-30d.svg").write_text(svg_badge("DIFF 30D", *stats["30d"]), encoding="utf-8")
    return stats


def main() -> int:
    output_dir = Path(os.environ.get("OUTPUT_DIR", "profile"))
    data_path = Path(os.environ.get("ACTIVITY_DATA", output_dir / "activity-data.json"))
    if not data_path.exists():
        print(f"Activity data not found: {data_path}", file=sys.stderr)
        return 1
    try:
        data = json.loads(data_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        print(f"Invalid activity data: {error}", file=sys.stderr)
        return 1
    if not isinstance(data, dict):
        print("Activity data root must be an object.", file=sys.stderr)
        return 1

    print(json.dumps(write_badges(output_dir, data)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
