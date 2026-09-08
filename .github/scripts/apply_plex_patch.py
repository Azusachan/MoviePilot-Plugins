#!/usr/bin/env python3
"""Apply the small, fail-closed Plex compatibility patch to upstream."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MEDIA_SERVER = ROOT / "plugins.v2/cloudsubscribefork/handlers/notification/media_server.py"
NOTIFICATION_INIT = ROOT / "plugins.v2/cloudsubscribefork/handlers/notification/__init__.py"
TELEVISION = ROOT / "plugins.v2/cloudsubscribefork/handlers/sync/television.py"

RESOLVER = '''class MediaServerEpisodeResolver:
    """Read existing TV episodes through MoviePilot's generic media-server API."""

    @staticmethod
    def episode_numbers(
            chain, mediainfo: MediaInfo, season: int
    ) -> tuple[bool, Set[int]]:
        """Return whether an active server was checked and its existing episodes."""
        services = MediaServerHelper().get_services()
        if not services or not chain or not mediainfo:
            return False, set()

        mediaserver_chain = MediaServerChain()
        checked = False
        episodes: Set[int] = set()
        for server_name, service in services.items():
            if service.instance.is_inactive():
                continue
            try:
                exists_media = chain.media_exists(
                    mediainfo=mediainfo,
                    server=server_name,
                )
                checked = True
                if not exists_media or not exists_media.itemid:
                    continue
                episode_ids = mediaserver_chain.get_season_episode_ids(
                    server=server_name,
                    item_id=exists_media.itemid,
                    season=season,
                )
                episodes.update(int(episode) for episode in (episode_ids or {}))
            except Exception as error:
                logger.warning(
                    f"读取媒体服务器剧集清单失败：{server_name} - "
                    f"{mediainfo.title_year} S{season:02d}，原因：{error}"
                )
        return checked, episodes


'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one upstream marker, found {count}")
    return text.replace(old, new, 1)


def patch_media_server() -> None:
    text = MEDIA_SERVER.read_text(encoding="utf-8")
    if "class MediaServerEpisodeResolver:" in text:
        return
    marker = "class EmbyMediaResolver:\n"
    text = replace_once(text, marker, RESOLVER + marker, "media resolver insertion")
    MEDIA_SERVER.write_text(text, encoding="utf-8")


def patch_notification_exports() -> None:
    text = NOTIFICATION_INIT.read_text(encoding="utf-8")
    if "MediaServerEpisodeResolver" in text:
        return
    text = replace_once(
        text,
        "from .media_server import EmbyMediaResolver, MediaServerNotifier",
        "from .media_server import (\n"
        "    EmbyMediaResolver,\n"
        "    MediaServerEpisodeResolver,\n"
        "    MediaServerNotifier,\n"
        ")",
        "notification import",
    )
    text = replace_once(
        text,
        '__all__ = ["EmbyMediaResolver", "MediaServerNotifier", "WebhookHandler"]',
        '__all__ = [\n'
        '    "EmbyMediaResolver",\n'
        '    "MediaServerEpisodeResolver",\n'
        '    "MediaServerNotifier",\n'
        '    "WebhookHandler",\n'
        ']',
        "notification export",
    )
    NOTIFICATION_INIT.write_text(text, encoding="utf-8")


def patch_television() -> None:
    text = TELEVISION.read_text(encoding="utf-8")
    if "MediaServerEpisodeResolver.episode_numbers" in text:
        return
    replacements = (
        ("from ..notification import EmbyMediaResolver", "from ..notification import MediaServerEpisodeResolver"),
        ("# 1. 先读取 Emby 实际剧集，不混入订阅 note。", "# 1. 先通过 MoviePilot 的通用媒体服务器接口读取实际剧集。"),
        ("emby_valid, emby_episodes", "mediaserver_valid, mediaserver_episodes"),
        ('"emby_scan"', '"mediaserver_scan"'),
        ("EmbyMediaResolver.episode_numbers", "MediaServerEpisodeResolver.episode_numbers"),
        ("emby_episodes & expected_episodes", "mediaserver_episodes & expected_episodes"),
        ("if not emby_valid:", "if not mediaserver_valid:"),
        ("emby_episodes = set()", "mediaserver_episodes = set()"),
        ("未读取到 Emby 数据", "未读取到媒体服务器数据"),
        ("无法读取 Emby 实际数据", "无法读取媒体服务器实际数据"),
        ("Emby 实际存在剧集", "媒体服务器实际存在剧集"),
        ("Emby 与115合并后已存在", "媒体服务器与115合并后已存在"),
        ("Emby 与115均不存在", "媒体服务器与115均不存在"),
        ("Emby 与115已完整存在", "媒体服务器与115已完整存在"),
    )
    for old, new in replacements:
        if old not in text:
            raise SystemExit(f"television patch marker missing: {old}")
        text = text.replace(old, new)
    TELEVISION.write_text(text, encoding="utf-8")


def main() -> None:
    patch_media_server()
    patch_notification_exports()
    patch_television()
    print("Plex compatibility patch applied")


if __name__ == "__main__":
    main()
