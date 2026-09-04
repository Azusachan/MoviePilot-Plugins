import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "plugins.v2/cloudsubscribe/handlers/notification/media_server.py"


def install_stub(name, **members):
    module = types.ModuleType(name)
    module.__dict__.update(members)
    sys.modules[name] = module
    return module


class MediaInfo:
    title_year = "Example (2026)"


class RefreshMediaItem:
    pass


for package in ("app", "app.chain", "app.helper", "app.schemas", "app.utils"):
    install_stub(package)

install_stub("app.chain.mediaserver", MediaServerChain=Mock)
install_stub("app.helper.mediaserver", MediaServerHelper=Mock)
install_stub("app.log", logger=Mock())
sys.modules["app.schemas"].MediaInfo = MediaInfo
sys.modules["app.schemas"].RefreshMediaItem = RefreshMediaItem
install_stub(
    "app.schemas.types",
    MediaType=SimpleNamespace(MOVIE="电影", TV="电视剧"),
)
install_stub("app.utils.http", RequestUtils=Mock)

spec = importlib.util.spec_from_file_location("cloudsubscribe_media_server", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(module)


class ResolverTests(unittest.TestCase):
    def setUp(self):
        self.chain = Mock()
        self.media = MediaInfo()
        self.active = SimpleNamespace(instance=SimpleNamespace(is_inactive=lambda: False))
        self.inactive = SimpleNamespace(instance=SimpleNamespace(is_inactive=lambda: True))
        module.MediaServerHelper = Mock()
        module.MediaServerChain = Mock()

    def test_plex_episodes_are_read_through_generic_api(self):
        module.MediaServerHelper.return_value.get_services.return_value = {
            "Plex-Windows": self.active,
            "Disabled": self.inactive,
        }
        self.chain.media_exists.return_value = SimpleNamespace(itemid="show-42")
        module.MediaServerChain.return_value.get_season_episode_ids.return_value = {
            1: "ep-1",
            3: "ep-3",
        }

        checked, episodes = module.MediaServerEpisodeResolver.episode_numbers(
            self.chain, self.media, 1
        )

        self.assertTrue(checked)
        self.assertEqual({1, 3}, episodes)
        self.chain.media_exists.assert_called_once_with(
            mediainfo=self.media,
            server="Plex-Windows",
        )
        module.MediaServerChain.return_value.get_season_episode_ids.assert_called_once_with(
            server="Plex-Windows",
            item_id="show-42",
            season=1,
        )

    def test_missing_show_is_a_successful_empty_check(self):
        module.MediaServerHelper.return_value.get_services.return_value = {
            "Plex-Windows": self.active,
        }
        self.chain.media_exists.return_value = None

        checked, episodes = module.MediaServerEpisodeResolver.episode_numbers(
            self.chain, self.media, 1
        )

        self.assertTrue(checked)
        self.assertEqual(set(), episodes)

    def test_no_active_media_server_fails_closed(self):
        module.MediaServerHelper.return_value.get_services.return_value = {
            "Disabled": self.inactive,
        }

        checked, episodes = module.MediaServerEpisodeResolver.episode_numbers(
            self.chain, self.media, 1
        )

        self.assertFalse(checked)
        self.assertEqual(set(), episodes)


if __name__ == "__main__":
    unittest.main()
