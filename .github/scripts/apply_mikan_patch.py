"""Idempotent integration of the fork-owned Mikan adapter into upstream."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace(path, old, new):
    file = ROOT / path
    text = file.read_text(encoding="utf-8")
    if new in text:
        return
    if text.count(old) != 1:
        raise RuntimeError(f"Mikan integration marker changed: {path}: {old!r}")
    file.write_text(text.replace(old, new), encoding="utf-8")


replace("plugins.v2/cloudsubscribefork/core/hook/events.py",
        '        """新增订阅由搜索调度钩子自动分流。"""\n'
        '        sid = self._get_subscribe_id_from_event(event)\n'
        '        if not sid:\n'
        '            return\n'
        '        if self._is_subscribe_excluded(sid):\n'
        '            logger.debug(f"新增订阅不在插件处理范围：subscribe_id={sid}")\n'
        '            return\n'
        '        logger.debug(f"新增订阅等待搜索调度：subscribe_id={sid}")',
        '        """将接管范围内的新增订阅立即加入现有防抖搜索队列。"""\n'
        '        if not self._enabled or not self._takeover_new_subscribes:\n'
        '            return\n'
        '        sid = self._get_subscribe_id_from_event(event)\n'
        '        if not sid or sid <= 0:\n'
        '            return\n'
        '        if self._is_subscribe_excluded(sid):\n'
        '            logger.debug(f"新增订阅不在插件处理范围：subscribe_id={sid}")\n'
        '            return\n'
        '        if self.queue_subscribe_search(subscribe_id=sid, subscribe_state="N"):\n'
        '            logger.info(f"新增订阅已提交即时搜索队列：subscribe_id={sid}")\n'
        '        else:\n'
        '            logger.warning(f"新增订阅即时搜索未入队，保留定时重试：subscribe_id={sid}")')


replace("plugins.v2/cloudsubscribefork/__init__.py",
        '"pinglian", "piratebay", "uindex", "online_docs",\n            )',
        '"pinglian", "piratebay", "uindex", "online_docs", "mikan",\n            )')
replace("plugins.v2/cloudsubscribefork/__init__.py",
        '            pansou_client=self._pansou_client,',
        '            mikan_config=self.get_config() or {},\n            pansou_client=self._pansou_client,')
replace("plugins.v2/cloudsubscribefork/handlers/search/service.py",
        '            should_stop: Any = None,',
        '            should_stop: Any = None,\n            mikan_config=None,')
replace("plugins.v2/cloudsubscribefork/handlers/search/service.py",
        '        self._pansou_client = pansou_client',
        '        self._mikan_config = mikan_config or {}\n        self._pansou_client = pansou_client')
replace("plugins.v2/cloudsubscribefork/search/registry.py",
        '    return registry',
        '    if "mikan" in owner._search_source_order and "magnet" in resource_types:\n'
        '        from .mikan import create_mikan_provider\n'
        '        registry.register(create_mikan_provider(owner._mikan_config, owner._search_proxy))\n'
        '    return registry')
replace("plugins.v2/cloudsubscribefork/core/config.py",
        '            "piratebay_result_limit": 20,',
        '            "mikan_base_url": "https://mikanani.me",\n'
        '            "mikan_result_limit": 80,\n'
        '            "mikan_timeout": 30,\n'
        '            "mikan_request_interval": 2,\n'
        '            "piratebay_result_limit": 20,')
replace("frontend/cloudsubscribefork/src/config/fields/search/common.js",
        '  {title: "盘链", value: "pinglian"},',
        '  {title: "蜜柑", value: "mikan"},\n  {title: "盘链", value: "pinglian"},')
replace("frontend/cloudsubscribefork/src/config/fields/search/index.js",
        'import {createCommonSearchGroups}',
        'import {createMikanGroups} from "./mikan.js";\nimport {createCommonSearchGroups}')
replace("frontend/cloudsubscribefork/src/config/fields/search/index.js",
        '      ...createPirateBayGroups(),',
        '      ...createMikanGroups(),\n      ...createPirateBayGroups(),')
replace("frontend/cloudsubscribefork/src/config/fields/search/index.js",
        '      {value: "piratebay", title: "海盗湾", icon: "mdi-pirate"},',
        '      {value: "mikan", title: "蜜柑", icon: "mdi-magnet"},\n'
        '      {value: "piratebay", title: "海盗湾", icon: "mdi-pirate"},')
for path in ["frontend/cloudsubscribefork/src/components/Config.vue", "frontend/cloudsubscribefork/src/components/dashboard/HistoryTable.vue"]:
    replace(path, '  pinglian: "盘链",', '  mikan: "蜜柑",\n  pinglian: "盘链",')
replace("plugins.v2/cloudsubscribefork/core/api/form_content.py",
        '("SeedHub", "seedhub"),',
        '("SeedHub", "seedhub"), ("蜜柑", "mikan"),')
replace("plugins.v2/cloudsubscribefork/core/api/search.py",
        '        "pinglian": frozenset({',
        '        "mikan": frozenset({"mikan_base_url", "mikan_result_limit", "mikan_timeout", "mikan_request_interval"}),\n        "pinglian": frozenset({')
replace("plugins.v2/cloudsubscribefork/core/api/search.py",
        '            "pinglian", "pansou", "piratebay", "uindex",',
        '            "pinglian", "pansou", "piratebay", "uindex", "mikan",')
replace("plugins.v2/cloudsubscribefork/core/api/search.py",
        '            pansou_client=pansou_client,',
        '            mikan_config=config,\n            pansou_client=pansou_client,')
replace("plugins.v2/cloudsubscribefork/core/api/search.py",
        '            "pinglian": "盘链",',
        '            "mikan": "蜜柑",\n            "pinglian": "盘链",')
print("Mikan integration applied")
replace("plugins.v2/cloudsubscribefork/handlers/notification/media_server.py",
        '            success = bool(future.result(timeout=self._REFRESH_TIMEOUT_SECONDS))',
        '            result = future.result(timeout=self._REFRESH_TIMEOUT_SECONDS)\n'
        '            # MoviePilot Plex refresh returns None after submitting the HTTP request.\n'
        '            success = bool(result) or (service.type == "plex" and result is None)')
replace("plugins.v2/cloudsubscribefork/utils/file_parser.py",
        '                if relative_path:\n                    item.setdefault("_relative_path", relative_path)',
        '                if relative_path and hasattr(item, "setdefault"):\n'
        '                    item.setdefault("_relative_path", relative_path)')
replace("plugins.v2/cloudsubscribefork/handlers/sync/postprocess.py",
        '            episode_files = self._match_episode_files(\n'
        '                video_files,\n                mediainfo,\n                subscribe,\n'
        '                max(1, int(season or 1)),\n                target_episodes,\n            )',
        '            resource = item.get("resource") or {}\n'
        '            if resource.get("source") == "mikan":\n'
        '                from ...search.mikan import mikan_file_candidates\n'
        '                candidates = mikan_file_candidates(video_files, resource.get("title") or "",\n'
        '                                                   max(1, int(season or 1)), target_episodes)\n'
        '                episode_files = {episode: self._search_handler.select_file_candidate(files, mediainfo, subscribe)\n'
        '                                 for episode, files in candidates.items()}\n'
        '            else:\n'
        '                episode_files = self._match_episode_files(\n'
        '                    video_files, mediainfo, subscribe,\n'
        '                    max(1, int(season or 1)), target_episodes,\n                )')
replace("plugins.v2/cloudsubscribefork/handlers/sync/service.py",
        '            if pending_key in pending:\n                return pending_key\n        if not self._offline_download.add_offline_download(share_url, staging_dir):',
        '            if pending_key in pending:\n                return pending_key\n'
        '            if subscribe_id and season and target_episodes and not upgrade:\n'
        '                from ...search.pending import unreserved_episodes\n'
        '                target_episodes[:] = unreserved_episodes(pending, subscribe_id, season, target_episodes)\n'
        '                if not target_episodes:\n'
        '                    logger.info("跳过重复候选：目标集已有待完成的离线任务")\n'
        '                    return ""\n'
        '        if not self._offline_download.add_offline_download(share_url, staging_dir):')
replace("plugins.v2/cloudsubscribefork/handlers/search/service.py",
        '        for result in results:\n            result.setdefault("source", source)',
        '        from ...search.fansubs import filter_fansubs, is_japanese_anime\n'
        '        if is_japanese_anime(mediainfo):\n'
        '            before = len(results)\n'
        '            results = filter_fansubs(results)\n'
        '            logger.info(f"[{source.upper()}] 日番字幕策略：{before} → {len(results)}")\n'
        '        for result in results:\n            result.setdefault("source", source)')
replace("plugins.v2/cloudsubscribefork/handlers/search/service.py",
        '            *self._resource_target_coverage(resource, season, targets),',
        '            -int(resource.get("fansub_priority") or 0),\n'
        '            *self._resource_target_coverage(resource, season, targets),')
replace("plugins.v2/cloudsubscribefork/handlers/search/service.py",
        '                *coverage,',
        '                -int(item.get("fansub_priority") or 0),\n                *coverage,')
replace("frontend/cloudsubscribefork/src/components/Config.vue",
        'const sourceTestConfigKeys = {',
        'const sourceTestConfigKeys = {\n  mikan: ["mikan_base_url", "mikan_result_limit", "mikan_request_interval", "mikan_timeout"],')
