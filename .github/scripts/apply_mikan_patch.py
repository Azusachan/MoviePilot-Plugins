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


replace("plugins.v2/cloudsubscribe/__init__.py",
        '"pinglian", "online_docs",\n            )',
        '"pinglian", "online_docs", "mikan",\n            )')
replace("plugins.v2/cloudsubscribe/__init__.py",
        '            pansou_client=self._pansou_client,',
        '            mikan_config=self.get_config() or {},\n            pansou_client=self._pansou_client,')
replace("plugins.v2/cloudsubscribe/handlers/search/service.py",
        '            should_stop: Any = None,',
        '            should_stop: Any = None,\n            mikan_config=None,')
replace("plugins.v2/cloudsubscribe/handlers/search/service.py",
        '        self._pansou_client = pansou_client',
        '        self._mikan_config = mikan_config or {}\n        self._pansou_client = pansou_client')
replace("plugins.v2/cloudsubscribe/search/registry.py",
        '    return registry',
        '    if "mikan" in owner._search_source_order and "magnet" in resource_types:\n'
        '        from .mikan import create_mikan_provider\n'
        '        registry.register(create_mikan_provider(owner._mikan_config, owner._search_proxy))\n'
        '    return registry')
replace("plugins.v2/cloudsubscribe/core/config.py",
        '            "butailing_result_limit": 20,',
        '            "mikan_base_url": "https://mikanani.me",\n'
        '            "mikan_result_limit": 80,\n'
        '            "mikan_timeout": 30,\n'
        '            "mikan_request_interval": 2,\n'
        '            "butailing_result_limit": 20,')
replace("frontend/cloudsubscribe/src/config/fields/search/common.js",
        '  {title: "不太灵", value: "butailing"},',
        '  {title: "蜜柑", value: "mikan"},\n  {title: "不太灵", value: "butailing"},')
replace("frontend/cloudsubscribe/src/config/fields/search/index.js",
        'import {createButailingGroups}',
        'import {createMikanGroups} from "./mikan.js";\nimport {createButailingGroups}')
replace("frontend/cloudsubscribe/src/config/fields/search/index.js",
        '      ...createButailingGroups(),',
        '      ...createMikanGroups(),\n      ...createButailingGroups(),')
replace("frontend/cloudsubscribe/src/config/fields/search/index.js",
        '      {value: "butailing", title: "不太灵", icon: "mdi-magnet"},',
        '      {value: "mikan", title: "蜜柑", icon: "mdi-magnet"},\n'
        '      {value: "butailing", title: "不太灵", icon: "mdi-magnet"},')
for path in ["frontend/cloudsubscribe/src/components/Config.vue", "frontend/cloudsubscribe/src/components/dashboard/HistoryTable.vue"]:
    replace(path, '  butailing: "不太灵",', '  mikan: "蜜柑",\n  butailing: "不太灵",')
replace("plugins.v2/cloudsubscribe/core/api/form_content.py",
        '("不太灵", "butailing"),',
        '("不太灵", "butailing"), ("蜜柑", "mikan"),')
replace("plugins.v2/cloudsubscribe/core/api/search.py",
        '        "butailing": frozenset({',
        '        "mikan": frozenset({"mikan_base_url", "mikan_result_limit", "mikan_timeout", "mikan_request_interval"}),\n        "butailing": frozenset({')
replace("plugins.v2/cloudsubscribe/core/api/search.py",
        '            "butailing", "pinglian", "pansou",',
        '            "butailing", "pinglian", "pansou", "mikan",')
replace("plugins.v2/cloudsubscribe/core/api/search.py",
        '            pansou_client=pansou_client,',
        '            mikan_config=config,\n            pansou_client=pansou_client,')
replace("plugins.v2/cloudsubscribe/core/api/search.py",
        '            "butailing": "不太灵",',
        '            "mikan": "蜜柑",\n            "butailing": "不太灵",')
print("Mikan integration applied")
replace("plugins.v2/cloudsubscribe/handlers/sync/service.py",
        '            if pending_key in pending:\n                return pending_key\n        if not self._offline_download.add_offline_download(share_url, staging_dir):',
        '            if pending_key in pending:\n                return pending_key\n'
        '            if subscribe_id and season and target_episodes and not upgrade:\n'
        '                from ...search.pending import unreserved_episodes\n'
        '                target_episodes[:] = unreserved_episodes(pending, subscribe_id, season, target_episodes)\n'
        '                if not target_episodes:\n'
        '                    logger.info("跳过重复候选：目标集已有待完成的离线任务")\n'
        '                    return ""\n'
        '        if not self._offline_download.add_offline_download(share_url, staging_dir):')
replace("plugins.v2/cloudsubscribe/handlers/search/service.py",
        '        for result in results:\n            result.setdefault("source", source)',
        '        from ...search.fansubs import filter_fansubs, is_japanese_anime\n'
        '        if is_japanese_anime(mediainfo):\n'
        '            before = len(results)\n'
        '            results = filter_fansubs(results)\n'
        '            logger.info(f"[{source.upper()}] 日番字幕策略：{before} → {len(results)}")\n'
        '        for result in results:\n            result.setdefault("source", source)')
replace("plugins.v2/cloudsubscribe/handlers/search/service.py",
        '            *self._resource_target_coverage(resource, season, targets),',
        '            -int(resource.get("fansub_priority") or 0),\n'
        '            *self._resource_target_coverage(resource, season, targets),')
replace("plugins.v2/cloudsubscribe/handlers/search/service.py",
        '                *coverage,',
        '                -int(item.get("fansub_priority") or 0),\n                *coverage,')
replace("frontend/cloudsubscribe/src/components/Config.vue",
        'const sourceTestConfigKeys = {',
        'const sourceTestConfigKeys = {\n  mikan: ["mikan_base_url", "mikan_result_limit", "mikan_request_interval", "mikan_timeout"],')
