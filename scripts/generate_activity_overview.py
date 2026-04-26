from __future__ import annotations

import datetime as dt
import html
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


API_BASE = "https://api.github.com"
USER_AGENT = "lReDragol-profile-widgets"
CARD_WIDTH = 960
CARD_HEIGHT = 320


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


def parse_datetime(value: str | None) -> dt.datetime | None:
    if not isinstance(value, str):
        return None

    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_commit_date(commit: dict[str, object]) -> dt.datetime | None:
    commit_info = commit.get("commit")
    if not isinstance(commit_info, dict):
        return None

    author_info = commit_info.get("author")
    if not isinstance(author_info, dict):
        return None

    return parse_datetime(author_info.get("date"))


def format_count(value: int) -> str:
    return f"{value:,}"


def date_labels_for_range(start_date: dt.date, days: int) -> list[str]:
    return [(start_date + dt.timedelta(days=index)).strftime("%d.%m") for index in range(days)]


def joined_text(created_at: dt.datetime, now: dt.datetime, label: str = "GitHub") -> str:
    now_date = now.date()
    created_date = created_at.date()
    years = now_date.year - created_date.year - ((now_date.month, now_date.day) < (created_date.month, created_date.day))
    if years >= 1:
        suffix = "year" if years == 1 else "years"
        return f"Joined {label} {years} {suffix} ago"

    months = (now_date.year - created_date.year) * 12 + now_date.month - created_date.month
    if now_date.day < created_date.day:
        months -= 1
    if months >= 1:
        suffix = "month" if months == 1 else "months"
        return f"Joined {label} {months} {suffix} ago"

    days = max((now_date - created_date).days, 0)
    suffix = "day" if days == 1 else "days"
    return f"Joined {label} {days} {suffix} ago"


def repo_recent_enough(repository: dict[str, object], cutoff: dt.datetime) -> bool:
    pushed_at = parse_datetime(repository.get("pushed_at"))
    return bool(pushed_at and pushed_at >= cutoff)


def owned_repo_counts(repositories: list[dict[str, object]], username: str) -> tuple[int, int]:
    public_count = 0
    private_count = 0
    username_lower = username.casefold()

    for repository in repositories:
        owner = repository.get("owner")
        if not isinstance(owner, dict):
            continue

        owner_login = owner.get("login")
        if not isinstance(owner_login, str) or owner_login.casefold() != username_lower:
            continue

        if repository.get("private") is True:
            private_count += 1
        else:
            public_count += 1

    return public_count, private_count


def collect_activity_overview(
    username: str,
    token: str | None,
    *,
    now: dt.datetime | None = None,
    days: int = 14,
    utc_offset_hours: int = 3,
) -> dict[str, object]:
    if days <= 0:
        raise ValueError("days must be positive")

    now_utc = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    local_tz = dt.timezone(dt.timedelta(hours=utc_offset_hours))
    now_local = now_utc.astimezone(local_tz)
    end_date = now_local.date()
    start_date = end_date - dt.timedelta(days=days - 1)
    since_local = dt.datetime.combine(start_date, dt.time.min, tzinfo=local_tz)
    since_utc = since_local.astimezone(dt.timezone.utc)

    profile_url = f"{API_BASE}/users/{username}"
    profile_payload, _ = request_json(profile_url, token)
    if not isinstance(profile_payload, dict):
        raise RuntimeError(f"Unexpected profile payload for {username!r}")

    repositories = list_repositories(username, token)
    public_repo_count, private_repo_count = owned_repo_counts(repositories, username)
    commit_counts = [0] * days
    seen_shas: set[str] = set()

    for repository in repositories:
        if repository.get("archived") is True or not repo_recent_enough(repository, since_utc):
            continue

        owner = repository.get("owner")
        if not isinstance(owner, dict):
            continue

        owner_login = owner.get("login")
        repo_name = repository.get("name")
        if not isinstance(owner_login, str) or not isinstance(repo_name, str):
            continue

        for commit in list_commits(owner_login, repo_name, username, since_utc, token):
            sha = commit.get("sha")
            if not isinstance(sha, str) or sha in seen_shas:
                continue

            commit_date = parse_commit_date(commit)
            if commit_date is None:
                continue

            commit_local_date = commit_date.astimezone(local_tz).date()
            if commit_local_date < start_date or commit_local_date > end_date:
                continue

            seen_shas.add(sha)
            bucket = (commit_local_date - start_date).days
            commit_counts[bucket] += 1

    login = profile_payload.get("login")
    name = profile_payload.get("name")
    created_at = parse_datetime(profile_payload.get("created_at"))
    title = str(login) if isinstance(login, str) else username
    if isinstance(name, str) and name.strip() and name.strip() != title:
        title = f"{title} ({name.strip()})"

    return {
        "title": title,
        "public_repo_count": public_repo_count,
        "private_repo_count": private_repo_count,
        "joined_text": joined_text(created_at or now_utc, now_local, "GitHub"),
        "daily_commit_counts": commit_counts,
        "date_labels": date_labels_for_range(start_date, days),
        "days": days,
    }


def graph_geometry(
    daily_commit_counts: list[int],
) -> tuple[list[tuple[float, float, float, float, int]], list[tuple[int, float]], int, float, float, float, float, float]:
    graph_left = 420.0
    graph_top = 102.0
    graph_width = 492.0
    graph_height = 140.0
    max_count = max(max(daily_commit_counts, default=0), 1)
    step = graph_width / max(len(daily_commit_counts), 1)
    bar_width = min(8.0, step * 0.28)
    baseline = graph_top + graph_height

    bars: list[tuple[float, float, float, float, int]] = []
    for index, count in enumerate(daily_commit_counts):
        center_x = graph_left + step * index + step / 2
        bar_height = (count / max_count) * (graph_height - 10) if count else 0.0
        y = baseline - bar_height
        bars.append((center_x - bar_width / 2, y, bar_width, bar_height, count))

    raw_tick_values = sorted({round(max_count * fraction / 3) for fraction in range(4)})
    if raw_tick_values[-1] != max_count:
        raw_tick_values.append(max_count)
    tick_values = sorted(set(raw_tick_values))
    tick_rows = [
        (
            value,
            baseline - (value / max_count) * (graph_height - 10) if value else baseline,
        )
        for value in tick_values
    ]

    return bars, tick_rows, max_count, graph_left, graph_top, graph_width, graph_height, baseline


def render_activity_card(overview: dict[str, object]) -> str:
    title = html.escape(str(overview["title"]))
    public_repo_count = int(overview["public_repo_count"])
    private_repo_count = int(overview["private_repo_count"])
    joined = html.escape(str(overview["joined_text"]))
    daily_commit_counts = [int(value) for value in overview["daily_commit_counts"]]
    date_labels = [html.escape(str(value)) for value in overview["date_labels"]]
    days = int(overview["days"])
    total_commits = sum(daily_commit_counts)
    bars, y_ticks, max_count, graph_left, graph_top, graph_width, graph_height, baseline = graph_geometry(daily_commit_counts)
    step = graph_width / max(len(daily_commit_counts), 1)

    grid_lines = "\n".join(
        f'  <line x1="{graph_left:.1f}" y1="{y:.1f}" x2="{graph_left + graph_width:.1f}" y2="{y:.1f}" stroke="#21262d" stroke-width="1"/>\n'
        f'  <text x="{graph_left - 12:.1f}" y="{y + 4:.1f}" fill="#6e7681" font-family="Segoe UI, DejaVu Sans, Arial, sans-serif" font-size="11" text-anchor="end">{value}</text>'
        for value, y in y_ticks
    )
    bar_shapes = "\n".join(
        (
            f'  <rect x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{max(height, 2.0):.1f}" rx="4" fill="url(#barGradient)" opacity="0.95"/>'
            if count
            else f'  <rect x="{x:.1f}" y="{baseline - 2:.1f}" width="{width:.1f}" height="2.0" rx="1" fill="#2d333b"/>'
        )
        for x, y, width, height, count in bars
    )
    count_labels = "\n".join(
        f'  <text x="{x + width / 2:.1f}" y="{graph_top - 12:.1f}" fill="{"#f0f6fc" if count else "#6e7681"}" font-family="Segoe UI, DejaVu Sans, Arial, sans-serif" font-size="11" font-weight="700" text-anchor="middle">{count}</text>'
        for x, _y, width, _height, count in bars
    )
    date_markup = "\n".join(
        f'  <text x="{graph_left + step * index + step / 2:.1f}" y="{baseline + 28:.1f}" fill="{"#f0f6fc" if index == len(date_labels) - 1 else "#8b949e"}" font-family="Segoe UI, DejaVu Sans, Arial, sans-serif" font-size="10.5" text-anchor="middle">{label}</text>'
        for index, label in enumerate(date_labels)
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{CARD_WIDTH}" height="{CARD_HEIGHT}" viewBox="0 0 {CARD_WIDTH} {CARD_HEIGHT}" role="img" aria-label="{html.escape(str(overview['title']))}: {total_commits} commits in the last {days} days">
  <defs>
    <linearGradient id="cardBg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0d1117"/>
      <stop offset="100%" stop-color="#111926"/>
    </linearGradient>
    <linearGradient id="barGradient" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#3fb950"/>
      <stop offset="100%" stop-color="#238636"/>
    </linearGradient>
  </defs>

  <rect width="{CARD_WIDTH}" height="{CARD_HEIGHT}" rx="24" fill="url(#cardBg)"/>
  <rect x="1" y="1" width="{CARD_WIDTH - 2}" height="{CARD_HEIGHT - 2}" rx="23" fill="none" stroke="#30363d"/>

  <text x="40" y="56" fill="#f0f6fc" font-family="Segoe UI, DejaVu Sans, Arial, sans-serif" font-size="28" font-weight="700">{title}</text>
  <text x="40" y="92" fill="#8b949e" font-family="Segoe UI, DejaVu Sans, Arial, sans-serif" font-size="16">{joined}</text>

  <text x="40" y="136" fill="#8b949e" font-family="Segoe UI, DejaVu Sans, Arial, sans-serif" font-size="14" font-weight="700" letter-spacing="0.08em">REPOSITORIES</text>
  <text x="40" y="176" fill="#f0f6fc" font-family="Segoe UI, DejaVu Sans, Arial, sans-serif" font-size="34" font-weight="700">{format_count(public_repo_count)}</text>
  <text x="40" y="202" fill="#8b949e" font-family="Segoe UI, DejaVu Sans, Arial, sans-serif" font-size="16">Public Repos</text>

  <text x="206" y="176" fill="#f0f6fc" font-family="Segoe UI, DejaVu Sans, Arial, sans-serif" font-size="34" font-weight="700">{format_count(private_repo_count)}</text>
  <text x="206" y="202" fill="#8b949e" font-family="Segoe UI, DejaVu Sans, Arial, sans-serif" font-size="16">Private Repos</text>

  <text x="40" y="246" fill="#8b949e" font-family="Segoe UI, DejaVu Sans, Arial, sans-serif" font-size="14" font-weight="700" letter-spacing="0.08em">DAILY COMMITS</text>
  <text x="40" y="286" fill="#3fb950" font-family="Segoe UI, DejaVu Sans, Arial, sans-serif" font-size="30" font-weight="700">{format_count(total_commits)}</text>
  <text x="104" y="286" fill="#8b949e" font-family="Segoe UI, DejaVu Sans, Arial, sans-serif" font-size="16">total in the last {days} days</text>

  <text x="{graph_left:.1f}" y="56" fill="#f0f6fc" font-family="Segoe UI, DejaVu Sans, Arial, sans-serif" font-size="20" font-weight="700">Daily Commits ({days}d)</text>
  <text x="{graph_left + graph_width:.1f}" y="56" fill="#8b949e" font-family="Segoe UI, DejaVu Sans, Arial, sans-serif" font-size="14" text-anchor="end">Total: {format_count(total_commits)} | Peak: {format_count(max_count)}</text>
  <text x="{graph_left:.1f}" y="76" fill="#6e7681" font-family="Segoe UI, DejaVu Sans, Arial, sans-serif" font-size="12">Exact daily counts above each bar</text>

{grid_lines}
{count_labels}
{bar_shapes}
{date_markup}
</svg>
"""


def write_activity_card(output_dir: Path, overview: dict[str, object]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "activity-dark.svg"
    output_path.write_text(render_activity_card(overview), encoding="utf-8")
    return output_path


def main() -> int:
    username = os.environ.get("GITHUB_USER") or os.environ.get("GITHUB_REPOSITORY_OWNER")
    token = os.environ.get("GITHUB_TOKEN") or None
    output_dir = Path(os.environ.get("OUTPUT_DIR", "profile"))
    utc_offset_hours = int(os.environ.get("UTC_OFFSET", "3"))
    days = int(os.environ.get("ACTIVITY_DAYS", "14"))

    if not username:
        print("GITHUB_USER or GITHUB_REPOSITORY_OWNER is required.", file=sys.stderr)
        return 1

    overview = collect_activity_overview(
        username,
        token,
        days=days,
        utc_offset_hours=utc_offset_hours,
    )
    write_activity_card(output_dir, overview)
    print(json.dumps(overview))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
