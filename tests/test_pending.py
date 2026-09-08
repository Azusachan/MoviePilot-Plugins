import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('pending_test',Path(__file__).resolve().parents[1]/'plugins.v2/cloudsubscribefork/search/pending.py')
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
class PendingTests(unittest.TestCase):
    def test_reservation_is_subscription_and_season_scoped(self):
        pending={'one':dict(subscribe_id=1,season=1,task_type='magnet',target_episodes=[8])}
        self.assertEqual(mod.unreserved_episodes(pending,1,1,[7,8]),[7])
        self.assertEqual(mod.unreserved_episodes(pending,1,1,[8]),[])
        self.assertEqual(mod.unreserved_episodes(pending,2,1,[8]),[8])
        self.assertEqual(mod.unreserved_episodes(pending,1,2,[8]),[8])
    def test_removed_task_does_not_reserve_episode(self):
        self.assertEqual(mod.unreserved_episodes({},1,1,[8]),[8])
