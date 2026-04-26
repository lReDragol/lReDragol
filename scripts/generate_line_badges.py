from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


API_BASE = "https://api.github.com"
USER_AGENT = "lReDragol-profile-widgets"
SVG_WIDTH = 360
SVG_HEIGHT = 36


def isoformat_z(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
        response_headers = {k.lower(): v for k, v in response.headers.items()}
        return payload, response_headers


def list_repositories_from_url(base_url: str, query_params: dict[str, object], token: str | None) -> list[dict[str, object]]:
    repositories: list[dict[str, object]] = []
    page = 1

    while True:
        query = urllib.parse.urlencode({**query_params, "per_page": 100, "page": page})
        url = f"{base_url}?{query}"
        payload, _ = request_json(url, token)
        if not isinstance(payload, list) or not payload:
            break

        repositories.extend(repo for repo in payload if isinstance(repo, dict))
        if len(payload) < 100:
            break
        page += 1

    return repositories


def list_repositories(username: str, token: str | None) -> list[dict[str, object]]:
    if token:
        try:
            repositories = list_repositories_from_url(
                f"{API_BASE}/user/repos",
                {
                    "visibility": "all",
                    "affiliation": "owner,collaborator,organization_member",
                    "sort": "updated",
                },
                token,
            )
        except urllib.error.HTTPError as error:
            if error.code not in {401, 403, 404}:
                raise
        else:
            if repositories:
                return repositories

    return list_repositories_from_url(
        f"{API_BASE}/users/{username}/repos",
        {
            "type": "owner",
            "sort": "updated",
        },
        token,
    )


def list_commits(owner: str, repo: str, author: str, since: dt.datetime, token: str | None) -> list[dict[str, object]]:
    commits: list[dict[str, object]] = []
    page = 1

    while True:
        query = urllib.parse.urlencode(
            {
                "author": author,
                "since": isoformat_z(since),
                "per_page": 100,
                "page": page,
            }
        )
        url = f"{API_BASE}/repos/{owner}/{repo}/commits?{query}"
        try:
            payload, _ = request_json(url, token)
        except urllib.error.HTTPError as error:
            if error.code in {409, 422}:
                return commits
            raise

        if not isinstance(payload, list) or not payload:
            break

        commits.extend(commit for commit in payload if isinstance(commit, dict))
        if len(payload) < 100:
            break
        page += 1

    return commits


def commit_stats(owner: str, repo: str, sha: str, token: str | None) -> tuple[int, int]:
    url = f"{API_BASE}/repos/{owner}/{repo}/commits/{sha}"
    try:
        payload, _ = request_json(url, token)
    except urllib.error.HTTPError as error:
        if error.code in {409, 422}:
            return 0, 0
        raise

    if not isinstance(payload, dict):
        return 0, 0

    stats = payload.get("stats")
    if not isinstance(stats, dict):
        return 0, 0

    additions = int(stats.get("additions", 0) or 0)
    deletions = int(stats.get("deletions", 0) or 0)
    return additions, deletions


def parse_commit_date(commit: dict[str, object]) -> dt.datetime | None:
    commit_info = commit.get("commit")
    if not isinstance(commit_info, dict):
        return None

    author_info = commit_info.get("author")
    if not isinstance(author_info, dict):
        return None

    raw_date = author_info.get("date")
    if not isinstance(raw_date, str):
        return None

    try:
        return dt.datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
    except ValueError:
        return None


def format_number(value: int) -> str:
    return f"{value:,}"


def repo_recent_enough(repository: dict[str, object], cutoff: dt.datetime) -> bool:
    pushed_at = repository.get("pushed_at")
    if not isinstance(pushed_at, str):
        return False

    try:
        pushed_at_dt = dt.datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
    except ValueError:
        return False

    return pushed_at_dt >= cutoff


def svg_badge(label: str, additions: int, deletions: int) -> str:
    label_x = 18
    plus_x = 126
    slash_x = 236
    minus_x = 258
    y = 23

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_WIDTH}" height="{SVG_HEIGHT}" viewBox="0 0 {SVG_WIDTH} {SVG_HEIGHT}" role="img" aria-label="{label}: +{additions} / -{deletions}">
  <rect width="{SVG_WIDTH}" height="{SVG_HEIGHT}" rx="10" fill="#161b22"/>
  <rect x="1" y="1" width="{SVG_WIDTH - 2}" height="{SVG_HEIGHT - 2}" rx="9" fill="#161b22" stroke="#30363d"/>
  <rect x="1" y="1" width="104" height="{SVG_HEIGHT - 2}" rx="9" fill="#0d1117"/>
  <text x="{label_x}" y="{y}" fill="#f0f6fc" font-family="Segoe UI, DejaVu Sans, Arial, sans-serif" font-size="13" font-weight="700">{label}</text>
  <text x="{plus_x}" y="{y}" fill="#3fb950" font-family="Segoe UI, DejaVu Sans, Arial, sans-serif" font-size="13" font-weight="700">+{format_number(additions)}</text>
  <text x="{slash_x}" y="{y}" fill="#8b949e" font-family="Segoe UI, DejaVu Sans, Arial, sans-serif" font-size="13" font-weight="700">/</text>
  <text x="{minus_x}" y="{y}" fill="#f85149" font-family="Segoe UI, DejaVu Sans, Arial, sans-serif" font-size="13" font-weight="700">-{format_number(deletions)}</text>
</svg>
"""


def write_badges(output_dir: Path, stats: dict[str, tuple[int, int]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "lines-7d.svg").write_text(svg_badge("LINES 7D", *stats["7d"]), encoding="utf-8")
    (output_dir / "lines-30d.svg").write_text(svg_badge("LINES 30D", *stats["30d"]), encoding="utf-8")


def collect_stats(username: str, token: str | None) -> dict[str, tuple[int, int]]:
    now = dt.datetime.now(dt.timezone.utc)
    cutoff_7d = now - dt.timedelta(days=7)
    cutoff_30d = now - dt.timedelta(days=30)

    totals = {
        "7d": [0, 0],
        "30d": [0, 0],
    }

    repositories = list_repositories(username, token)
    seen_shas: set[str] = set()

    for repository in repositories:
        if repository.get("archived") is True or not repo_recent_enough(repository, cutoff_30d):
            continue

        owner = repository.get("owner")
        if not isinstance(owner, dict):
            continue

        owner_login = owner.get("login")
        repo_name = repository.get("name")
        if not isinstance(owner_login, str) or not isinstance(repo_name, str):
            continue

        for commit in list_commits(owner_login, repo_name, username, cutoff_30d, token):
            sha = commit.get("sha")
            if not isinstance(sha, str) or sha in seen_shas:
                continue

            seen_shas.add(sha)
            commit_date = parse_commit_date(commit)
            if commit_date is None:
                continue

            additions, deletions = commit_stats(owner_login, repo_name, sha, token)
            totals["30d"][0] += additions
            totals["30d"][1] += deletions

            if commit_date >= cutoff_7d:
                totals["7d"][0] += additions
                totals["7d"][1] += deletions

    return {
        "7d": (totals["7d"][0], totals["7d"][1]),
        "30d": (totals["30d"][0], totals["30d"][1]),
    }


def main() -> int:
    username = os.environ.get("GITHUB_USER") or os.environ.get("GITHUB_REPOSITORY_OWNER")
    token = os.environ.get("GITHUB_TOKEN") or None
    output_dir = Path(os.environ.get("OUTPUT_DIR", "profile"))

    if not username:
        print("GITHUB_USER or GITHUB_REPOSITORY_OWNER is required.", file=sys.stderr)
        return 1

    stats = collect_stats(username, token)
    write_badges(output_dir, stats)
    print(json.dumps(stats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
