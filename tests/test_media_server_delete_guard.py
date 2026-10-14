"""媒体库条目删除守卫与刷新日志测试：仅整目录删除才移除条目；同一媒体多条删除记录的未找到日志合并为一条。"""

import types
import unittest
from unittest.mock import MagicMock

from plugin_env import install_app_mocks, load_module, register_mock, register_package

install_app_mocks(
    "app.chain",
    "app.chain.mediaserver",
    "app.helper",
    "app.helper.mediaserver",
    "app.log",
    "app.schemas",
    "app.schemas.types",
    "app.utils",
    "app.utils.http",
)
register_mock("cloudsubscribefork")
register_package("cloudsubscribefork.handlers")
register_package("cloudsubscribefork.handlers.notification")

_media_server = load_module(
    "cloudsubscribefork.handlers.notification.media_server",
    "plugins.v2/cloudsubscribefork/handlers/notification/media_server.py",
)
MediaServerNotifier = _media_server.MediaServerNotifier


class TestEntryFullyDeleted(unittest.TestCase):
    def test_partial_file_deletion_keeps_item(self):
        """部分删除：只上报具体文件时不得移除媒体库条目。"""
        entry = {
            "paths": {"/media/tv/Show/Season 01/Show.S01E01.strm"},
            "deleted_paths": {"/media/tv/Show/Season 01/Show.S01E01.strm"},
        }
        self.assertFalse(MediaServerNotifier._entry_fully_deleted(entry))

    def test_directory_removal_marks_fully_deleted(self):
        """整目录消失：上报目录路径时可安全移除条目。"""
        entry = {
            "paths": {"/media/tv/Show/Season 01"},
            "deleted_paths": {
                "/media/tv/Show/Season 01/Show.S01E01.strm",
                "/media/tv/Show/Season 01",
            },
        }
        self.assertTrue(MediaServerNotifier._entry_fully_deleted(entry))

    def test_non_deleted_entry_is_false(self):
        entry = {"paths": {"/media/tv/Show/Season 01/Show.S01E01.strm"}, "deleted_paths": set()}
        self.assertFalse(MediaServerNotifier._entry_fully_deleted(entry))

    def test_empty_deleted_paths_is_false(self):
        self.assertFalse(MediaServerNotifier._entry_fully_deleted({}))


class TestMissingItemLogDedupe(unittest.TestCase):
    """同一媒体的多条删除记录（多集/多路径）只应产生一条「未找到条目」日志。"""

    def _notifier(self):
        notifier = object.__new__(MediaServerNotifier)
        notifier._emby_refresh_connection = lambda service: ("http://emby", "key")
        notifier._find_emby_item_id = lambda **kwargs: None
        notifier._entry_fully_deleted = lambda entry: True
        notifier.emby_mediainfo_enabled = False
        return notifier

    def test_duplicate_missing_entries_logged_once(self):
        notifier = self._notifier()
        service = types.SimpleNamespace(type="emby", instance=MagicMock())
        entries = [
            {"deleted_paths": {"/a"}, "tmdb_id": 1423191, "title": "兰香如故"},
            {"deleted_paths": {"/b"}, "tmdb_id": 1423191, "title": "兰香如故"},
        ]

        globals_map = MediaServerNotifier._refresh_emby_entries.__globals__
        recorder = MagicMock()
        original = globals_map["logger"]
        globals_map["logger"] = recorder
        try:
            self.assertTrue(notifier._refresh_emby_entries("Emby", service, entries))
        finally:
            globals_map["logger"] = original

        missing = [
            call.args[0] for call in recorder.debug.call_args_list
            if "未找到媒体条目" in call.args[0]
        ]
        self.assertEqual(len(missing), 1, missing)
        self.assertIn("2 条记录已合并", missing[0])
        self.assertIn(
            "Emby (Emby) 媒体处理完成：成功 0 个，无命中的待刷新条目",
            [call.args[0] for call in recorder.info.call_args_list],
        )


if __name__ == "__main__":
    unittest.main()
