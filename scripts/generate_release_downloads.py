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
CARD_HEIGHT = 310


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
    return text if len(text) <= limit else f"{text[: limit - 1]}..."


def render_release_card(data: dict[str, object]) -> str:
    totals = data.get("totals") if isinstance(data.get("totals"), dict) else {}
    repositories = data.get("repositories") if isinstance(data.get("repositories"), list) else []
    top_repositories = [row for row in repositories if isinstance(row, dict)][:5]
    total_downloads = safe_int(totals.get("downloads"))
    maximum = max((safe_int(row.get("downloads")) for row in top_repositories), default=1)
    max_log = math.log1p(maximum) or 1.0
    bar_rows: list[str] = []
    for index, row in enumerate(top_repositories):
        y = 103 + index * 37
        downloads = safe_int(row.get("downloads"))
        width = 490 * (math.log1p(downloads) / max_log) if downloads else 0
        name = html.escape(truncated(row.get("name", "repository")))
        bar_rows.append(
            f'  <text x="326" y="{y}" class="label">{name}</text>\n'
            f'  <rect x="486" y="{y - 12}" width="490" height="14" rx="7" fill="#161b22"/>\n'
            f'  <rect x="486" y="{y - 12}" width="{width:.1f}" height="14" rx="7" fill="url(#downloadsGradient)"/>\n'
            f'  <text x="944" y="{y}" class="value" text-anchor="end">{format_count(downloads)}</text>'
        )

    history = data.get("history") if isinstance(data.get("history"), list) else []
    delta_text = "Daily history starts with this snapshot"
    if len(history) >= 2 and isinstance(history[-1], dict) and isinstance(history[-2], dict):
        delta = safe_int(history[-1].get("downloads")) - safe_int(history[-2].get("downloads"))
        delta_text = f"{delta:+,} since previous daily snapshot"

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{CARD_WIDTH}" height="{CARD_HEIGHT}" viewBox="0 0 {CARD_WIDTH} {CARD_HEIGHT}" role="img" aria-label="Release downloads: {total_downloads} total">
  <style>
    .title {{ font-family: "Segoe UI", Arial, sans-serif; fill: #f0f6fc; font-size: 27px; font-weight: 700; }}
    .muted {{ font-family: "Segoe UI", Arial, sans-serif; fill: #8b949e; font-size: 12px; }}
    .label {{ font-family: "Segoe UI", Arial, sans-serif; fill: #c9d1d9; font-size: 12px; font-weight: 600; }}
    .value {{ font-family: "Segoe UI", Arial, sans-serif; fill: #f0f6fc; font-size: 12px; font-weight: 700; }}
  </style>
  <defs>
    <linearGradient id="cardBg" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#0d1117"/><stop offset="100%" stop-color="#111926"/></linearGradient>
    <linearGradient id="downloadsGradient" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="#238636"/><stop offset="100%" stop-color="#39d353"/></linearGradient>
  </defs>
  <rect width="960" height="310" rx="24" fill="url(#cardBg)"/>
  <rect x="1" y="1" width="958" height="308" rx="23" fill="none" stroke="#30363d"/>
  <text x="34" y="47" class="title">Release Downloads</text>
  <text x="926" y="43" class="muted" text-anchor="end">Updated daily · public GitHub release assets</text>

  <text x="34" y="111" fill="#39d353" font-family="Segoe UI,Arial,sans-serif" font-size="42" font-weight="800">{format_count(total_downloads)}</text>
  <text x="34" y="135" class="muted">total downloads</text>
  <text x="34" y="180" class="value" font-size="19">{safe_int(totals.get('repositories_with_downloads'))}</text>
  <text x="64" y="180" class="muted">projects</text>
  <text x="144" y="180" class="value" font-size="19">{safe_int(totals.get('releases'))}</text>
  <text x="182" y="180" class="muted">releases</text>
  <text x="34" y="215" class="value" font-size="19">{safe_int(totals.get('assets'))}</text>
  <text x="69" y="215" class="muted">assets</text>
  <text x="34" y="250" class="muted">{html.escape(delta_text)}</text>

  <text x="326" y="67" class="label" font-size="14">TOP REPOSITORIES / LOG SCALE</text>
{chr(10).join(bar_rows)}
  <text x="326" y="289" class="muted">Click for interactive repositories, releases, and assets</text>
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
