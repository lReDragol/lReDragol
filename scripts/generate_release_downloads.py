from __future__ import annotations

import datetime as dt
import html
import json
import math
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


API_BASE = "https://api.github.com"
USER_AGENT = "lReDragol-profile-widgets"
SCHEMA_VERSION = 1
CARD_WIDTH = 960
CARD_HEIGHT = 286


def request_json(url: str, token: str | None) -> tuple[object, dict[str, str]]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request) as response:
        payload = json.loads(response.read().decode("utf-8"))
        return payload, {key.lower(): value for key, value in response.headers.items()}


def paginated_list(base_url: str, params: dict[str, object], token: str | None) -> list[dict[str, object]]:
    values: list[dict[str, object]] = []
    page = 1
    while True:
        query = urllib.parse.urlencode({**params, "per_page": 100, "page": page})
        payload, _ = request_json(f"{base_url}?{query}", token)
        if not isinstance(payload, list) or not payload:
            break
        values.extend(item for item in payload if isinstance(item, dict))
        if len(payload) < 100:
            break
        page += 1
    return values


def list_public_repositories(username: str, token: str | None) -> list[dict[str, object]]:
    repositories = paginated_list(
        f"{API_BASE}/users/{username}/repos",
        {"type": "owner", "sort": "updated"},
        token,
    )
    username_lower = username.casefold()
    return [
        repository
        for repository in repositories
        if repository.get("private") is not True
        and isinstance(repository.get("owner"), dict)
        and str(repository["owner"].get("login", "")).casefold() == username_lower
    ]


def list_releases(owner: str, repository: str, token: str | None) -> list[dict[str, object]]:
    try:
        return paginated_list(
            f"{API_BASE}/repos/{owner}/{repository}/releases",
            {},
            token,
        )
    except urllib.error.HTTPError as error:
        if error.code in {403, 404, 409}:
            return []
        raise


def list_release_assets(owner: str, repository: str, release_id: int, token: str | None) -> list[dict[str, object]]:
    try:
        return paginated_list(
            f"{API_BASE}/repos/{owner}/{repository}/releases/{release_id}/assets",
            {},
            token,
        )
    except urllib.error.HTTPError as error:
        if error.code in {403, 404, 409}:
            return []
        raise


def safe_int(value: object) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def public_github_url(value: object) -> str:
    if isinstance(value, str) and value.startswith("https://github.com/"):
        return value
    return ""


def merge_history(cached_data: dict[str, object] | None, date_value: str, total_downloads: int) -> list[dict[str, object]]:
    snapshots: dict[str, dict[str, object]] = {}
    raw_history = cached_data.get("history") if isinstance(cached_data, dict) else None
    if isinstance(raw_history, list):
        for raw in raw_history:
            if not isinstance(raw, dict) or not isinstance(raw.get("date"), str):
                continue
            try:
                dt.date.fromisoformat(raw["date"])
            except ValueError:
                continue
            snapshots[raw["date"]] = {
                "date": raw["date"],
                "downloads": safe_int(raw.get("downloads")),
            }

    snapshots[date_value] = {"date": date_value, "downloads": total_downloads}
    return [snapshots[key] for key in sorted(snapshots)[-365:]]


def collect_release_downloads(
    username: str,
    token: str | None,
    *,
    now: dt.datetime | None = None,
    utc_offset_hours: int = 3,
    cached_data: dict[str, object] | None = None,
) -> dict[str, object]:
    now_utc = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    local_tz = dt.timezone(dt.timedelta(hours=utc_offset_hours))
    snapshot_date = now_utc.astimezone(local_tz).date().isoformat()
    repositories = list_public_repositories(username, token)

    repository_rows: list[dict[str, object]] = []
    all_assets: list[dict[str, object]] = []
    total_releases = 0
    total_assets = 0
    total_downloads = 0

    for repository in repositories:
        name = repository.get("name")
        owner = repository.get("owner")
        if not isinstance(name, str) or not isinstance(owner, dict) or not isinstance(owner.get("login"), str):
            continue
        owner_login = owner["login"]
        published_releases = [release for release in list_releases(owner_login, name, token) if release.get("draft") is not True]
        if not published_releases:
            continue

        repo_assets: list[dict[str, object]] = []
        repo_downloads = 0
        latest_release: dict[str, object] | None = None
        for release in published_releases:
            release_published = release.get("published_at") if isinstance(release.get("published_at"), str) else ""
            if latest_release is None or release_published > str(latest_release.get("published_at", "")):
                latest_release = release

            release_id = safe_int(release.get("id"))
            assets = list_release_assets(owner_login, name, release_id, token) if release_id else release.get("assets")
            if not isinstance(assets, list):
                assets = []
            for asset in assets:
                if not isinstance(asset, dict):
                    continue
                downloads = safe_int(asset.get("download_count"))
                row = {
                    "repository": name,
                    "release": str(release.get("tag_name") or release.get("name") or "release"),
                    "name": str(asset.get("name") or "asset"),
                    "downloads": downloads,
                    "size": safe_int(asset.get("size")),
                    "updated_at": str(asset.get("updated_at") or ""),
                    "url": public_github_url(asset.get("browser_download_url")),
                }
                repo_assets.append(row)
                all_assets.append(row)
                repo_downloads += downloads

        total_releases += len(published_releases)
        total_assets += len(repo_assets)
        total_downloads += repo_downloads
        repository_rows.append(
            {
                "name": name,
                "url": public_github_url(repository.get("html_url")),
                "downloads": repo_downloads,
                "releases": len(published_releases),
                "assets": len(repo_assets),
                "latest_release": str((latest_release or {}).get("tag_name") or (latest_release or {}).get("name") or ""),
                "latest_published_at": str((latest_release or {}).get("published_at") or ""),
            }
        )

    repository_rows.sort(key=lambda item: (-safe_int(item["downloads"]), str(item["name"]).casefold()))
    all_assets.sort(
        key=lambda item: (
            -safe_int(item["downloads"]),
            str(item["repository"]).casefold(),
            str(item["name"]).casefold(),
        )
    )
    history = merge_history(cached_data, snapshot_date, total_downloads)

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_utc.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "username": username,
        "scope": "Published releases and public release assets only",
        "totals": {
            "downloads": total_downloads,
            "releases": total_releases,
            "assets": total_assets,
            "repositories": len(repository_rows),
            "repositories_with_downloads": sum(1 for row in repository_rows if safe_int(row["downloads"]) > 0),
        },
        "repositories": repository_rows,
        "assets": all_assets,
        "history": history,
    }


def load_cached_data(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) and payload.get("schema_version") == SCHEMA_VERSION else None


def format_count(value: int) -> str:
    return f"{value:,}"


def truncated(value: object, limit: int = 24) -> str:
    text = str(value)
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def render_release_card(data: dict[str, object]) -> str:
    totals = data.get("totals") if isinstance(data.get("totals"), dict) else {}
    repositories = data.get("repositories") if isinstance(data.get("repositories"), list) else []
    top_repositories = [row for row in repositories if isinstance(row, dict)][:5]
    total_downloads = safe_int(totals.get("downloads"))
    maximum = max((safe_int(row.get("downloads")) for row in top_repositories), default=1)
    max_log = math.log1p(maximum) or 1.0
    repository_cards: list[str] = []
    for index, row in enumerate(top_repositories):
        x = 34 + index * 180
        downloads = safe_int(row.get("downloads"))
        width = 142 * (math.log1p(downloads) / max_log) if downloads else 0
        name = html.escape(truncated(row.get("name", "repository"), 19))
        repository_cards.append(
            f'  <g transform="translate({x} 207)">\n'
            f'    <rect width="170" height="52" rx="11" class="panel"/>\n'
            f'    <text x="14" y="20" class="rank">#{index + 1}</text>\n'
            f'    <text x="42" y="20" class="repo">{name}</text>\n'
            f'    <text x="14" y="41" class="count">{format_count(downloads)}</text>\n'
            f'    <text x="54" y="41" class="muted">downloads</text>\n'
            f'    <rect x="14" y="48" width="142" height="3" rx="1.5" fill="#21262d"/>\n'
            f'    <rect x="14" y="48" width="{width:.1f}" height="3" rx="1.5" fill="url(#downloadsGradient)"/>\n'
            f'  </g>'
        )

    if not repository_cards:
        repository_cards.append('  <text x="34" y="235" class="muted">No published release downloads yet</text>')

    history = data.get("history") if isinstance(data.get("history"), list) else []
    delta_value = "NEW"
    delta_caption = "tracking started"
    delta_color = "#58a6ff"
    if len(history) >= 2 and isinstance(history[-1], dict) and isinstance(history[-2], dict):
        delta = safe_int(history[-1].get("downloads")) - safe_int(history[-2].get("downloads"))
        delta_value = f"{delta:+,}"
        delta_caption = "since last snapshot"
        delta_color = "#39d353" if delta >= 0 else "#f85149"

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{CARD_WIDTH}" height="{CARD_HEIGHT}" viewBox="0 0 {CARD_WIDTH} {CARD_HEIGHT}" role="img" aria-label="Release downloads: {total_downloads} total">
  <style>
    text {{ font-family: "Segoe UI", Arial, sans-serif; }}
    .title {{ fill: #f0f6fc; font-size: 25px; font-weight: 750; }}
    .muted {{ fill: #8b949e; font-size: 11px; }}
    .eyebrow {{ fill: #8b949e; font-size: 10px; font-weight: 700; letter-spacing: 1px; }}
    .metric {{ fill: #f0f6fc; font-size: 29px; font-weight: 800; }}
    .total {{ fill: #39d353; font-size: 40px; font-weight: 800; }}
    .panel {{ fill: #161b22; stroke: #30363d; stroke-width: 1; }}
    .rank {{ fill: #39d353; font-size: 11px; font-weight: 800; }}
    .repo {{ fill: #c9d1d9; font-size: 11px; font-weight: 650; }}
    .count {{ fill: #f0f6fc; font-size: 12px; font-weight: 750; }}
  </style>
  <defs>
    <linearGradient id="cardBg" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#0d1117"/><stop offset="100%" stop-color="#111926"/></linearGradient>
    <linearGradient id="downloadsGradient" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="#238636"/><stop offset="100%" stop-color="#39d353"/></linearGradient>
  </defs>
  <rect width="960" height="286" rx="24" fill="url(#cardBg)"/>
  <rect x="1" y="1" width="958" height="284" rx="23" fill="none" stroke="#30363d"/>
  <text x="34" y="42" class="title">Release Downloads</text>
  <text x="926" y="39" class="muted" text-anchor="end">Updated daily · public release assets</text>

  <g transform="translate(34 66)">
    <rect width="232" height="98" rx="14" fill="#101923" stroke="#238636" stroke-opacity=".65"/>
    <text x="20" y="25" class="eyebrow">TOTAL DOWNLOADS</text>
    <text x="20" y="70" class="total">{format_count(total_downloads)}</text>
    <circle cx="205" cy="25" r="5" fill="#39d353"/>
    <circle cx="205" cy="25" r="10" fill="#39d353" opacity=".12"/>
  </g>
  <g transform="translate(278 66)">
    <rect width="148" height="98" rx="14" class="panel"/>
    <text x="18" y="28" class="eyebrow">PROJECTS</text>
    <text x="18" y="67" class="metric">{safe_int(totals.get('repositories_with_downloads'))}</text>
    <text x="18" y="85" class="muted">with downloads</text>
  </g>
  <g transform="translate(438 66)">
    <rect width="148" height="98" rx="14" class="panel"/>
    <text x="18" y="28" class="eyebrow">RELEASES</text>
    <text x="18" y="67" class="metric">{safe_int(totals.get('releases'))}</text>
    <text x="18" y="85" class="muted">published</text>
  </g>
  <g transform="translate(598 66)">
    <rect width="148" height="98" rx="14" class="panel"/>
    <text x="18" y="28" class="eyebrow">ASSETS</text>
    <text x="18" y="67" class="metric">{safe_int(totals.get('assets'))}</text>
    <text x="18" y="85" class="muted">downloadable files</text>
  </g>
  <g transform="translate(758 66)">
    <rect width="168" height="98" rx="14" class="panel"/>
    <text x="18" y="28" class="eyebrow">LATEST CHANGE</text>
    <text x="18" y="64" fill="{delta_color}" font-size="22" font-weight="800">{html.escape(delta_value)}</text>
    <text x="18" y="85" class="muted">{html.escape(delta_caption)}</text>
  </g>

  <text x="34" y="193" class="eyebrow">MOST DOWNLOADED PROJECTS</text>
  <text x="926" y="193" class="muted" text-anchor="end">Open interactive breakdown →</text>
{chr(10).join(repository_cards)}
</svg>
"""


def write_outputs(output_dir: Path, data: dict[str, object]) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    data_path = output_dir / "releases-data.json"
    svg_path = output_dir / "releases-dark.svg"
    data_path.write_text(json.dumps(data, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    svg_path.write_text(render_release_card(data), encoding="utf-8")
    return data_path, svg_path


def main() -> int:
    username = os.environ.get("GITHUB_USER") or os.environ.get("GITHUB_REPOSITORY_OWNER")
    token = os.environ.get("GITHUB_TOKEN") or None
    output_dir = Path(os.environ.get("OUTPUT_DIR", "profile"))
    utc_offset_hours = int(os.environ.get("UTC_OFFSET", "3"))
    if not username:
        print("GITHUB_USER or GITHUB_REPOSITORY_OWNER is required.", file=sys.stderr)
        return 1

    data_path = output_dir / "releases-data.json"
    data = collect_release_downloads(
        username,
        token,
        utc_offset_hours=utc_offset_hours,
        cached_data=load_cached_data(data_path),
    )
    write_outputs(output_dir, data)
    print(json.dumps({"generated_at": data["generated_at"], "totals": data["totals"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
