"""搜索阶段中间态生命周期与状态机重置测试。"""

import importlib.util
import os
import sys
import types
import unittest
from unittest.mock import MagicMock

# 构造 mock 的 app 包结构
mock_app = types.ModuleType("app")
mock_app.__path__ = []
sys.modules["app"] = mock_app

mock_app_core = types.ModuleType("app.core")
mock_app_core.__path__ = []
mock_app_core.config = MagicMock()
mock_app_core.config.global_vars = MagicMock()
mock_app_core.config.settings = MagicMock()
mock_app_core.context = MagicMock()
mock_app_core.metainfo = MagicMock()
sys.modules["app.core"] = mock_app_core
sys.modules["app.core.config"] = mock_app_core.config
sys.modules["app.core.context"] = mock_app_core.context
sys.modules["app.core.metainfo"] = mock_app_core.metainfo

mock_app_db = types.ModuleType("app.db")
mock_app_db.__path__ = []
mock_app_db.SessionFactory = MagicMock()
mock_app_db.subscribe_oper = MagicMock()
sys.modules["app.db"] = mock_app_db
sys.modules["app.db.subscribe_oper"] = mock_app_db.subscribe_oper

mock_app_log = types.ModuleType("app.log")
mock_app_log.logger = MagicMock()
sys.modules["app.log"] = mock_app_log

mock_app_schemas = types.ModuleType("app.schemas")
mock_app_schemas.__path__ = []
mock_app_schemas.types = MagicMock()
sys.modules["app.schemas"] = mock_app_schemas
sys.modules["app.schemas.types"] = mock_app_schemas.types

mock_app_utils = types.ModuleType("app.utils")
mock_app_utils.__path__ = []
mock_app_utils.http = MagicMock()
sys.modules["app.utils"] = mock_app_utils
sys.modules["app.utils.http"] = mock_app_utils.http


class OwnerDelegator:
    def __init__(self, owner=None):
        object.__setattr__(self, "_owner", owner)

    def __getattr__(self, name):
        return getattr(self._owner, name) if self._owner else None

    def __setattr__(self, name, value):
        if name == "_owner":
            object.__setattr__(self, name, value)
            return
        if self._owner:
            setattr(self._owner, name, value)


pkg = types.ModuleType("cloudsubscribe")
pkg.__path__ = []
sys.modules["cloudsubscribe"] = pkg

mock_core = types.ModuleType("cloudsubscribe.core")
mock_core.__path__ = []
mock_core.OwnerDelegator = OwnerDelegator
mock_core.CloudDriveCapability = MagicMock()
sys.modules["cloudsubscribe.core"] = mock_core

mock_media = types.ModuleType("cloudsubscribe.core.media")
mock_media.apply_media_identity = MagicMock()
mock_media.legacy_media_ids = MagicMock()
mock_media.media_identity = MagicMock()
mock_media.recognize_media = MagicMock()
mock_media.search_medias = MagicMock()
mock_media.tmdb_id_of = MagicMock()
mock_media.tmdb_identity_update = MagicMock()
sys.modules["cloudsubscribe.core.media"] = mock_media

mock_utils = types.ModuleType("cloudsubscribe.utils")
mock_utils.__path__ = []
sys.modules["cloudsubscribe.utils"] = mock_utils

mock_utils_cache = types.ModuleType("cloudsubscribe.utils.cache")
mock_utils_cache.normalize_platform_cache_key = MagicMock()
sys.modules["cloudsubscribe.utils.cache"] = mock_utils_cache

# 动态加载 metadata.py
base_dir = os.path.dirname(__file__)
meta_path = os.path.abspath(os.path.join(base_dir, "../plugins.v2/cloudsubscribe/handlers/sync/metadata.py"))
spec_m = importlib.util.spec_from_file_location("cloudsubscribe.handlers.sync.metadata", meta_path)
mod_m = importlib.util.module_from_spec(spec_m)
spec_m.loader.exec_module(mod_m)
SyncMetadataService = mod_m.SyncMetadataService

# 动态加载 runtime.py
runtime_path = os.path.abspath(os.path.join(base_dir, "../plugins.v2/cloudsubscribe/core/services/runtime.py"))
spec_r = importlib.util.spec_from_file_location("cloudsubscribe.core.services.runtime", runtime_path)
mod_r = importlib.util.module_from_spec(spec_r)
spec_r.loader.exec_module(mod_r)
SyncRuntimeService = mod_r.SyncRuntimeService


class TestSearchStateLifecycle(unittest.TestCase):
    """测试搜索渠道状态的生命周期重置契约。"""

    def test_idle_search_state_structure(self):
        """验证搜索闲置状态的标准数据结构。"""
        state = SyncMetadataService._idle_search_state()
        self.assertEqual(state, {
            "search_active": False,
            "search_channels": [],
            "search_total_results": 0,
        })
        self.assertEqual(SyncRuntimeService._idle_search_state(), state)

    def test_set_task_phase_no_text_magic_sniffing(self):
        """验证 _set_task_phase 不再根据包含'转存'或'后处理'等文案偷偷清空搜索态。"""
        task_update_mock = MagicMock()
        service = SyncMetadataService(owner=MagicMock(_task_update=task_update_mock))

        subscribe = MagicMock()
        subscribe.id = 123
        subscribe._transient_target = False

        # 阶段名包含"转存"，但 clear_search 为 False（默认）
        service._set_task_phase(subscribe, "正在转存电影文件", 80)
        task_update_mock.assert_called_once_with(
            "subscribe:123",
            phase="正在转存电影文件",
            progress=80,
        )
        self.assertNotIn("search_active", task_update_mock.call_args[1])
        self.assertNotIn("search_channels", task_update_mock.call_args[1])

    def test_set_task_phase_explicit_clear_search(self):
        """验证 _set_task_phase 在 clear_search=True 时显式重置搜索态。"""
        task_update_mock = MagicMock()
        service = SyncMetadataService(owner=MagicMock(_task_update=task_update_mock))

        subscribe = MagicMock()
        subscribe.id = 123
        subscribe._transient_target = False

        service._set_task_phase(subscribe, "转存匹配文件", 90, clear_search=True)
        task_update_mock.assert_called_once_with(
            "subscribe:123",
            phase="转存匹配文件",
            progress=90,
            search_active=False,
            search_channels=[],
            search_total_results=0,
        )

    def test_clear_task_search_state(self):
        """验证 _clear_task_search_state 显式调用。"""
        task_update_mock = MagicMock()
        service = SyncMetadataService(owner=MagicMock(_task_update=task_update_mock))

        subscribe = MagicMock()
        subscribe.id = 456
        subscribe._transient_target = False

        service._clear_task_search_state(subscribe)
        task_update_mock.assert_called_once_with(
            "subscribe:456",
            search_active=False,
            search_channels=[],
            search_total_results=0,
        )

    def test_runtime_service_status_transition_safeguard(self):
        """验证 runtime 服务在状态进入 transferring/downloading/postprocessing 时自动兜底收敛搜索态。"""
        runtime = SyncRuntimeService(owner=MagicMock())
        task_id = "subscribe:789"
        runtime._sync_tasks = {
            task_id: {
                "id": task_id,
                "status": "running",
                "phase": "搜索候选资源",
                "search_active": True,
                "search_channels": [{"key": "quark", "name": "夸克网盘", "count": 2}],
                "search_total_results": 2,
            }
        }

        # 状态切换为 transferring，应触发状态机兜底清理
        runtime._update_sync_task(task_id, status="transferring", phase="转存中")
        updated_task = runtime._sync_tasks[task_id]

        self.assertEqual(updated_task["status"], "transferring")
        self.assertFalse(updated_task["search_active"])
        self.assertEqual(updated_task["search_channels"], [])
        self.assertEqual(updated_task["search_total_results"], 0)


if __name__ == "__main__":
    unittest.main()
