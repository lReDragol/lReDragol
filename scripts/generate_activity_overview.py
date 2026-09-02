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
SCHEMA_VERSION = 1
CARD_WIDTH = 960
CARD_HEIGHT = 330
DEFAULT_HISTORY_DAYS = 365
DEFAULT_REFRESH_DAYS = 35


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


def list_repositories_from_url(
    base_url: str,
    query_params: dict[str, object],
    token: str | None,
) -> list[dict[str, object]]:
    repositories: list[dict[str, object]] = []
    page = 1

    while True:
        query = urllib.parse.urlencode({**query_params, "per_page": 100, "page": page})
        payload, _ = request_json(f"{base_url}?{query}", token)
        if not isinstance(payload, list) or not payload:
            break

        repositories.extend(repository for repository in payload if isinstance(repository, dict))
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
        {"type": "owner", "sort": "updated"},
        token,
    )


def list_commits(
    owner: str,
    repo: str,
    author: str,
    since: dt.datetime,
    token: str | None,
) -> list[dict[str, object]]:
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
        try:
            payload, _ = request_json(f"{API_BASE}/repos/{owner}/{repo}/commits?{query}", token)
        except urllib.error.HTTPError as error:
            if error.code in {403, 404, 409, 422}:
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
    try:
        payload, _ = request_json(f"{API_BASE}/repos/{owner}/{repo}/commits/{sha}", token)
    except urllib.error.HTTPError as error:
        if error.code in {403, 404, 409, 422}:
            return 0, 0
        raise

    if not isinstance(payload, dict) or not isinstance(payload.get("stats"), dict):
        return 0, 0

    stats = payload["stats"]
    return int(stats.get("additions", 0) or 0), int(stats.get("deletions", 0) or 0)


def parse_datetime(value: object) -> dt.datetime | None:
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


def repo_recent_enough(repository: dict[str, object], cutoff: dt.datetime) -> bool:
    pushed_at = parse_datetime(repository.get("pushed_at"))
    return bool(pushed_at and pushed_at >= cutoff)


def repository_full_name(repository: dict[str, object]) -> str | None:
    full_name = repository.get("full_name")
    if isinstance(full_name, str):
        return full_name

    owner = repository.get("owner")
    name = repository.get("name")
    if isinstance(owner, dict) and isinstance(owner.get("login"), str) and isinstance(name, str):
        return f"{owner['login']}/{name}"
    return None


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


def joined_text(created_at: dt.datetime, now: dt.datetime, label: str = "GitHub") -> str:
    now_date = now.date()
    created_date = created_at.date()
    years = now_date.year - created_date.year - ((now_date.month, now_date.day) < (created_date.month, created_date.day))
    if years >= 1:
        return f"Joined {label} {years} {'year' if years == 1 else 'years'} ago"

    months = (now_date.year - created_date.year) * 12 + now_date.month - created_date.month
    if now_date.day < created_date.day:
        months -= 1
    if months >= 1:
        return f"Joined {label} {months} {'month' if months == 1 else 'months'} ago"

    elapsed_days = max((now_date - created_date).days, 0)
    return f"Joined {label} {elapsed_days} {'day' if elapsed_days == 1 else 'days'} ago"


def empty_day(value: dt.date) -> dict[str, object]:
    return {
        "date": value.isoformat(),
        "commits": 0,
        "additions": 0,
        "deletions": 0,
        "changed": 0,
        "merges": 0,
    }


def normalized_cached_day(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict) or not isinstance(value.get("date"), str):
        return None
    try:
        dt.date.fromisoformat(value["date"])
        commits = max(int(value.get("commits", 0) or 0), 0)
        additions = max(int(value.get("additions", 0) or 0), 0)
        deletions = max(int(value.get("deletions", 0) or 0), 0)
        merges = max(int(value.get("merges", 0) or 0), 0)
    except (TypeError, ValueError):
        return None
    return {
        "date": value["date"],
        "commits": commits,
        "additions": additions,
        "deletions": deletions,
        "changed": additions + deletions,
        "merges": merges,
    }


def load_activity_data(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) and payload.get("schema_version") == SCHEMA_VERSION else None


def collect_activity_data(
    username: str,
    token: str | None,
    *,
    now: dt.datetime | None = None,
    days: int = DEFAULT_HISTORY_DAYS,
    refresh_days: int | None = None,
    utc_offset_hours: int = 3,
    cached_data: dict[str, object] | None = None,
    excluded_repositories: set[str] | None = None,
) -> dict[str, object]:
    if days <= 0:
        raise ValueError("days must be positive")
    if refresh_days is not None and refresh_days <= 0:
        raise ValueError("refresh_days must be positive")

    now_utc = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    local_tz = dt.timezone(dt.timedelta(hours=utc_offset_hours))
    now_local = now_utc.astimezone(local_tz)
    end_date = now_local.date()
    start_date = end_date - dt.timedelta(days=days - 1)
    refresh_span = min(refresh_days or days, days)
    refresh_start = end_date - dt.timedelta(days=refresh_span - 1)
    since_local = dt.datetime.combine(refresh_start, dt.time.min, tzinfo=local_tz)
    since_utc = since_local.astimezone(dt.timezone.utc)

    profile_payload, _ = request_json(f"{API_BASE}/users/{username}", token)
    if not isinstance(profile_payload, dict):
        raise RuntimeError(f"Unexpected profile payload for {username!r}")

    repositories = list_repositories(username, token)
    public_repo_count, private_repo_count = owned_repo_counts(repositories, username)
    days_by_date = {
        (start_date + dt.timedelta(days=index)).isoformat(): empty_day(start_date + dt.timedelta(days=index))
        for index in range(days)
    }

    if cached_data and isinstance(cached_data.get("days"), list):
        for raw_day in cached_data["days"]:
            cached_day = normalized_cached_day(raw_day)
            if cached_day is None:
                continue
            cached_date = dt.date.fromisoformat(str(cached_day["date"]))
            if start_date <= cached_date < refresh_start:
                days_by_date[str(cached_day["date"])] = cached_day

    excluded = {name.casefold() for name in (excluded_repositories or set())}
    seen_shas: set[str] = set()

    for repository in repositories:
        full_name = repository_full_name(repository)
        if (
            repository.get("archived") is True
            or full_name is None
            or full_name.casefold() in excluded
            or not repo_recent_enough(repository, since_utc)
        ):
            continue

        owner = repository.get("owner")
        repo_name = repository.get("name")
        if not isinstance(owner, dict) or not isinstance(owner.get("login"), str) or not isinstance(repo_name, str):
            continue
        owner_login = owner["login"]

        # Without an explicit `sha`, GitHub's commits endpoint walks the repository default branch.
        for commit in list_commits(owner_login, repo_name, username, since_utc, token):
            sha = commit.get("sha")
            if not isinstance(sha, str) or sha in seen_shas:
                continue

            commit_date = parse_commit_date(commit)
            if commit_date is None:
                continue
            local_date = commit_date.astimezone(local_tz).date()
            if local_date < refresh_start or local_date > end_date:
                continue

            seen_shas.add(sha)
            additions, deletions = commit_stats(owner_login, repo_name, sha, token)
            day = days_by_date[local_date.isoformat()]
            day["commits"] = int(day["commits"]) + 1
            day["additions"] = int(day["additions"]) + additions
            day["deletions"] = int(day["deletions"]) + deletions
            day["changed"] = int(day["additions"]) + int(day["deletions"])
            parents = commit.get("parents")
            if isinstance(parents, list) and len(parents) > 1:
                day["merges"] = int(day["merges"]) + 1

    login = profile_payload.get("login")
    name = profile_payload.get("name")
    title = str(login) if isinstance(login, str) else username
    if isinstance(name, str) and name.strip() and name.strip() != title:
        title = f"{title} ({name.strip()})"
    created_at = parse_datetime(profile_payload.get("created_at")) or now_utc

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_utc.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "username": username,
        "title": title,
        "joined_text": joined_text(created_at, now_local, "GitHub"),
        "timezone": f"UTC{utc_offset_hours:+03d}:00",
        "period": {"start": start_date.isoformat(), "end": end_date.isoformat(), "days": days},
        "scope": {
            "commits": "Authored commits reachable from repository default branches",
            "lines": "Raw Git diff additions and deletions, including generated files and merges",
            "privacy": "Daily aggregate only; repository names, commit IDs, messages, paths, and code are omitted",
        },
        "repository_counts": {"public": public_repo_count, "private": private_repo_count},
        "days": [days_by_date[key] for key in sorted(days_by_date)],
    }


def summarize_days(data: dict[str, object], period_days: int | None = None) -> dict[str, int]:
    raw_days = data.get("days")
    normalized = [day for raw in raw_days if (day := normalized_cached_day(raw))] if isinstance(raw_days, list) else []
    selected = normalized[-period_days:] if period_days else normalized
    return {
        key: sum(int(day[key]) for day in selected)
        for key in ("commits", "additions", "deletions", "changed", "merges")
    }


def format_count(value: int) -> str:
    return f"{value:,}"


def heat_level(value: int, maximum: int) -> int:
    if value <= 0 or maximum <= 0:
        return 0
    ratio = value / maximum
    if ratio <= 0.15:
        return 1
    if ratio <= 0.35:
        return 2
    if ratio <= 0.65:
        return 3
    return 4


def render_activity_card(data: dict[str, object]) -> str:
    raw_days = data.get("days")
    daily = [day for raw in raw_days if (day := normalized_cached_day(raw))] if isinstance(raw_days, list) else []
    if not daily:
        raise ValueError("activity data has no valid days")

    totals_30d = summarize_days(data, 30)
    totals_all = summarize_days(data)
    repo_counts = data.get("repository_counts") if isinstance(data.get("repository_counts"), dict) else {}
    title = html.escape(str(data.get("title", data.get("username", "GitHub activity"))))
    joined = html.escape(str(data.get("joined_text", "")))
    start_date = dt.date.fromisoformat(str(daily[0]["date"]))
    grid_start = start_date - dt.timedelta(days=(start_date.weekday() + 1) % 7)
    cell = 10
    gap = 3
    step = cell + gap
    grid_left = 76
    grid_top = 122
    max_commits = max((int(day["commits"]) for day in daily), default=0)
    colors = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]

    cells: list[str] = []
    month_labels: list[str] = []
    last_month: tuple[int, int] | None = None
    for day in daily:
        date_value = dt.date.fromisoformat(str(day["date"]))
        delta = (date_value - grid_start).days
        week = delta // 7
        weekday = delta % 7
        x = grid_left + week * step
        y = grid_top + weekday * step
        commits = int(day["commits"])
        additions = int(day["additions"])
        deletions = int(day["deletions"])
        level = heat_level(commits, max_commits)
        tooltip = html.escape(
            f"{date_value.isoformat()}: {commits} commits, +{additions} / -{deletions} lines",
            quote=True,
        )
        cells.append(
            f'  <rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{colors[level]}"><title>{tooltip}</title></rect>'
        )
        month_key = (date_value.year, date_value.month)
        if month_key != last_month and date_value.day <= 7:
            month_labels.append(
                f'  <text x="{x}" y="{grid_top - 12}" class="muted month">{html.escape(date_value.strftime("%b"))}</text>'
            )
            last_month = month_key

    legend = "".join(
        f'<rect x="{807 + index * 16}" y="294" width="10" height="10" rx="2" fill="{color}"/>'
        for index, color in enumerate(colors)
    )
    period = data.get("period") if isinstance(data.get("period"), dict) else {}
    period_days = int(period.get("days", len(daily)) or len(daily))

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{CARD_WIDTH}" height="{CARD_HEIGHT}" viewBox="0 0 {CARD_WIDTH} {CARD_HEIGHT}" role="img" aria-label="{title}: {totals_all['commits']} authored commits in {period_days} days">
  <style>
    .text {{ font-family: "Segoe UI", "DejaVu Sans", Arial, sans-serif; fill: #f0f6fc; }}
    .muted {{ font-family: "Segoe UI", "DejaVu Sans", Arial, sans-serif; fill: #8b949e; }}
    .month {{ font-size: 11px; }}
  </style>
  <defs>
    <linearGradient id="cardBg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0d1117"/>
      <stop offset="100%" stop-color="#111926"/>
    </linearGradient>
  </defs>
  <rect width="{CARD_WIDTH}" height="{CARD_HEIGHT}" rx="24" fill="url(#cardBg)"/>
  <rect x="1" y="1" width="958" height="328" rx="23" fill="none" stroke="#30363d"/>

  <text x="34" y="44" class="text" font-size="25" font-weight="700">Activity Overview</text>
  <text x="926" y="42" class="muted" font-size="13" text-anchor="end">{title} | {joined}</text>
  <text x="34" y="76" class="text" font-size="18" font-weight="700">{format_count(totals_30d['commits'])}</text>
  <text x="88" y="76" class="muted" font-size="13">commits / 30d</text>
  <text x="224" y="76" style="fill:#3fb950" class="text" font-size="18" font-weight="700">+{format_count(totals_30d['additions'])}</text>
  <text x="354" y="76" style="fill:#f85149" class="text" font-size="18" font-weight="700">-{format_count(totals_30d['deletions'])}</text>
  <text x="487" y="76" class="muted" font-size="13">raw diff lines / 30d</text>
  <text x="926" y="76" class="muted" font-size="13" text-anchor="end">{int(repo_counts.get('public', 0))} public + {int(repo_counts.get('private', 0))} private repos</text>

{chr(10).join(month_labels)}
  <text x="34" y="148" class="muted" font-size="11">Mon</text>
  <text x="34" y="174" class="muted" font-size="11">Wed</text>
  <text x="34" y="200" class="muted" font-size="11">Fri</text>
{chr(10).join(cells)}

  <text x="34" y="302" class="muted" font-size="12">Click for interactive daily commits and raw diff details</text>
  <text x="772" y="303" class="muted" font-size="11">Less</text>
  {legend}
  <text x="895" y="303" class="muted" font-size="11">More</text>
</svg>
"""


def write_activity_outputs(output_dir: Path, data: dict[str, object]) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    data_path = output_dir / "activity-data.json"
    svg_path = output_dir / "activity-dark.svg"
    data_path.write_text(json.dumps(data, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    svg_path.write_text(render_activity_card(data), encoding="utf-8")
    return data_path, svg_path


def main() -> int:
    username = os.environ.get("GITHUB_USER") or os.environ.get("GITHUB_REPOSITORY_OWNER")
    token = os.environ.get("GITHUB_TOKEN") or None
    output_dir = Path(os.environ.get("OUTPUT_DIR", "profile"))
    utc_offset_hours = int(os.environ.get("UTC_OFFSET", "3"))
    days = int(os.environ.get("ACTIVITY_DAYS", str(DEFAULT_HISTORY_DAYS)))
    data_path = output_dir / "activity-data.json"
    cached_data = load_activity_data(data_path)
    refresh_default = DEFAULT_REFRESH_DAYS if cached_data else days
    refresh_days = int(os.environ.get("ACTIVITY_REFRESH_DAYS", str(refresh_default)))
    excluded = {
        item.strip()
        for item in os.environ.get("EXCLUDE_REPOSITORY", f"{username}/{username}" if username else "").split(",")
        if item.strip()
    }

    if not username:
        print("GITHUB_USER or GITHUB_REPOSITORY_OWNER is required.", file=sys.stderr)
        return 1

    data = collect_activity_data(
        username,
        token,
        days=days,
        refresh_days=refresh_days,
        utc_offset_hours=utc_offset_hours,
        cached_data=cached_data,
        excluded_repositories=excluded,
    )
    write_activity_outputs(output_dir, data)
    print(
        json.dumps(
            {
                "generated_at": data["generated_at"],
                "period": data["period"],
                "repository_counts": data["repository_counts"],
                "totals": summarize_days(data),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
