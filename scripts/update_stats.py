#!/usr/bin/env python3
"""Refresh the moonlit, text-only GitHub statistics in the profile README."""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

API_ROOT = "https://api.github.com"
API_VERSION = "2022-11-28"
ROOT_DIR = Path(__file__).resolve().parents[1]
README_PATH = ROOT_DIR / "README.md"
START_MARKER = "<!-- PROFILE-STATS:START -->"
END_MARKER = "<!-- PROFILE-STATS:END -->"
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")


class GitHubAPIError(RuntimeError):
    """Raised when GitHub returns an unusable API response."""


def validate_username(username: str) -> str:
    username = username.strip()
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("GITHUB_USERNAME must be a valid GitHub username.")
    return username


def request_json(url: str, token: str | None = None) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "moonlit-profile-readme-stats",
        "X-GitHub-Api-Version": API_VERSION,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=25) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = ""
        try:
            detail = str(json.loads(exc.read().decode("utf-8")).get("message", ""))
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
            pass
        raise GitHubAPIError(
            f"GitHub API returned HTTP {exc.code}. {detail}".strip()
        ) from exc
    except URLError as exc:
        raise GitHubAPIError(f"Could not reach GitHub API: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise GitHubAPIError("GitHub returned invalid JSON.") from exc


def fetch_public_profile(username: str) -> dict[str, Any]:
    """Fetch public profile metadata without exposing private repositories."""
    payload = request_json(f"{API_ROOT}/users/{quote(username, safe='')}")
    if not isinstance(payload, dict):
        raise GitHubAPIError("GitHub public profile response was not an object.")
    return payload


def fetch_authenticated_profile(username: str, token: str) -> dict[str, Any]:
    """Fetch the signed-in owner's profile so private-visibility counts are visible."""
    payload = request_json(f"{API_ROOT}/user", token=token)
    if not isinstance(payload, dict):
        raise GitHubAPIError("GitHub authenticated profile response was not an object.")
    actual_login = str(payload.get("login", ""))
    if actual_login.casefold() != username.casefold():
        raise GitHubAPIError(
            "GH_PROFILE_TOKEN belongs to a different GitHub account. "
            "Create the token while signed in as the profile owner."
        )
    return payload


def fetch_public_repositories(username: str) -> list[dict[str, Any]]:
    """List only publicly visible repositories; deliberately do not use the token."""
    repositories: list[dict[str, Any]] = []
    page = 1
    while True:
        query = urlencode(
            {
                "type": "owner",
                "sort": "updated",
                "direction": "desc",
                "per_page": 100,
                "page": page,
            }
        )
        payload = request_json(
            f"{API_ROOT}/users/{quote(username, safe='')}/repos?{query}"
        )
        if not isinstance(payload, list):
            raise GitHubAPIError("GitHub repository response was not a list.")
        repositories.extend(item for item in payload if isinstance(item, dict))
        if len(payload) < 100:
            return repositories
        page += 1


def safe_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return 0


def calculate_metrics(
    repositories: list[dict[str, Any]],
    followers: int | None = None,
    public_repositories: int | None = None,
) -> dict[str, int | None]:
    """Calculate public repository metrics; None means follower count is unavailable."""
    original_repositories = [
        repository for repository in repositories if repository.get("fork") is not True
    ]
    repo_count = (
        safe_int(public_repositories)
        if public_repositories is not None
        else len(repositories)
    )
    return {
        "public_repositories": repo_count,
        "stars_earned": sum(
            safe_int(repository.get("stargazers_count"))
            for repository in original_repositories
        ),
        "followers": safe_int(followers) if followers is not None else None,
        # Counts repositories this account forked, not forks made by other people.
        "forks_created": sum(
            1 for repository in repositories if repository.get("fork") is True
        ),
    }


def format_number(value: int | None) -> str:
    return "hidden" if value is None else f"{value:,}"


def render_stats_section(
    username: str,
    metrics: dict[str, int | None],
    updated_at: datetime | None = None,
) -> str:
    updated_at = updated_at or datetime.now(timezone.utc)
    date_label = updated_at.astimezone(timezone.utc).strftime("%d %b %Y · %H:%M UTC")
    return f"""{START_MARKER}
<div align="center">

<sub>☾ ✦ A LITTLE SPACE UNDER THE STARS ✦ ☽</sub>

### ✧ GITHUB AT A GLANCE ✧

<sub>@{username}</sub>

✧ 📦 **Public repositories** · **{format_number(metrics['public_repositories'])}**

✧ ⭐ **Stars earned** · **{format_number(metrics['stars_earned'])}**

✧ 👥 **Followers** · **{format_number(metrics['followers'])}**

✧ 🍴 **Forks created** · **{format_number(metrics['forks_created'])}**

<sub>little by little, one travels far. 🦋</sub>

<sub>updated {date_label}</sub>

</div>
{END_MARKER}"""


def replace_stats_section(readme_content: str, section: str) -> str:
    if readme_content.count(START_MARKER) != 1 or readme_content.count(END_MARKER) != 1:
        raise ValueError(
            "README.md must contain exactly one PROFILE-STATS START and END marker."
        )
    start = readme_content.index(START_MARKER)
    end_marker_start = readme_content.index(END_MARKER)
    if end_marker_start < start:
        raise ValueError("README statistics markers are in the wrong order.")
    end = end_marker_start + len(END_MARKER)
    return readme_content[:start] + section + readme_content[end:]


def write_readme(content: str, output_path: Path = README_PATH) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=output_path.parent,
            prefix=f"{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_file.write(content)
            temporary_path = Path(temporary_file.name)
        temporary_path.replace(output_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def main() -> int:
    try:
        username = validate_username(os.getenv("GITHUB_USERNAME", "sabirhusseinbalal"))
        token = os.getenv("GH_PROFILE_TOKEN", "").strip() or None

        public_profile = fetch_public_profile(username)
        repositories = fetch_public_repositories(username)

        followers: int | None = None
        if token:
            authenticated_profile = fetch_authenticated_profile(username, token)
            followers = safe_int(authenticated_profile.get("followers"))

        metrics = calculate_metrics(
            repositories,
            followers=followers,
            public_repositories=(
                public_profile.get("public_repos")
                if public_profile.get("public_repos") is not None
                else len(repositories)
            ),
        )
        current_readme = README_PATH.read_text(encoding="utf-8")
        updated_readme = replace_stats_section(
            current_readme,
            render_stats_section(username, metrics),
        )
        if updated_readme != current_readme:
            write_readme(updated_readme)
            print("Updated the written statistics in README.md.")
        else:
            print("The written statistics in README.md are already up to date.")

        for name, value in metrics.items():
            display_value = "hidden (add GH_PROFILE_TOKEN)" if value is None else value
            print(f"{name}: {display_value}")
        return 0
    except (GitHubAPIError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
