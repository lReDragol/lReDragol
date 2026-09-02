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
CARD_WIDTH = 420
CARD_HEIGHT = 200

LANGUAGE_COLORS = {
    "C": "#555555",
    "C#": "#178600",
    "C++": "#f34b7d",
    "CSS": "#563d7c",
    "Cuda": "#3a4e3a",
    "Go": "#00ADD8",
    "HTML": "#e34c26",
    "Inno Setup": "#264b99",
    "Java": "#b07219",
    "JavaScript": "#f1e05a",
    "Lua": "#000080",
    "PowerShell": "#012456",
    "Python": "#3572A5",
    "Rust": "#dea584",
    "Shell": "#89e051",
    "TypeScript": "#3178c6",
}

THEMES = {
    "light": {
        "background": "#ffffff",
        "border": "#d0d7de",
        "title": "#24292f",
        "text": "#57606a",
        "track": "#eaeef2",
    },
    "dark": {
        "background": "#0d1117",
        "border": "#30363d",
        "title": "#f0f6fc",
        "text": "#8b949e",
        "track": "#21262d",
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
        return payload, {key.lower(): value for key, value in response.headers.items()}


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
        repositories.extend(item for item in payload if isinstance(item, dict))
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


def repository_languages(owner: str, name: str, token: str | None) -> dict[str, int]:
    owner_path = urllib.parse.quote(owner, safe="")
    name_path = urllib.parse.quote(name, safe="")
    try:
        payload, _ = request_json(f"{API_BASE}/repos/{owner_path}/{name_path}/languages", token)
    except urllib.error.HTTPError as error:
        if error.code in {403, 404, 409}:
            return {}
        raise
    if not isinstance(payload, dict):
        return {}
    result: dict[str, int] = {}
    for language, raw_bytes in payload.items():
        if not isinstance(language, str):
            continue
        try:
            result[language] = max(int(raw_bytes or 0), 0)
        except (TypeError, ValueError):
            continue
    return result


def collect_top_languages(
    username: str,
    token: str | None,
    *,
    excluded_languages: set[str] | None = None,
    now: dt.datetime | None = None,
) -> dict[str, object]:
    excluded = {language.casefold() for language in (excluded_languages or set())}
    username_lower = username.casefold()
    aggregate: dict[str, int] = {}
    repository_count = 0

    for repository in list_repositories(username, token):
        owner = repository.get("owner")
        owner_login = owner.get("login") if isinstance(owner, dict) else None
        name = repository.get("name")
        if (
            not isinstance(owner_login, str)
            or owner_login.casefold() != username_lower
            or not isinstance(name, str)
            or repository.get("fork") is True
        ):
            continue
        repository_count += 1
        for language, byte_count in repository_languages(owner_login, name, token).items():
            if language.casefold() in excluded:
                continue
            aggregate[language] = aggregate.get(language, 0) + byte_count

    total_bytes = sum(aggregate.values())
    languages = [
        {
            "name": language,
            "bytes": byte_count,
            "percent": round((byte_count / total_bytes) * 100, 2) if total_bytes else 0.0,
            "color": LANGUAGE_COLORS.get(language, "#8b949e"),
        }
        for language, byte_count in sorted(aggregate.items(), key=lambda item: (-item[1], item[0].casefold()))
    ]
    generated_at = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    return {
        "schema_version": 1,
        "generated_at": generated_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "username": username,
        "repository_count": repository_count,
        "total_bytes": total_bytes,
        "languages": languages,
    }


def render_top_languages(data: dict[str, object], *, theme: str) -> str:
    palette = THEMES[theme]
    raw_languages = data.get("languages")
    languages = raw_languages[:5] if isinstance(raw_languages, list) else []
    repository_count = int(data.get("repository_count", 0) or 0)
    total_bytes = int(data.get("total_bytes", 0) or 0)
    rows: list[str] = []

    for index, language in enumerate(languages):
        if not isinstance(language, dict):
            continue
        name = html.escape(str(language.get("name", "Unknown")))
        percent = max(float(language.get("percent", 0) or 0), 0.0)
        color = html.escape(str(language.get("color", "#8b949e")), quote=True)
        y = 76 + index * 24
        bar_width = 132 * min(percent / 100, 1.0)
        rows.append(
            f'  <circle cx="22" cy="{y - 4}" r="5" fill="{color}"/>\n'
            f'  <text x="34" y="{y}" class="name">{name}</text>\n'
            f'  <rect x="176" y="{y - 12}" width="132" height="8" rx="4" fill="{palette["track"]}"/>\n'
            f'  <rect x="176" y="{y - 12}" width="{bar_width:.2f}" height="8" rx="4" fill="{color}"/>\n'
            f'  <text x="398" y="{y}" class="percent" text-anchor="end">{percent:.2f}%</text>'
        )

    description = f"Top languages by code size across {repository_count} owned repositories"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{CARD_WIDTH}" height="{CARD_HEIGHT}" viewBox="0 0 {CARD_WIDTH} {CARD_HEIGHT}" role="img" aria-label="{html.escape(description, quote=True)}">
  <style>
    text {{ font-family: "Segoe UI", Arial, sans-serif; }}
    .title {{ fill: {palette['title']}; font-size: 18px; font-weight: 700; }}
    .subtitle, .percent {{ fill: {palette['text']}; font-size: 11px; }}
    .name {{ fill: {palette['title']}; font-size: 12px; font-weight: 600; }}
  </style>
  <rect x="1" y="1" width="418" height="198" rx="10" fill="{palette['background']}" stroke="{palette['border']}"/>
  <text x="20" y="29" class="title">Top Languages</text>
  <text x="20" y="49" class="subtitle">By code size | {repository_count} owned repos | {total_bytes:,} bytes</text>
{chr(10).join(rows)}
</svg>
"""


def write_outputs(output_dir: Path, data: dict[str, object]) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    data_path = output_dir / "languages-data.json"
    light_path = output_dir / "top-langs.svg"
    dark_path = output_dir / "top-langs-dark.svg"
    data_path.write_text(json.dumps(data, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    light_path.write_text(render_top_languages(data, theme="light"), encoding="utf-8")
    dark_path.write_text(render_top_languages(data, theme="dark"), encoding="utf-8")
    return data_path, light_path, dark_path


def main() -> int:
    username = os.environ.get("GITHUB_USER") or os.environ.get("GITHUB_REPOSITORY_OWNER")
    token = os.environ.get("GITHUB_TOKEN") or None
    output_dir = Path(os.environ.get("OUTPUT_DIR", "profile"))
    excluded = {
        item.strip()
        for item in os.environ.get("EXCLUDE_LANGUAGES", "Jupyter Notebook").split(",")
        if item.strip()
    }
    if not username:
        print("GITHUB_USER or GITHUB_REPOSITORY_OWNER is required.", file=sys.stderr)
        return 1
    data = collect_top_languages(username, token, excluded_languages=excluded)
    write_outputs(output_dir, data)
    print(
        json.dumps(
            {
                "generated_at": data["generated_at"],
                "repository_count": data["repository_count"],
                "total_bytes": data["total_bytes"],
                "languages": len(data["languages"]),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
