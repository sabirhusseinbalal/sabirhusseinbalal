#!/usr/bin/env python3
"""Generate an aesthetic GitHub profile statistics SVG using public API data."""
from __future__ import annotations
import json, os, re, sys, tempfile, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

API_ROOT = "https://api.github.com"
API_VERSION = "2022-11-28"
ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT_DIR / "assets" / "profile-stats.svg"
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")

class GitHubAPIError(RuntimeError):
    pass

def validate_username(username: str) -> str:
    username = username.strip()
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("GITHUB_USERNAME must be a valid GitHub username.")
    return username

def request_json(url: str) -> Any:
    request = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "profile-stats-card", "X-GitHub-Api-Version": API_VERSION})
    try:
        with urlopen(request, timeout=25) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = ""
        try:
            detail = str(json.loads(exc.read().decode("utf-8")).get("message", ""))
        except Exception:
            pass
        raise GitHubAPIError(f"GitHub API returned HTTP {exc.code}. {detail}".strip()) from exc
    except URLError as exc:
        raise GitHubAPIError(f"Could not reach GitHub API: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise GitHubAPIError("GitHub returned invalid JSON.") from exc

def fetch_public_profile(username: str) -> dict[str, Any]:
    payload = request_json(f"{API_ROOT}/users/{quote(username, safe='')}")
    if not isinstance(payload, dict):
        raise GitHubAPIError("GitHub profile response was not an object.")
    return payload

def fetch_public_repositories(username: str) -> list[dict[str, Any]]:
    repos: list[dict[str, Any]] = []
    page = 1
    while True:
        query = urlencode({"type": "owner", "sort": "updated", "direction": "desc", "per_page": 100, "page": page})
        payload = request_json(f"{API_ROOT}/users/{quote(username, safe='')}/repos?{query}")
        if not isinstance(payload, list):
            raise GitHubAPIError("GitHub repository response was not a list.")
        repos.extend(item for item in payload if isinstance(item, dict))
        if len(payload) < 100:
            return repos
        page += 1

def safe_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return 0

def calculate_metrics(repositories: list[dict[str, Any]], followers: int = 0) -> dict[str, int]:
    original_repos = [repo for repo in repositories if repo.get("fork") is not True]
    return {
        "public_repositories": len(repositories),
        "stars_earned": sum(safe_int(repo.get("stargazers_count")) for repo in original_repos),
        "followers": safe_int(followers),
        "forks_created": sum(1 for repo in repositories if repo.get("fork") is True),
    }

def compact_number(value: int | None) -> str:
    if value is None: return "—"
    if value >= 1_000_000: return f"{value / 1_000_000:.1f}m".replace(".0m", "m")
    if value >= 10_000: return f"{value / 1_000:.0f}k"
    if value >= 1_000: return f"{value / 1_000:.1f}k".replace(".0k", "k")
    return f"{value:,}"

def xml_escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;")

def render_svg(username: str, metrics: dict[str, int], updated_at: datetime | None = None) -> str:
    updated_at = updated_at or datetime.now(timezone.utc)
    date_label = updated_at.astimezone(timezone.utc).strftime("%Y-%m-%d UTC")
    cards = [("PUBLIC REPOS", metrics["public_repositories"]), ("STARS EARNED", metrics["stars_earned"]), ("FOLLOWERS", metrics["followers"]), ("FORKS CREATED", metrics["forks_created"])]
    width, height, left, gap, card_y, card_h = 920, 300, 28, 14, 112, 124
    card_w = (width - left * 2 - gap * 3) / 4
    pieces = []
    for i, (label, value) in enumerate(cards):
        x = left + i * (card_w + gap)
        pieces.append(f'<g><rect x="{x:.1f}" y="{card_y}" width="{card_w:.1f}" height="{card_h}" rx="17" fill="#1b2038" fill-opacity=".92" stroke="#625879"/><text x="{x+18:.1f}" y="{card_y+34}" class="label">{label}</text><text x="{x+18:.1f}" y="{card_y+88}" class="value">{compact_number(value)}</text></g>')
    user = xml_escape(username)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
<title id="title">GitHub statistics for {user}</title><desc id="desc">Public repositories, stars earned, followers and public repositories forked by this account. Updated {date_label}.</desc>
<defs><linearGradient id="night" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#101827"/><stop offset="52%" stop-color="#24223d"/><stop offset="100%" stop-color="#342b4d"/></linearGradient><linearGradient id="moon" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#fff0d5"/><stop offset="100%" stop-color="#c8b9ff"/></linearGradient><style>.heading{{font:700 21px 'Segoe UI',Arial,sans-serif;letter-spacing:2.4px;fill:#f5f0ff}}.subheading{{font:400 12px 'Segoe UI',Arial,sans-serif;fill:#c0bad7;letter-spacing:.5px}}.label{{font:700 10px 'Segoe UI',Arial,sans-serif;letter-spacing:1.15px;fill:#bcb4d7}}.value{{font:700 39px 'Segoe UI',Arial,sans-serif;fill:#fff8ed}}.footer{{font:400 10px 'Segoe UI',Arial,sans-serif;fill:#aaa3c5;letter-spacing:.5px}}</style></defs>
<rect x="1" y="1" width="918" height="298" rx="23" fill="url(#night)" stroke="#625879" stroke-width="1.5"/>
<circle cx="830" cy="49" r="25" fill="url(#moon)" opacity=".95"/><circle cx="841" cy="39" r="22" fill="#24223d"/>
<g fill="#eee7ff" opacity=".8"><circle cx="777" cy="34" r="1.7"/><circle cx="875" cy="77" r="1.4"/><circle cx="737" cy="61" r="1.2"/><path d="M704 29l2 5 5 2-5 2-2 5-2-5-5-2 5-2z"/><path d="M883 116l1.5 4 4 1.5-4 1.5-1.5 4-1.5-4-4-1.5 4-1.5z"/></g>
<text x="30" y="47" class="heading">GITHUB AT A GLANCE</text><text x="30" y="70" class="subheading">A little snapshot of my GitHub journey · @{user}</text><rect x="30" y="82" width="110" height="2.5" rx="2" fill="#c9b7ff"/>
{''.join(pieces)}
<text x="30" y="270" class="footer">LIVE PUBLIC GITHUB DATA  ·  UPDATED {date_label}</text><text x="890" y="270" text-anchor="end" class="footer">LITTLE BY LITTLE, ONE TRAVELS FAR</text></svg>'''

def write_svg(content: str, output_path: Path = OUTPUT_PATH) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ET.fromstring(content)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=output_path.parent, prefix=f"{output_path.name}.", suffix=".tmp", delete=False) as temp:
        temp.write(content)
        temp_path = Path(temp.name)
    temp_path.replace(output_path)

def main() -> int:
    try:
        username = validate_username(os.getenv("GITHUB_USERNAME", "sabirhusseinbalal"))
        profile = fetch_public_profile(username)
        repos = fetch_public_repositories(username)
        metrics = calculate_metrics(repos, safe_int(profile.get("followers")))
        write_svg(render_svg(username, metrics))
        print(f"Updated {OUTPUT_PATH.relative_to(ROOT_DIR)}")
        for key, value in metrics.items(): print(f"{key}: {value}")
        return 0
    except (GitHubAPIError, ValueError, OSError, ET.ParseError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
