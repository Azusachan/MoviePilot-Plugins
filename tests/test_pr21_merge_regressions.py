"""Protect fork safety boundaries across the upstream postprocess refactor."""
import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1] / 'plugins.v2/cloudsubscribefork'


def load_method(path, name, **extra):
    tree = ast.parse((ROOT / path).read_text(encoding='utf-8'))
    method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    scope = dict(Any=Any, Dict=Dict, List=List, Optional=Optional, logger=Mock(), **extra)
    exec(compile(ast.Module(body=[method], type_ignores=[]), path, 'exec'), scope)
    return scope[name]


class MergeSafetyTests(unittest.TestCase):
    def test_precise_lookup_failure_never_falls_back(self):
        method = load_method('handlers/sync/postprocess.py', '_list_magnet_files')
        cloud = Mock()
        cloud.list_offline_task_files.side_effect = RuntimeError('missing file id')
        with self.assertRaises(RuntimeError):
            method(SimpleNamespace(_cloud_query=cloud), {'staging_dir': '/'}, {})
        cloud.list_files_recursive.assert_not_called()

    def test_no_task_capability_cannot_scan_root(self):
        method = load_method('handlers/sync/postprocess.py', '_list_magnet_files')
        cloud = SimpleNamespace(list_files_recursive=Mock())
        for item in ({}, {'staging_dir': '/'}):
            with self.assertRaises(RuntimeError):
                method(SimpleNamespace(_cloud_query=cloud), item, None)
        cloud.list_files_recursive.assert_not_called()

    def test_failure_cleanup_does_not_delete_cloud_task(self):
        method = load_method('handlers/sync/postprocess.py', '_cleanup_failed_offline_task')
        host = Mock()
        method(host, {'task_id': 'accepted'}, 'transient failure')
        host._offline_tasks.delete_offline_task.assert_not_called()

    def test_completed_magnet_lookup_error_schedules_retry(self):
        # Bind the new upstream context signature, not the old subscribe_cache kwarg.
        method = load_method('handlers/sync/postprocess.py', '_finalize_magnet_due_item',
                             PostprocessBatchContext=Any)
        host = Mock()
        host._finalize_magnet_package.side_effect = RuntimeError('lookup temporarily failed')
        item = {}
        ctx = SimpleNamespace(now=123, subscribe_cache={})
        method(host, item, 'key', ctx, {'completed': True})
        self.assertTrue(item['download_completed'])
        host._schedule_finalize_retry.assert_called_once_with(item, 123)
        host._finalize_magnet_package.assert_called_once_with(item, 'key', ctx, offline_task={'completed': True})

