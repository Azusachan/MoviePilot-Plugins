import types
import unittest
from unittest.mock import MagicMock

from plugin_env import OwnerDelegator, ensure_package, install_app_mocks, load_module, set_media_type

install_app_mocks(
    "app.core", "app.core.config", "app.core.context", "app.core.metainfo", "app.db",
    "app.db.subscribe_oper", "app.utils", "app.utils.string", "app.modules",
    "app.modules.filemanager", "app.modules.filemanager.transhandler",
    "cloudsubscribefork", "cloudsubscribefork.core", "cloudsubscribefork.core.media",
    "cloudsubscribefork.handlers", "cloudsubscribefork.handlers.sync",
    "cloudsubscribefork.handlers.notification",
    "cloudsubscribefork.search",
    "cloudsubscribefork.utils",
    "cloudsubscribefork.utils.cache",
)
MediaType = set_media_type(movie="电影", tv="电视剧")

ensure_package("cloudsubscribefork.core").OwnerDelegator = OwnerDelegator
ensure_package("cloudsubscribefork.utils.cache").create_platform_ttl_cache = lambda *args, **kwargs: {}

# 实际加载 media
media_mod = load_module(
    "cloudsubscribefork.core.media",
    "plugins.v2/cloudsubscribefork/core/media.py",
)
ensure_package("cloudsubscribefork.core").media = media_mod

load_module(
    "cloudsubscribefork.search.types",
    "plugins.v2/cloudsubscribefork/search/types.py",
)
load_module(
    "cloudsubscribefork.search.matching",
    "plugins.v2/cloudsubscribefork/search/matching.py",
)

runtime_mod = load_module(
    "cloudsubscribefork.core.services.runtime",
    "plugins.v2/cloudsubscribefork/core/services/runtime.py",
)
SyncRuntimeService = runtime_mod.SyncRuntimeService

sync_api_mod = load_module(
    "cloudsubscribefork.core.api.sync",
    "plugins.v2/cloudsubscribefork/core/api/sync.py",
)
SyncApi = sync_api_mod.SyncApi


class TestSeriesSubscriptionSync(unittest.TestCase):
    def test_sync_series_group_key_groups_all_seasons(self):
        """测试同剧集不同季归入同一队列，避免拆散多队列导致重复并发搜索。"""
        sub_s1 = types.SimpleNamespace(type=MediaType.TV.value, tmdb_id=12345, name="良陈美锦", season=1)
        sub_s2 = types.SimpleNamespace(type=MediaType.TV.value, tmdb_id=12345, name="良陈美锦", season=2)
        sub_s3 = types.SimpleNamespace(type=MediaType.TV.value, tmdb_id=12345, name="良陈美锦", season=3)

        key1 = SyncRuntimeService._sync_series_group_key(sub_s1)
        key2 = SyncRuntimeService._sync_series_group_key(sub_s2)
        key3 = SyncRuntimeService._sync_series_group_key(sub_s3)

        self.assertEqual(key1, key2)
        self.assertEqual(key2, key3)
        self.assertEqual(key1, (MediaType.TV.value, "themoviedb:12345"))

    def test_manual_sync_with_empty_metadata_safe_unpacking(self):
        """测试手动添加 Magnet/直链时，空元数据安全解构不会触发 KeyError: 'resource_ref' 或 'target_episodes'。"""
        owner = MagicMock()
        owner._cloud_drive = MagicMock()
        owner._cloud_drive.key = "guangya"
        owner._offline_download = MagicMock()
        owner._offline_download.is_magnet_url.return_value = True
        owner._offline_download.is_ed2k_url.return_value = False
        owner._offline_download.parse_magnet_metadata = MagicMock(
            return_value={"name": "良陈美锦", "metadata_available": True})
        owner._resource_type_order = ["magnet", "guangya"]
        owner._manual_resource_type.return_value = "magnet"

        api = SyncApi(owner)
        payload = {
            "subscribe_id": 0,
            "media": {"tmdb_id": 12345, "media_type": "tv", "title": "良陈美锦"},
            "resource_links": ["magnet:?xt=urn:btih:0749695e009731d953fecba32aed7d9a2e2d5c00"],
            "resources": [],
        }

        owner._submit_sync_operation = MagicMock(return_value=MagicMock())
        owner._cloud_drive.name = "光鸭"
        res = api.api_vue_start_manual_sync(payload, wait=False)
        self.assertTrue(res.get("success"), f"Should succeed but got: {res}")


if __name__ == "__main__":
    unittest.main()
