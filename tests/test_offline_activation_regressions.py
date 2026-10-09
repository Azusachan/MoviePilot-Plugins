"""Exercise production state boundaries without app startup or cloud IO."""
import ast
from pathlib import Path
import re
from threading import RLock
import time
from typing import Any, Dict, List, Optional, Set
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1] / 'plugins.v2/cloudsubscribefork/handlers/sync'

def method(filename, name):
    tree = ast.parse((ROOT / filename).read_text(encoding='utf-8'))
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    scope = dict(Any=Any, Dict=Dict, List=List, Optional=Optional, Set=Set, time=time, re=re,
                 extract_ed2k_filename=lambda url: '',
                 Path=Path, logger=Mock(), extract_magnet_hash=lambda url: re.search(r'btih:([0-9a-f]{40})', url, re.I).group(1).upper())
    exec(compile(ast.Module(body=[node], type_ignores=[]), filename, 'exec'), scope)
    return scope[name]

class OfflineActivationRegressionTests(unittest.TestCase):
    def test_monitor_repairs_orphan_but_not_inflight_history(self):
        host = Mock()
        host._get_data.return_value = {
            'old': {'created_at': time.time()-120, 'history_ready': False},
            'new': {'created_at': time.time(), 'history_ready': False},
            'submitting': {'created_at': time.time()-120, 'status': 'submitting'},
            'ready': {'created_at': time.time()-120, 'history_ready': True},
        }
        host._prepare_postprocess_context.return_value = None
        method('postprocess.py', 'monitor_offline_strm_tasks')(host)
        self.assertEqual([call.args[1] for call in host._persist_offline_pending_history.call_args_list], ['old'])

    def test_provider_only_manifest_has_idempotent_task_history(self):
        host = Mock()
        host._magnet_history_entries.return_value = []
        host._build_transfer_history_item.side_effect = lambda **kw: kw
        history = []
        args = dict(history=history, mediainfo=object(), subscribe=object(), share_url='fixture',
                    cloud_dir='/staging', resource={'title':'[Haruhana] Fate - 01 [CHI_JPN]'},
                    finalize_key='magnet:fixture:2', season=1, target_episodes=[1])
        append = method('resources.py', '_append_magnet_pending_history')
        self.assertEqual(append(host, **args), 1)
        self.assertTrue(history[0]['manifest_pending'])
        self.assertEqual(history[0]['status'], '下载中')
        self.assertEqual(history[0]['episode'], 1)
        self.assertEqual(append(host, **args), 0)

    def test_boolean_submission_uses_native_hash_and_persists_immediately(self):
        host = Mock()
        host._offline_pending_lock = RLock()
        host._get_data.return_value = {}
        host._serialize_mediainfo.return_value = {}
        host._cloud_transfer_path = '/staging'
        host._OFFLINE_CHECK_DELAYS = [10]
        host._upgrade_mode = 'largest'
        ctx = dict(pending_key='magnet:'+'A'*40+':2', prefix='magnet',
                   share_url='magnet:?xt=urn:btih:'+'a'*40, staging_dir='/staging',
                   resource={'title':'Fate - 01'}, subscribe=object(), mediainfo=object(),
                   subscribe_id=2, season=1, target_episodes=[1])
        method('service.py', '_complete_offline_submission')(host, ctx)
        pending = host._save_offline_pending.call_args.args[0]
        self.assertEqual(pending[ctx['pending_key']]['task_id'], 'A'*40)
        host._persist_offline_pending_history.assert_called_once()

    def test_history_io_failure_preserves_accepted_task(self):
        host = Mock()
        host._offline_pending_lock = RLock()
        host._get_data.return_value = {}
        host._serialize_mediainfo.return_value = {}
        host._OFFLINE_CHECK_DELAYS = [10]
        host._persist_offline_pending_history.side_effect = OSError('fixture DB failure')
        ctx = dict(pending_key='magnet:'+'A'*40+':2', prefix='magnet',
                   share_url='magnet:?xt=urn:btih:'+'a'*40, staging_dir='/staging',
                   resource={'title':'Fate - 01'}, subscribe=object(), mediainfo=object(),
                   subscribe_id=2, season=1, target_episodes=[1])
        method('service.py', '_complete_offline_submission')(host, ctx)
        self.assertIn(ctx['pending_key'], host._save_offline_pending.call_args.args[0])
