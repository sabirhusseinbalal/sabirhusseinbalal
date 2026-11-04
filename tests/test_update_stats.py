import unittest
from unittest.mock import patch
from urllib.parse import urlparse, parse_qs
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from scripts.update_stats import (
    calculate_metrics,
    compact_number,
    fetch_public_repositories,
    render_svg,
    validate_username,
)


class ValidateUsernameTests(unittest.TestCase):
    def test_accepts_profile_username(self):
        self.assertEqual(validate_username("sabirhusseinbalal"), "sabirhusseinbalal")

    def test_rejects_invalid_username(self):
        with self.assertRaises(ValueError):
            validate_username("../someone")


class CalculateMetricsTests(unittest.TestCase):
    def test_counts_public_repos_and_only_original_repo_stars_and_forks(self):
        repos = [
            {"fork": False, "stargazers_count": 4, "forks_count": 2},
            {"fork": True, "stargazers_count": 99, "forks_count": 50},
            {"fork": False, "stargazers_count": 3, "forks_count": 1},
        ]
        result = calculate_metrics(repos, followers=7)
        self.assertEqual(result["public_repositories"], 3)
        self.assertEqual(result["stars_earned"], 7)
        self.assertEqual(result["forks_received"], 3)
        self.assertEqual(result["followers"], 7)

    def test_missing_or_invalid_counts_are_safe(self):
        result = calculate_metrics([{"fork": False, "stargazers_count": "bad"}])
        self.assertEqual(result["stars_earned"], 0)
        self.assertEqual(result["forks_received"], 0)
        self.assertIsNone(result["followers"])


class RepositoryPaginationTests(unittest.TestCase):
    @patch("scripts.update_stats.request_json")
    def test_fetches_all_pages_and_requests_owned_public_repositories(self, request_json):
        first_page = [{"id": i} for i in range(100)]
        second_page = [{"id": 100}, {"id": 101}]
        request_json.side_effect = [first_page, second_page]

        repositories = fetch_public_repositories("sabirhusseinbalal")

        self.assertEqual(len(repositories), 102)
        self.assertEqual(request_json.call_count, 2)
        first_url = request_json.call_args_list[0].args[0]
        query = parse_qs(urlparse(first_url).query)
        self.assertEqual(query["type"], ["owner"])
        self.assertEqual(query["per_page"], ["100"])
        second_url = request_json.call_args_list[1].args[0]
        self.assertIn("page=2", second_url)


class SvgTests(unittest.TestCase):
    def test_renders_valid_svg_without_follower_card_by_default(self):
        metrics = {
            "public_repositories": 39,
            "stars_earned": 12,
            "forks_received": 2,
            "followers": None,
        }
        svg = render_svg(
            "sabirhusseinbalal",
            metrics,
            updated_at=datetime(2026, 11, 4, tzinfo=timezone.utc),
        )
        root = ET.fromstring(svg)
        self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
        self.assertIn("GITHUB AT A GLANCE", svg)
        self.assertIn("PUBLIC REPOSITORIES", svg)
        self.assertIn("STARS EARNED", svg)
        self.assertIn("FORKS OF YOUR REPOS", svg)
        self.assertNotIn("FOLLOWERS</text>", svg)

    def test_can_render_follower_metric_when_explicitly_enabled(self):
        metrics = {
            "public_repositories": 1,
            "stars_earned": 0,
            "forks_received": 0,
            "followers": 8,
        }
        svg = render_svg(
            "sabirhusseinbalal",
            metrics,
            updated_at=datetime(2026, 11, 4, tzinfo=timezone.utc),
            show_followers=True,
        )
        self.assertIn("FOLLOWERS", svg)
        self.assertIn(">8</text>", svg)
        ET.fromstring(svg)

    def test_username_is_xml_escaped(self):
        svg = render_svg(
            "user&name",
            {"public_repositories": 0, "stars_earned": 0, "forks_created": 0},
            updated_at=datetime(2026, 11, 4, tzinfo=timezone.utc),
        )
        self.assertIn("user&amp;name", svg)
        ET.fromstring(svg)


class NumberFormattingTests(unittest.TestCase):
    def test_compact_number(self):
        self.assertEqual(compact_number(None), "—")
        self.assertEqual(compact_number(0), "0")
        self.assertEqual(compact_number(1500), "1.5k")
        self.assertEqual(compact_number(12000), "12k")
        self.assertEqual(compact_number(2_000_000), "2m")


if __name__ == "__main__":
    unittest.main()
