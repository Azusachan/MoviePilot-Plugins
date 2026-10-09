import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / 'plugins.v2/cloudsubscribefork/core/episodes.py'
spec = importlib.util.spec_from_file_location('episode_count_fixture', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
correct = module.bangumi_main_episode_total

class BangumiEpisodeCountTests(unittest.TestCase):
    def test_real_botan_mixed_total(self):
        self.assertEqual(correct(25, 1, 12, {'eps': 12, 'total_episodes': 25}), 12)

    def test_user_override_other_season_and_uncorroborated_metadata_preserved(self):
        for current, season, main, subject in (
            (24, 1, 12, {'eps': 12, 'total_episodes': 25}),
            (25, 0, 12, {'eps': 12, 'total_episodes': 25}),
            (25, 2, 12, {'eps': 12, 'total_episodes': 25}),
            (25, 1, 13, {'eps': 12, 'total_episodes': 25}),
            (25, 1, 12, {}), (25, 1, 12, None),
            (12, 1, 12, {'eps': 12, 'total_episodes': 12}),
            (25, 1, 12, {'eps': True, 'total_episodes': 25}),
        ):
            self.assertEqual(correct(current, season, main, subject), current)
