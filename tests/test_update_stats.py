import unittest
from datetime import datetime, timezone

from scripts.update_stats import (
    calculate_metrics,
    format_number,
    render_stats_section,
    replace_stats_section,
    validate_username,
)


class StatsTests(unittest.TestCase):
    def test_username_validation(self):
        self.assertEqual(validate_username("sabirhusseinbalal"), "sabirhusseinbalal")
        with self.assertRaises(ValueError):
            validate_username("../bad")

    def test_counts_public_metrics_correctly(self):
        repositories = [
            {"fork": False, "stargazers_count": 4},
            {"fork": True, "stargazers_count": 99},
            {"fork": False, "stargazers_count": 3},
            {"fork": True, "stargazers_count": 0},
        ]
        result = calculate_metrics(repositories, followers=1, public_repositories=39)
        self.assertEqual(
            result,
            {
                "public_repositories": 39,
                "stars_earned": 7,
                "followers": 1,
                "forks_created": 2,
            },
        )

    def test_private_follower_count_is_not_falsely_shown_as_zero(self):
        result = calculate_metrics([], followers=None, public_repositories=39)
        self.assertIsNone(result["followers"])
        self.assertEqual(format_number(result["followers"]), "hidden")

    def test_non_numeric_values_are_safe(self):
        result = calculate_metrics(
            [{"fork": False, "stargazers_count": "not-a-number"}],
            followers="not-a-number",
        )
        self.assertEqual(result["stars_earned"], 0)
        self.assertEqual(result["followers"], 0)

    def test_written_section_matches_moonlit_style(self):
        metrics = {
            "public_repositories": 39,
            "stars_earned": 0,
            "followers": 1,
            "forks_created": 4,
        }
        section = render_stats_section(
            "sabirhusseinbalal",
            metrics,
            datetime(2026, 11, 4, tzinfo=timezone.utc),
        )
        for expected in (
            "☾ ✦ A LITTLE SPACE UNDER THE STARS ✦ ☽",
            "✧ GITHUB AT A GLANCE ✧",
            "Public repositories",
            "Stars earned",
            "Followers",
            "Forks created",
            "little by little, one travels far.",
            "🦋",
        ):
            self.assertIn(expected, section)

    def test_readme_replacement_preserves_banner(self):
        original = (
            '<img src="animation.gif" />\n\n'
            '<!-- PROFILE-STATS:START -->old stats<!-- PROFILE-STATS:END -->\n'
        )
        replacement = render_stats_section(
            "sabirhusseinbalal",
            {
                "public_repositories": 39,
                "stars_earned": 0,
                "followers": 1,
                "forks_created": 4,
            },
        )
        updated = replace_stats_section(original, replacement)
        self.assertIn('src="animation.gif"', updated)
        self.assertIn("GITHUB AT A GLANCE", updated)
        self.assertNotIn("old stats", updated)

    def test_number_formatting(self):
        self.assertEqual(format_number(0), "0")
        self.assertEqual(format_number(1500), "1,500")
        self.assertEqual(format_number(None), "hidden")


if __name__ == "__main__":
    unittest.main()
