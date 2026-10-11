"""洗版重复转存防护测试：备份文件识别、保守跳过与残留备份清理。"""

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from plugin_env import (
    OwnerDelegator,
    ensure_package,
    install_app_mocks,
    load_module,
    register_mock,
    register_package,
)


def ensure_package_attrs(name: str, **attrs) -> None:
    """仅在缺失时补位模块属性，避免覆盖其他用例注册的实现。"""
    module = sys.modules.get(name)
    if module is None:
        register_package(name, **attrs)
        return
    for key, value in attrs.items():
        if not hasattr(module, key):
            setattr(module, key, value)


install_app_mocks(
    "app.core",
    "app.core.context",
    "app.core.metainfo",
    "app.domain",
    "app.domain.episode",
    "app.helper",
    "app.helper.directory",
    "app.log",
    "app.modules",
    "app.modules.filemanager",
    "app.modules.filemanager.transhandler",
    "app.modules.themoviedb",
    "app.modules.themoviedb.category",
    "app.schemas",
    "app.schemas.types",
    "app.sdk",
    "app.sdk.classification",
    "app.utils",
    "app.utils.string",
)
register_mock("cloudsubscribe")
_cloud = load_module(
    "cloudsubscribe.core.cloud",
    "plugins.v2/cloudsubscribe/core/cloud.py",
)
register_package(
    "cloudsubscribe.core",
    OwnerDelegator=OwnerDelegator,
    CloudDriveCapability=_cloud.CloudDriveCapability,
    CloudFile=_cloud.CloudFile,
)
load_module("cloudsubscribe.core.media", "plugins.v2/cloudsubscribe/core/media.py")
ensure_package("cloudsubscribe.drive")
ensure_package_attrs("cloudsubscribe.drive.common", format_size=lambda size: f"{size} B")
ensure_package_attrs("cloudsubscribe.utils", FileMatcher=MagicMock(), MediaFileParser=MagicMock())
register_package("cloudsubscribe.handlers")
register_package("cloudsubscribe.handlers.sync")

_sync_utils = load_module(
    "cloudsubscribe.handlers.sync.utils",
    "plugins.v2/cloudsubscribe/handlers/sync/utils.py",
)
ensure_package_attrs(
    "cloudsubscribe.handlers.sync.baseline",
    normalize_platform_cache_key=lambda value: str(value),
)

_rule_scoring = load_module(
    "cloudsubscribe.handlers.sync.rule_scoring",
    "plugins.v2/cloudsubscribe/handlers/sync/rule_scoring.py",
)
_naming = load_module(
    "cloudsubscribe.handlers.sync.naming",
    "plugins.v2/cloudsubscribe/handlers/sync/naming.py",
)

is_upgrade_backup_name = _sync_utils.is_upgrade_backup_name
strip_upgrade_backup_suffix = _sync_utils.strip_upgrade_backup_suffix
RuleScoringService = _rule_scoring.UpgradeRuleScoringService
SyncNamingService = _naming.SyncNamingService
CloudFile = _cloud.CloudFile


class TestBackupNameDetection(unittest.TestCase):
    def test_backup_name_matches(self):
        self.assertTrue(is_upgrade_backup_name("剧.S01E01.2160p-abcdef1234.mkv"))
        self.assertTrue(is_upgrade_backup_name("电影.2024-abc123XYZ9.mp4"))

    def test_strip_suffix_for_backup(self):
        self.assertEqual(
            strip_upgrade_backup_suffix("剧.S01E01.2160p-abcdef1234.mkv"),
            "剧.S01E01.2160p",
        )
        self.assertEqual(strip_upgrade_backup_suffix("剧.S01E01.2160p.mkv"), "")

    def test_normal_name_not_matched(self):
        self.assertFalse(is_upgrade_backup_name("剧.S01E01.2160p.mkv"))
        self.assertFalse(is_upgrade_backup_name("电影.2024-1080p.mkv"))
        self.assertFalse(is_upgrade_backup_name(""))


class TestUpgradeCandidateGuard(unittest.TestCase):
    """目标季存在无法解析集号的既有文件时，缺版本集不得再转存。"""

    @classmethod
    def setUpClass(cls):
        cls.service = RuleScoringService(SimpleNamespace(_upgrade_mode="largest"))

    def test_no_existing_transfers_by_default(self):
        should, reason = self.service._should_upgrade_candidate(0, 10, has_existing=False)
        self.assertTrue(should)
        self.assertEqual(reason, "无现有版本")

    def test_unparsed_season_suppresses_transfer(self):
        should, reason = self.service._should_upgrade_candidate(
            0, 10, has_existing=False, suppress_when_unparsed=True
        )
        self.assertFalse(should)
        self.assertIn("保守跳过", reason)

    def test_existing_episode_still_compares(self):
        should, _ = self.service._should_upgrade_candidate(
            10, 20, 100, 200, has_existing=True, suppress_when_unparsed=True
        )
        self.assertTrue(should)


class TestLeftoverBackupCleanup(unittest.TestCase):
    """同集已有正常文件时清理残留备份；备份是唯一副本时保留。"""

    def build_service(self, deleted_ids=("b1", "b2"), pending=None):
        service = SyncNamingService(
            SimpleNamespace(
                _upgrade_mode="largest",
                _cloud_batch_mutations=MagicMock(),
                _OFFLINE_PENDING_KEY="pending_offline_strm",
                _get_data=lambda key: dict(pending or {}),
            )
        )
        service._cloud_batch_mutations.delete_files = MagicMock(
            return_value=set(deleted_ids)
        )
        return service

    def test_cleanup_when_normal_file_exists(self):
        service = self.build_service()
        normal = CloudFile(id="n1", name="剧.S01E01.2160p.mkv", is_directory=False, size=100)
        backup = CloudFile(id="b1", name="剧.S01E01.2160p-abcdef1234.mkv", is_directory=False, size=90)
        episode_all = {1: [normal, backup]}

        removed = service._cleanup_episode_backups(episode_all, "/media/x/Season 1")

        self.assertEqual(removed, 1)
        service._cloud_batch_mutations.delete_files.assert_called_once_with(["b1"])
        self.assertEqual([item.id for item in episode_all[1]], ["n1"])

    def test_backup_kept_when_only_copy(self):
        service = self.build_service()
        backup = CloudFile(id="b2", name="剧.S01E02.2160p-abcdef1234.mkv", is_directory=False)
        episode_all = {2: [backup]}

        removed = service._cleanup_episode_backups(episode_all, "/media/x/Season 1")

        self.assertEqual(removed, 0)
        service._cloud_batch_mutations.delete_files.assert_not_called()
        self.assertEqual([item.id for item in episode_all[2]], ["b2"])

    def test_backup_tracked_by_pending_is_kept(self):
        """后处理队列仍在追踪的备份不得清理，否则该项会一直重试直至失败。"""
        service = self.build_service(pending={
            "k1": {
                "upgrade_backup_name": "剧.S01E01.2160p-abcdef1234.mkv",
                "upgrade_old_file_id": "b1",
            }
        })
        normal = CloudFile(id="n1", name="剧.S01E01.2160p.mkv", is_directory=False)
        backup = CloudFile(id="b1", name="剧.S01E01.2160p-abcdef1234.mkv", is_directory=False)

        removed = service._cleanup_episode_backups({1: [normal, backup]}, "/media/x/Season 1")

        self.assertEqual(removed, 0)
        service._cloud_batch_mutations.delete_files.assert_not_called()

    def test_unrelated_tail_name_is_kept(self):
        """非本集同名主干（合法名恰好也带 10 位短串）不得被当作备份删除。"""
        service = self.build_service()
        normal = CloudFile(id="n1", name="剧.S01E05.2160p.mkv", is_directory=False)
        other = CloudFile(id="b9", name="剧.S01E05.其他版-abcdefghij.mkv", is_directory=False)

        removed = service._cleanup_episode_backups({5: [normal, other]}, "/media/x/Season 1")

        self.assertEqual(removed, 0)
        service._cloud_batch_mutations.delete_files.assert_not_called()

    def test_same_backup_mapped_to_multiple_episodes_deleted_once(self):
        service = self.build_service()
        normal = CloudFile(id="n1", name="剧.S01E06.2160p.mkv", is_directory=False)
        backup = CloudFile(id="b1", name="剧.S01E06.2160p-abcdef1234.mkv", is_directory=False)

        removed = service._cleanup_episode_backups(
            {6: [normal, backup], 7: [normal, backup]}, "/media/x/Season 1"
        )

        self.assertEqual(removed, 1)
        service._cloud_batch_mutations.delete_files.assert_called_once_with(["b1"])

    def test_cleanup_survives_delete_failure(self):
        service = self.build_service()
        service._cloud_batch_mutations.delete_files = MagicMock(side_effect=RuntimeError("boom"))
        normal = CloudFile(id="n1", name="剧.S01E03.2160p.mkv", is_directory=False)
        backup = CloudFile(id="b1", name="剧.S01E03.2160p-abcdef1234.mkv", is_directory=False)

        removed = service._cleanup_episode_backups({3: [normal, backup]}, "/media/x/Season 1")

        self.assertEqual(removed, 0)


class StubDirectories:
    """目录解析/列出的假驱动器：可指定先失败后成功。"""

    def __init__(self, lookups, listings, refreshable=True):
        self.lookups = list(lookups)
        self.listings = list(listings)
        self.refresh_calls = 0
        if refreshable:
            self.refresh_directories = self._refresh

    def _refresh(self):
        self.refresh_calls += 1

    def resolve_directory(self, path):
        return self.lookups.pop(0) if self.lookups else SimpleNamespace(checked=False, directory_id=None)

    def list_directory(self, directory_id):
        return self.listings.pop(0) if self.listings else SimpleNamespace(checked=False, files=())


def lookup(directory_id="cid-1", checked=True):
    return SimpleNamespace(checked=checked, directory_id=directory_id)


def listing(checked=True, files=()):
    return SimpleNamespace(checked=checked, files=files)


class TestDirectoryListRetry(unittest.TestCase):
    """列目录失败时失效缓存重试一次，避免陈旧 CID 让整轮订阅永久跳过。"""

    def test_retry_after_stale_cache(self):
        file_item = CloudFile(id="f1", name="剧.S01E01.mkv", is_directory=False)
        directories = StubDirectories([lookup(), lookup()], [listing(False), listing(True, (file_item,))])

        checked, files = SyncNamingService._resolve_and_list(directories, "/媒体/剧/Season 01")

        self.assertTrue(checked)
        self.assertEqual([item.id for item in files], ["f1"])
        self.assertEqual(directories.refresh_calls, 1)

    def test_missing_directory_treated_as_empty(self):
        directories = StubDirectories([lookup(), lookup(None)], [listing(False)])

        checked, files = SyncNamingService._resolve_and_list(directories, "/媒体/剧/Season 01")

        self.assertTrue(checked)
        self.assertEqual(files, [])
        self.assertEqual(directories.refresh_calls, 1)

    def test_retry_failure_reports_unchecked(self):
        directories = StubDirectories([lookup(), lookup()], [listing(False), listing(False)])

        checked, files = SyncNamingService._resolve_and_list(directories, "/媒体/剧/Season 01")

        self.assertFalse(checked)
        self.assertEqual(files, [])

    def test_refresh_called_once_before_giving_up(self):
        """重试前必须失效一次目录缓存；两次都失败才判定无法确认。"""
        directories = StubDirectories([lookup(), lookup()], [listing(False), listing(False)])

        checked, files = SyncNamingService._resolve_and_list(directories, "/媒体/剧/Season 01")

        self.assertFalse(checked)
        self.assertEqual(files, [])
        self.assertEqual(directories.refresh_calls, 1)


if __name__ == "__main__":
    unittest.main()
