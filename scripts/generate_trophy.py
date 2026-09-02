from __future__ import annotations

import datetime as dt
import html
import json
import os
import sys
from pathlib import Path


WIDTH = 1160
HEIGHT = 132

THEMES = {
    "light": {
        "background": "#ffffff",
        "card": "#f6f8fa",
        "border": "#d0d7de",
        "title": "#24292f",
        "muted": "#57606a",
        "track": "#d8dee4",
    },
    "dark": {
        "background": "#0d1117",
        "card": "#161b22",
        "border": "#30363d",
        "title": "#f0f6fc",
        "muted": "#8b949e",
        "track": "#30363d",
    },
}

ACCENTS = ["#a371f7", "#58a6ff", "#3fb950", "#d29922", "#f778ba", "#39c5cf", "#ff7b72", "#dbab09"]


def load_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not load {path}: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"Expected an object in {path}")
    return payload


def safe_int(value: object) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def years_since(value: object, now: dt.date) -> int:
    if not isinstance(value, str):
        return 0
    try:
        created = dt.datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return 0
    return max(now.year - created.year - ((now.month, now.day) < (created.month, created.day)), 0)


def build_metrics(stats: dict[str, object], releases: dict[str, object], now: dt.date | None = None) -> list[dict[str, object]]:
    release_totals = releases.get("totals") if isinstance(releases.get("totals"), dict) else {}
    current_date = now or dt.datetime.now(dt.timezone.utc).date()
    public_repositories = safe_int(stats.get("public_repositories"))
    private_repositories = safe_int(stats.get("private_repositories"))
    return [
        {"title": "Stars", "value": safe_int(stats.get("total_stars")), "subtitle": "across owned repos", "target": 100},
        {"title": "Commits", "value": safe_int(stats.get("total_commits")), "subtitle": "authored commits", "target": 2000},
        {"title": "Repositories", "value": public_repositories + private_repositories, "subtitle": f"{public_repositories} public + {private_repositories} private", "target": 100},
        {"title": "Experience", "value": years_since(stats.get("created_at"), current_date), "suffix": "y", "subtitle": "on GitHub", "target": 10},
        {"title": "Followers", "value": safe_int(stats.get("followers")), "subtitle": "GitHub followers", "target": 50},
        {"title": "Releases", "value": safe_int(release_totals.get("releases")), "subtitle": "public releases", "target": 100},
        {"title": "Downloads", "value": safe_int(release_totals.get("downloads")), "subtitle": "release assets", "target": 10000},
        {"title": "Projects", "value": safe_int(release_totals.get("repositories_with_downloads")), "subtitle": "with downloads", "target": 20},
    ]


def format_count(value: int) -> str:
    return f"{value:,}"


def render_trophy(metrics: list[dict[str, object]], *, theme: str) -> str:
    palette = THEMES[theme]
    card_width = 135
    card_height = 116
    gap = 10
    start_x = 5
    cards: list[str] = []

    for index, metric in enumerate(metrics[:8]):
        x = start_x + index * (card_width + gap)
        accent = ACCENTS[index % len(ACCENTS)]
        value = safe_int(metric.get("value"))
        target = max(safe_int(metric.get("target")), 1)
        progress = min(value / target, 1.0)
        progress_width = 101 * progress
        suffix = html.escape(str(metric.get("suffix", "")))
        title = html.escape(str(metric.get("title", "Metric")))
        subtitle = html.escape(str(metric.get("subtitle", "")))
        cards.append(
            f'  <g transform="translate({x},8)">\n'
            f'    <rect width="{card_width}" height="{card_height}" rx="12" fill="{palette["card"]}" stroke="{palette["border"]}"/>\n'
            f'    <text x="67.5" y="20" text-anchor="middle" fill="{palette["title"]}" font-size="12" font-weight="700">{title}</text>\n'
            f'    <circle cx="67.5" cy="48" r="18" fill="{accent}" opacity="0.16"/>\n'
            f'    <path d="M60 39h15v8c0 8-4 13-7.5 13S60 55 60 47z M60 42h-5v4c0 4 2 6 6 7 M75 42h5v4c0 4-2 6-6 7 M64 64h7 M61 68h13" fill="none" stroke="{accent}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>\n'
            f'    <text x="67.5" y="84" text-anchor="middle" fill="{palette["title"]}" font-size="15" font-weight="800">{format_count(value)}{suffix}</text>\n'
            f'    <text x="67.5" y="98" text-anchor="middle" fill="{palette["muted"]}" font-size="8.5">{subtitle}</text>\n'
            f'    <rect x="17" y="106" width="101" height="3" rx="1.5" fill="{palette["track"]}"/>\n'
            f'    <rect x="17" y="106" width="{progress_width:.1f}" height="3" rx="1.5" fill="{accent}"/>\n'
            f'  </g>'
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="GitHub profile achievements">
  <style>text {{ font-family: "Segoe UI", Arial, sans-serif; }}</style>
  <rect width="{WIDTH}" height="{HEIGHT}" rx="16" fill="{palette['background']}"/>
{chr(10).join(cards)}
</svg>
"""


def write_trophies(output_dir: Path, metrics: list[dict[str, object]]) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    light_path = output_dir / "trophy.svg"
    dark_path = output_dir / "trophy-dark.svg"
    light_path.write_text(render_trophy(metrics, theme="light"), encoding="utf-8")
    dark_path.write_text(render_trophy(metrics, theme="dark"), encoding="utf-8")
    return light_path, dark_path


def main() -> int:
    output_dir = Path(os.environ.get("OUTPUT_DIR", "profile"))
    stats_path = Path(os.environ.get("PROFILE_STATS_DATA", output_dir / "stats-data.json"))
    releases_path = Path(os.environ.get("RELEASES_DATA", output_dir / "releases-data.json"))
    try:
        metrics = build_metrics(load_json(stats_path), load_json(releases_path))
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    write_trophies(output_dir, metrics)
    print(json.dumps({str(metric["title"]): metric["value"] for metric in metrics}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
