from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


API_BASE = "https://api.github.com"
USER_AGENT = "lReDragol-profile-widgets"
CARD_WIDTH = 340
CARD_HEIGHT = 200

THEMES = {
    "light": {
        "background": "#ffffff",
        "border": "#d0d7de",
        "title": "#0969da",
        "text": "#57606a",
        "value": "#24292f",
        "divider": "#d8dee4",
        "accent": "#1f883d",
    },
    "dark": {
        "background": "#0d1117",
        "border": "#30363d",
        "title": "#2f81f7",
        "text": "#8b949e",
        "value": "#f0f6fc",
        "divider": "#21262d",
        "accent": "#3fb950",
    },
}


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
        response_headers = {key.lower(): value for key, value in response.headers.items()}
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


def list_commits(owner: str, repo: str, author: str, token: str | None) -> list[dict[str, object]]:
    commits: list[dict[str, object]] = []
    page = 1

    while True:
        query = urllib.parse.urlencode(
            {
                "author": author,
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


def search_issue_count(query: str, token: str | None) -> int:
    encoded_query = urllib.parse.quote_plus(query)
    url = f"{API_BASE}/search/issues?q={encoded_query}&per_page=1"
    payload, _ = request_json(url, token)
    if not isinstance(payload, dict):
        return 0
    return int(payload.get("total_count", 0) or 0)


def format_count(value: int) -> str:
    return f"{value:,}"


def collect_profile_stats(username: str, token: str | None) -> dict[str, int]:
    repositories = list_repositories(username, token)
    username_lower = username.casefold()
    total_stars = 0

    for repository in repositories:
        owner = repository.get("owner")
        if not isinstance(owner, dict):
            continue

        owner_login = owner.get("login")
        if not isinstance(owner_login, str) or owner_login.casefold() != username_lower:
            continue

        total_stars += int(repository.get("stargazers_count", 0) or 0)

    seen_shas: set[str] = set()
    contributed_to: set[str] = set()

    for repository in repositories:
        if repository.get("archived") is True:
            continue

        owner = repository.get("owner")
        if not isinstance(owner, dict):
            continue

        owner_login = owner.get("login")
        repo_name = repository.get("name")
        if not isinstance(owner_login, str) or not isinstance(repo_name, str):
            continue

        for commit in list_commits(owner_login, repo_name, username, token):
            sha = commit.get("sha")
            if not isinstance(sha, str) or sha in seen_shas:
                continue

            seen_shas.add(sha)
            contributed_to.add(f"{owner_login}/{repo_name}")

    return {
        "total_stars": total_stars,
        "total_commits": len(seen_shas),
        "total_prs": search_issue_count(f"author:{username} is:pr", token),
        "total_issues": search_issue_count(f"author:{username} is:issue", token),
        "contributed_to": len(contributed_to),
    }


def render_stats_card(stats: dict[str, int], *, theme: str = "light") -> str:
    palette = THEMES[theme]
    rows = [
        ("Total Stars", format_count(int(stats["total_stars"]))),
        ("Total Commits", format_count(int(stats["total_commits"]))),
        ("Total PRs", format_count(int(stats["total_prs"]))),
        ("Total Issues", format_count(int(stats["total_issues"]))),
        ("Contributed to", format_count(int(stats["contributed_to"]))),
    ]

    row_markup: list[str] = []
    y = 94
    for label, value in rows:
        row_markup.append(
            f'  <circle cx="31" cy="{y - 5}" r="4" fill="{palette["accent"]}"/>\n'
            f'  <text x="44" y="{y}" style="fill: {palette["text"]}; font-size: 14px;">{label}</text>\n'
            f'  <text x="306" y="{y}" text-anchor="end" style="fill: {palette["value"]}; font-size: 14px; font-weight: 700;">{value}</text>'
        )
        y += 24

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{CARD_WIDTH}" height="{CARD_HEIGHT}" viewBox="0 0 {CARD_WIDTH} {CARD_HEIGHT}" role="img" aria-label="GitHub profile stats">
  <style>* {{
          font-family: 'Segoe UI', Ubuntu, "Helvetica Neue", Sans-Serif
        }}</style>
  <rect x="1" y="1" rx="10" ry="10" height="{CARD_HEIGHT - 2}" width="{CARD_WIDTH - 2}" stroke="{palette["border"]}" stroke-width="1" fill="{palette["background"]}" stroke-opacity="1"></rect>
  <text x="24" y="38" style="font-size: 22px; fill: {palette["title"]}; font-weight: 700;">Stats</text>
  <text x="24" y="58" style="font-size: 12px; fill: {palette["text"]};">Includes private repos available to the token</text>
  <line x1="24" y1="72" x2="316" y2="72" stroke="{palette["divider"]}" stroke-width="1"/>
{chr(10).join(row_markup)}
</svg>
"""


def write_stats_cards(output_dir: Path, stats: dict[str, int]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "stats.svg").write_text(render_stats_card(stats, theme="light"), encoding="utf-8")
    (output_dir / "stats-dark.svg").write_text(render_stats_card(stats, theme="dark"), encoding="utf-8")


def main() -> int:
    username = os.environ.get("GITHUB_USER") or os.environ.get("GITHUB_REPOSITORY_OWNER")
    token = os.environ.get("GITHUB_TOKEN") or None
    output_dir = Path(os.environ.get("OUTPUT_DIR", "profile"))

    if not username:
        print("GITHUB_USER or GITHUB_REPOSITORY_OWNER is required.", file=sys.stderr)
        return 1

    stats = collect_profile_stats(username, token)
    write_stats_cards(output_dir, stats)
    print(json.dumps(stats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
