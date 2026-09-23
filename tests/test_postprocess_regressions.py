import ast
import importlib.util
from pathlib import Path
import sys
import threading
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1] / 'plugins.v2/cloudsubscribefork'
pkg = types.ModuleType('bracket_search_tests')
pkg.__path__ = [str(ROOT / 'search')]
sys.modules[pkg.__name__] = pkg
for name in ('matching', 'subs_filter'):
    spec = importlib.util.spec_from_file_location(pkg.__name__ + '.' + name, ROOT / 'search' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
policy = module


def load_nodes(path, names, namespace):
    tree = ast.parse((ROOT / path).read_text(encoding='utf-8'))
    nodes = [node for node in tree.body if getattr(node, 'name', None) in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


class BracketMatchingTests(unittest.TestCase):
    release = '[爱恋字幕社&猫恋汉化组][7月新番][拔作岛][Nukitashi The Animation][08][1080P][BIG5][MP4][繁中]'

    def test_real_files_all_eight_episodes(self):
        for episode in range(1, 9):
            title = 'Nukitashi The Animation' if episode < 6 else 'Nukitashi'
            group = 'KissSub&Romanticat' if episode < 6 else 'Comicat&KissSub'
            name = f'[{group}][{title}][{episode:02}][1080p][BIG5][MP4].mp4'
            file = {'name': name}
            self.assertEqual(policy.anime_file_candidates([file], self.release, 1, [episode]), {episode: [file]})

    def test_no_false_match_on_group_or_technical_tags(self):
        for title in ('Other Show', 'Nukitashi Extra', '1080P'):
            name = f'[KissSub][{title}][08][1080P][BIG5][MP4].mp4'
            self.assertEqual(policy.anime_file_candidates([{'name': name}], self.release, 1, [8]), {8: []})
        self.assertEqual(policy.release_titles('[KissSub][08][1080P][BIG5][MP4].mp4'), [])

    def test_season_episode_and_subtitle_guards(self):
        for name in ('[KissSub][Nukitashi][09][BIG5].mp4',
                     '[KissSub][Nukitashi S02][08][BIG5].mp4',
                     '[KissSub][Nukitashi][08][无字幕].mp4',
                     '[Unknown][Nukitashi][08][BIG5].mp4'):
            self.assertEqual(policy.anime_file_candidates([{'name': name}], self.release, 1, [8]), {8: []})

    def test_plain_title_unchanged(self):
        self.assertEqual(policy.release_titles('[SweetSub] Example / 例子 - 08 [1080p][CHS]'), ['Example', '例子'])

    def test_specials_are_explicit_and_season_scoped(self):
        for title, expected in (('[SweetSub] Example OVA_01 [CHS]', [1]),
                                ('[SweetSub] Example - EX01~EX02 [CHS]', [1, 2]),
                                ('[SweetSub] Example S00E03 [CHS]', [3])):
            self.assertEqual(policy.release_episodes(title, 0), expected)
            self.assertTrue(policy.release_season_matches(title, 0))
            self.assertFalse(policy.release_season_matches(title, 1))
            self.assertIsNone(policy.fansub_priority(title))
            self.assertIsNotNone(policy.fansub_priority(title, {'_target_season': 0}))
        self.assertEqual(policy.release_episodes('[SweetSub] Example [01-11+OVA][CHS]', 0), [])
        self.assertFalse(policy.release_season_matches('[SweetSub] Example - 01 [CHS]', 0))

    def test_star_group_and_ova_real_file(self):
        title = '六四位元字幕组★Example★OVA_01★1920x1080★AVC AAC MP4★繁体中文'
        file = {'name': title + '.mp4'}
        self.assertEqual(policy.anime_file_candidates([file], title, 0, [1]), {1: [file]})
        self.assertEqual(policy.anime_file_candidates([file], title, 1, [1]), {1: []})

    def test_actual_ova_torrent_file(self):
        title = '六四位元字幕组★住在拔作岛上的我该如何是好 Nukitashi★OVA_01★1920x1080★AVC AAC MP4★繁体中文'
        file = {'name': '[64bitsub][Nukitashi][OVA_01][BDRIP_1920x1080][AVC_AAC][CHT].mp4'}
        self.assertEqual(policy.anime_file_candidates([file], title, 0, [1]), {1: [file]})


class TimeoutTests(unittest.TestCase):
    def test_native_transport_limits_and_no_mutation_retry(self):
        namespace = load_nodes('drive/p115/client.py', {'_bounded_p115_request'}, {})
        transport = types.ModuleType('urllib3_future_request')
        transport.request = Mock(return_value='ok')
        util = types.ModuleType('urllib3_future.util')
        util.Timeout = lambda **kw: kw
        extensions = {'timeout': {'connect': 2, 'read': 3, 'pool': 4}}
        with patch.dict(sys.modules, {'urllib3_future_request': transport, 'urllib3_future.util': util}):
            self.assertEqual(namespace['_bounded_p115_request']('url', extensions=extensions), 'ok')
        kwargs = transport.request.call_args.kwargs
        self.assertEqual(kwargs['timeout'], {'connect': 2, 'read': 3})
        self.assertEqual(kwargs['pool_timeout'], 4)
        self.assertEqual(kwargs['retries'], 0)
        self.assertNotIn('extensions', kwargs)
        self.assertIn('timeout', extensions)


class MonitorLockTests(unittest.TestCase):
    def test_active_monitor_defers_config_without_blocking_search(self):
        tree = ast.parse((ROOT / 'core/services/sync.py').read_text(encoding='utf-8'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
        node = next(n for n in cls.body if getattr(n, 'name', '') == '_apply_pending_config_if_idle')
        namespace = {}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<test>', 'exec'), namespace)
        owner = types.SimpleNamespace(_offline_monitor_lock=threading.Lock(), _apply_pending_config=Mock(return_value=True))
        owner._offline_monitor_lock.acquire()
        self.assertFalse(namespace[node.name](owner))
        owner._apply_pending_config.assert_not_called()
        owner._offline_monitor_lock.release()
        self.assertTrue(namespace[node.name](owner))
        self.assertFalse(owner._offline_monitor_lock.locked())
