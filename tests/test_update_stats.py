import unittest
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
from scripts.update_stats import calculate_metrics, compact_number, render_svg, validate_username

class StatsTests(unittest.TestCase):
    def test_username_validation(self):
        self.assertEqual(validate_username('sabirhusseinbalal'), 'sabirhusseinbalal')
        with self.assertRaises(ValueError): validate_username('../bad')

    def test_counts_metrics_correctly(self):
        repos = [
            {'fork': False, 'stargazers_count': 4},
            {'fork': True, 'stargazers_count': 99},
            {'fork': False, 'stargazers_count': 3},
            {'fork': True, 'stargazers_count': 0},
        ]
        result = calculate_metrics(repos, followers=7)
        self.assertEqual(result, {'public_repositories': 4, 'stars_earned': 7, 'followers': 7, 'forks_created': 2})

    def test_bad_numbers_are_safe(self):
        result = calculate_metrics([{'fork': False, 'stargazers_count': 'bad'}], followers='bad')
        self.assertEqual(result['stars_earned'], 0)
        self.assertEqual(result['followers'], 0)

    def test_svg_contains_all_four_live_metrics(self):
        metrics = {'public_repositories': 39, 'stars_earned': 12, 'followers': 8, 'forks_created': 3}
        svg = render_svg('sabirhusseinbalal', metrics, datetime(2026, 11, 4, tzinfo=timezone.utc))
        ET.fromstring(svg)
        for label in ('GITHUB AT A GLANCE', 'PUBLIC REPOS', 'STARS EARNED', 'FOLLOWERS', 'FORKS CREATED'):
            self.assertIn(label, svg)

    def test_username_is_escaped(self):
        svg = render_svg('user&name', {'public_repositories': 0, 'stars_earned': 0, 'followers': 0, 'forks_created': 0})
        self.assertIn('user&amp;name', svg)
        ET.fromstring(svg)

    def test_number_formatting(self):
        self.assertEqual(compact_number(0), '0')
        self.assertEqual(compact_number(1500), '1.5k')
        self.assertEqual(compact_number(2_000_000), '2m')

if __name__ == '__main__':
    unittest.main()
