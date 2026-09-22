import ast
from pathlib import Path
import unittest
from types import SimpleNamespace
from typing import Any, Dict, Optional, Iterable, List, Set

source = Path(__file__).resolve().parents[1]/'plugins.v2/cloudsubscribefork/handlers/sync/service.py'
tree = ast.parse(source.read_text(encoding='utf-8'))
owner = next(node for node in tree.body if isinstance(node, ast.ClassDef))
owner.bases = []
owner.body = [node for node in owner.body if isinstance(node, ast.FunctionDef)
              and node.name in ('_is_same_media_target', '_unreserved_episodes')]
namespace = dict(Any=Any, Dict=Dict, Optional=Optional, Iterable=Iterable, List=List, Set=Set,
                 tmdb_id_of=lambda value: (value or {}).get('tmdbid'),
                 legacy_media_ids=lambda value: value or {})
exec(compile(ast.Module(body=[owner], type_ignores=[]), str(source), 'exec'), namespace)
mod = SimpleNamespace(unreserved_episodes=namespace[owner.name]._unreserved_episodes)
class PendingTests(unittest.TestCase):
    def test_reservation_is_subscription_and_season_scoped(self):
        pending={'one':dict(subscribe_id=1,season=1,task_type='magnet',target_episodes=[8])}
        self.assertEqual(mod.unreserved_episodes(pending,1,1,[7,8]),[7])
        self.assertEqual(mod.unreserved_episodes(pending,1,1,[8]),[])
        self.assertEqual(mod.unreserved_episodes(pending,2,1,[8]),[8])
        self.assertEqual(mod.unreserved_episodes(pending,1,2,[8]),[8])
    def test_removed_task_does_not_reserve_episode(self):
        self.assertEqual(mod.unreserved_episodes({},1,1,[8]),[8])
