#!/usr/bin/env python3
"""Generate a public GitHub statistics SVG for a profile README.

Uses only the Python standard library. Public repository metrics are fetched
without authentication. An optional fine-grained PAT can be used to retrieve
the authenticated account's follower count when SHOW_FOLLOWERS=true.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

API_ROOT = "https://api.github.com"
API_VERSION = "2026-03-10"
ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT_DIR / "assets" / "profile-stats.svg"
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
PER_PAGE = 100


class GitHubAPIError(RuntimeError):
    """Raised when a GitHub API request fails or returns unexpected data."""


def validate_username(username: str) -> str:
    username = username.strip()
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError(
            "GITHUB_USERNAME must be a valid GitHub username "
            "(letters, numbers, and internal hyphens only)."
        )
    return username


def request_json(url: str, token: str | None = None) -> Any:
    """Fetch JSON from GitHub with clear errors and no token leakage."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "sabir-github-profile-stats/1.0",
        "X-GitHub-Api-Version": API_VERSION,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=25) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = ""
        try:
            payload = json.loads(exc.read().decode("utf-8"))
            detail = str(payload.get("message", ""))
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
            pass

        if exc.code == 401:
            hint = " Check that GH_STATS_TOKEN is valid and has not expired."
        elif exc.code == 403:
            hint = (
                " Check the token permissions and GitHub API rate limit. "
                "For follower data, use a fine-grained token with the account "
                "authenticated as the profile owner."
            )
        elif exc.code == 404:
            hint = " Check that GITHUB_USERNAME is correct and the account is public."
        else:
            hint = ""
        message = f"GitHub API returned HTTP {exc.code}. {detail}{hint}".strip()
        raise GitHubAPIError(message) from exc
    except URLError as exc:
        raise GitHubAPIError(f"Could not reach the GitHub API: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise GitHubAPIError("GitHub returned an invalid JSON response.") from exc


def get_authenticated_profile(token: str) -> dict[str, Any]:
    """Return the authenticated user's profile summary."""
    payload = request_json(f"{API_ROOT}/user", token=token)
    if not isinstance(payload, dict) or not isinstance(payload.get("login"), str):
        raise GitHubAPIError("GitHub's authenticated-user response was missing a login.")
    return payload


def fetch_public_repositories(username: str) -> list[dict[str, Any]]:
    """Fetch every public repository owned by username, including forks."""
    repositories: list[dict[str, Any]] = []
    page = 1
    encoded_username = quote(username, safe="")

    while True:
        query = urlencode(
            {
                "type": "owner",
                "sort": "updated",
                "direction": "desc",
                "per_page": PER_PAGE,
                "page": page,
            }
        )
        url = f"{API_ROOT}/users/{encoded_username}/repos?{query}"
        payload = request_json(url)
        if not isinstance(payload, list):
            raise GitHubAPIError("GitHub's repository response was not a list.")

        repositories.extend(item for item in payload if isinstance(item, dict))
        if len(payload) < PER_PAGE:
            break
        page += 1

    return repositories


def safe_nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return 0


def calculate_metrics(
    repositories: list[dict[str, Any]], followers: int | None = None
) -> dict[str, int | None]:
    """Calculate transparent public-repository totals.

    Stars and forks are summed only across original (non-forked) repositories,
    so stars on somebody else's upstream project are not attributed to the user.
    The public repository count includes forks because they are still public repos
    owned by this account.
    """
    original_repositories = [repo for repo in repositories if repo.get("fork") is not True]
    stars_earned = sum(safe_nonnegative_int(repo.get("stargazers_count")) for repo in original_repositories)
    forks_created = sum(safe_nonnegative_int(repo.get("forks_count")) for repo in original_repositories)

    return {
        "public_repositories": len(repositories),
        "stars_earned": stars_earned,
        "forks_created": forks_created,
        "followers": None if followers is None else safe_nonnegative_int(followers),
    }


def compact_number(value: int | None) -> str:
    if value is None:
        return "—"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}m".replace(".0m", "m")
    if value >= 10_000:
        return f"{value / 1_000:.0f}k"
    if value >= 1_000:
        return f"{value / 1_000:.1f}k".replace(".0k", "k")
    return f"{value:,}"


def render_svg(
    username: str,
    metrics: dict[str, int | None],
    updated_at: datetime | None = None,
    show_followers: bool = False,
) -> str:
    """Render a self-contained, accessible SVG card."""
    updated_at = updated_at or datetime.now(timezone.utc)
    date_label = updated_at.astimezone(timezone.utc).strftime("%Y-%m-%d UTC")

    cards: list[tuple[str, int | None, str]] = [
        ("PUBLIC REPOSITORIES", metrics.get("public_repositories"), "folders"),
        ("STARS EARNED", metrics.get("stars_earned"), "star"),
        ("FORKS CREATED", metrics.get("forks_created"), "fork"),
    ]
    if show_followers:
        cards.append(("FOLLOWERS", metrics.get("followers"), "users"))

    width = 900
    height = 284
    left = 28
    gap = 16
    card_y = 104
    card_h = 116
    card_w = (width - (left * 2) - (gap * (len(cards) - 1))) / len(cards)

    card_parts: list[str] = []
    for index, (label, value, icon) in enumerate(cards):
        x = left + index * (card_w + gap)
        display_value = compact_number(value)
        card_parts.append(
            f'''<g>
  <rect x="{x:.1f}" y="{card_y}" width="{card_w:.1f}" height="{card_h}" rx="16" fill="#17243a" stroke="#2c4263" stroke-width="1"/>
  <text x="{x + 20:.1f}" y="{card_y + 31}" class="label">{label}</text>
  <text x="{x + 20:.1f}" y="{card_y + 81}" class="value">{display_value}</text>
</g>'''
        )

    safe_username = _xml_escape(username)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
<title id="title">GitHub public statistics for {safe_username}</title>
<desc id="desc">Public repository count, stars earned on original public repositories, and forks created. Updated {date_label}.</desc>
<defs>
  <linearGradient id="background" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0%" stop-color="#101a2b"/>
    <stop offset="100%" stop-color="#182b47"/>
  </linearGradient>
  <linearGradient id="accent" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0%" stop-color="#8bb9ff"/>
    <stop offset="100%" stop-color="#b8a7ff"/>
  </linearGradient>
  <style>
    .heading {{ font: 700 20px 'Segoe UI', Arial, sans-serif; letter-spacing: 2px; fill: #edf4ff; }}
    .subheading {{ font: 400 12px 'Segoe UI', Arial, sans-serif; fill: #9fb2cf; }}
    .label {{ font: 700 11px 'Segoe UI', Arial, sans-serif; letter-spacing: 1.1px; fill: #9fb2cf; }}
    .value {{ font: 700 38px 'Segoe UI', Arial, sans-serif; fill: #f4f7ff; }}
    .footer {{ font: 400 10px 'Segoe UI', Arial, sans-serif; fill: #8398b6; letter-spacing: .4px; }}
  </style>
</defs>
<rect x="1" y="1" width="898" height="282" rx="22" fill="url(#background)" stroke="#30496e" stroke-width="2"/>
<circle cx="846" cy="46" r="23" fill="#243b5c" opacity=".9"/>
<circle cx="854" cy="38" r="19" fill="#182b47"/>
<text x="30" y="46" class="heading">GITHUB AT A GLANCE</text>
<text x="30" y="69" class="subheading">A public snapshot of {safe_username}'s original work</text>
<rect x="30" y="82" width="90" height="3" rx="2" fill="url(#accent)"/>
{''.join(card_parts)}
<text x="30" y="250" class="footer">PUBLIC REPOSITORY METRICS  •  UPDATED {date_label}</text>
<text x="870" y="250" text-anchor="end" class="footer">STARS &amp; FORKS EXCLUDE FORKED REPOSITORIES</text>
</svg>
'''


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def write_svg(content: str, output_path: Path = OUTPUT_PATH) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Validate the SVG before replacing the existing image.
    ET.fromstring(content)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="\n", dir=output_path.parent,
        prefix=f"{output_path.name}.", suffix=".tmp", delete=False
    ) as temporary:
        temporary.write(content)
        temporary_path = Path(temporary.name)
    temporary_path.replace(output_path)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def main() -> int:
    try:
        username = validate_username(os.getenv("GITHUB_USERNAME", "sabirhusseinbalal"))
        token = os.getenv("GH_STATS_TOKEN", "").strip() or None
        show_followers = env_bool("SHOW_FOLLOWERS", default=False)

        if show_followers and not token:
            raise ValueError(
                "SHOW_FOLLOWERS is true, but GH_STATS_TOKEN is empty. "
                "Add a fine-grained PAT as a GitHub Actions secret named GH_STATS_TOKEN, "
                "or set SHOW_FOLLOWERS=false."
            )

        followers: int | None = None
        if show_followers:
            # Only use the personal token when the user explicitly enables
            # follower display. The default public-statistics card needs no PAT.
            assert token is not None
            profile = get_authenticated_profile(token)
            authenticated_login = str(profile.get("login", ""))
            if authenticated_login.casefold() != username.casefold():
                raise GitHubAPIError(
                    "GH_STATS_TOKEN authenticated as "
                    f"'{authenticated_login}', but GITHUB_USERNAME is '{username}'. "
                    "Use a token created by the profile owner."
                )
            followers = safe_nonnegative_int(profile.get("followers"))

        repositories = fetch_public_repositories(username)
        metrics = calculate_metrics(repositories, followers=followers)
        svg = render_svg(username, metrics, show_followers=show_followers)
        write_svg(svg)

        print(f"Updated {OUTPUT_PATH.relative_to(ROOT_DIR)}")
        print(f"Public repositories: {metrics['public_repositories']}")
        print(f"Stars earned on original public repositories: {metrics['stars_earned']}")
        print(f"Forks created from original public repositories: {metrics['forks_created']}")
        if show_followers:
            print(f"Followers (display only): {metrics['followers']}")
        return 0
    except (GitHubAPIError, ValueError, OSError, ET.ParseError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
