"""Run inside a disposable MoviePilot image, never against production /config."""
import socket
import tempfile
from pathlib import Path
from types import SimpleNamespace

def deny_network(*args, **kwargs):
    raise RuntimeError('Runtime smoke tests must not contact external services')
socket.socket.connect = deny_network
socket.create_connection = deny_network

from app.plugins.cloudsubscribefork import CloudSubscribeFork
from app.plugins.cloudsubscribefork.core.config import UIConfig
from app.plugins.cloudsubscribefork.core.storage import CloudSubscribeForkDataStore
from app.plugins.cloudsubscribefork.search.scanner import SearchSourceRegistry
from app.plugins.cloudsubscribefork.drive.scanner import DriverRegistry

assert CloudSubscribeFork.plugin_config_prefix == 'cloudsubscribefork_'
sources = {definition.id for definition in SearchSourceRegistry.get_definitions()}
assert {'mikan', 'pansou', 'hdhive', 'seedhub', 'animegarden'} <= sources, sources
assert '115' in {definition.id for definition in DriverRegistry.get_definitions()}
config = dict(enabled=False, takeover_new_subscribes=True,
              search_source_order=['mikan', 'pansou'], mikan_base_url='https://mikanani.me',
              mikan_result_limit=80, mikan_timeout=30)
original = dict(config)
UIConfig.normalize_config(config)
for key, value in original.items():
    assert config[key] == value, key

# The model schema is unchanged from stable 1.3.7. Exercise reopening the same
# persistent file and initialization twice, with pending/history payloads.
with tempfile.TemporaryDirectory(prefix='azusa-db-test-') as folder:
    owner = SimpleNamespace(get_data_path=lambda: Path(folder))
    store = CloudSubscribeForkDataStore(owner)
    history = [{'id': 'fixture', 'title': 'Fixture', 'status': 'success',
                'tmdb_id': '123', 'type': '电影', 'source': 'mikan'}]
    pending = {'fixture': {'subscribe_id': 7, 'season': 1, 'target_episodes': [8],
                           'task_type': 'magnet', 'status': 'pending'}}
    store.save('history', history)
    store.save('pending_offline_strm', pending)
    before_history = store.load('history')
    before_pending = store.load('pending_offline_strm')
    reopened = CloudSubscribeForkDataStore(owner)
    assert reopened.load('history') == before_history
    assert reopened.load('pending_offline_strm') == before_pending
    assert (Path(folder) / 'cloudsubscribefork.db').is_file()
print('Runtime imports, source discovery, config preservation and DB reopen passed')
