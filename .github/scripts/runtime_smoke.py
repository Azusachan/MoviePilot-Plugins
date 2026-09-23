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
from app.plugins.cloudsubscribefork.handlers.search.service import SearchHandler
from app.schemas.types import MediaType

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

# Exercise the actual common result boundary, including non-anime bypass.
handler = SimpleNamespace(
    _prefilter_resource_order=lambda rows, **kwargs: rows,
    _search_label=lambda *args: 'fixture',
    _filter_by_platform_rules=lambda rows, *args, **kwargs: rows,
)
anime = SimpleNamespace(category='日番', original_language='ja', genre_ids=[16])
movie = SimpleNamespace(category='电影', original_language='en', genre_ids=[18])
titles = ['[桜都字幕组] Fixture [08][CHS]', '[SweetSub] Fixture [08][CHS]',
          'Fixture [08][CHS]', '[LoliHouse] Fixture [08][CHS]',
          '[SweetSub] Fixture [08][无字幕]']
for source in ('pansou', 'mikan', 'animegarden'):
    rows = [{'title': title} for title in titles]
    accepted = SearchHandler._prepare_source_results(
        handler, rows, source, anime, MediaType.TV, None, 1, [8], True)
    assert [row['title'] for row in accepted] == [titles[1], titles[0]], source
rows = [{'title': 'Fixture movie without fansub tags'}]
assert SearchHandler._prepare_source_results(
    handler, rows, 'pansou', movie, MediaType.MOVIE, None, None, None, True) == rows

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

# Regression: 1.5.7 renamed the 115 path keys. Both runtime initialization and
# UI normalization must migrate before defaults are applied, without replacing
# an explicitly configured new path (including the deliberate root directory).
legacy = dict(cloud_transfer_path='/staging', cloud_media_path='/library')
UIConfig.migrate_drive_paths(legacy)
assert legacy == dict(p115_transfer_path='/staging', p115_media_path='/library')
UIConfig.migrate_drive_paths(legacy)
explicit = dict(cloud_transfer_path='/old', p115_transfer_path='/')
UIConfig.migrate_drive_paths(explicit)
assert explicit == dict(p115_transfer_path='/')

from app.plugins.cloudsubscribefork.drive.p115.files import P115FileService
from app.plugins.cloudsubscribefork.drive.p115.offline import OfflineDownloadService
task = OfflineDownloadService._format_offline_task(
    dict(info_hash='ABC', status=2, file_id='7', wp_path_id=0))
assert task['file_id'] == '7' and task['parent_id'] == '0'
directory_calls = []
fixture_tree = {
    '0': [dict(id=7, name='target.mkv', is_dir=False, parent_id=0),
          dict(id=8, name='unrelated', is_dir=True, parent_id=0)],
    '9': [dict(id=10, name='nested.mkv', is_dir=False, parent_id=9),
          dict(id=9, name='cycle', is_dir=True, parent_id=9)],
}
class FixtureFiles(P115FileService):
    def list_files_by_cid_checked(self, cid):
        directory_calls.append(str(cid))
        return True, fixture_tree[str(cid)]
files = FixtureFiles(SimpleNamespace())
found = files.list_offline_task_files(task, '/')
assert [file['id'] for file in found] == [7]
assert directory_calls == ['0'], directory_calls
try:
    files.list_offline_task_files({}, '/')
    raise AssertionError('Missing metadata must fail closed')
except RuntimeError:
    pass
assert directory_calls == ['0']
fixture_tree['0'].append(dict(id=9, name='package', is_dir=True, parent_id=0))
task['file_id'] = '9'
directory_calls.clear()
assert [file['id'] for file in files.list_offline_task_files(task, '/')] == [10]
assert directory_calls == ['0', '9'], directory_calls

# Exercise real lease acquisition, dispatch and reconciliation with cloud IO
# replaced; completed downloads must finalize, and lookup errors retain them.
import copy
import threading
import time
from unittest.mock import patch
from app.plugins.cloudsubscribefork.handlers.sync.postprocess import PostprocessService
for fails in (False, True):
    pending = {'fixture': dict(task_type='magnet', task_id='ABC',
                              subscribe_id=0, created_at=time.time())}
    def save_pending(values):
        pending.clear()
        pending.update(copy.deepcopy(values))
    owner = SimpleNamespace(
        _get_data=lambda key: copy.deepcopy(pending),
        _save_offline_pending=save_pending,
        _OFFLINE_PENDING_KEY='pending_offline_strm',
        _OFFLINE_MONITOR_LEASE_SECONDS=900,
        _OFFLINE_CHECK_DELAYS=(10, 20, 40),
        _OFFLINE_TIMEOUT=1800,
        _offline_pending_lock=threading.RLock(),
        _cloud_directories=True, _cloud_query=True, _cloud_mutations=True,
        _cloud_batch_mutations=None, _stop_requested=lambda: False,
        _postprocess_task_update=None,
        _notify_offline_pending_changed=lambda count: None,
        _schedule_finalize_retry=lambda item, now: item.update(check_index=1),
    )
    with patch.object(PostprocessService, '_finalize_magnet_package',
                      side_effect=RuntimeError('fixture lookup failure') if fails else None,
                      return_value=[dict(episode=9)]) as finalize, \
         patch.object(PostprocessService, '_flush_batch_postprocess'), \
         patch.object(PostprocessService, '_postprocess_task_id', return_value=''):
        result = PostprocessService(owner).monitor_offline_strm_tasks(
            offline_tasks=[dict(id='ABC', completed=True)], offline_tasks_valid=True)
        assert finalize.call_args.kwargs['offline_task']['completed']
        if fails:
            assert result['pending'] == 1 and pending['fixture']['check_index'] == 1
            assert '_monitor_token' not in pending['fixture']
            assert '_monitor_until' not in pending['fixture']
        else:
            assert result['completed'] == 1 and not pending
print('115 path migration, scoped file lookup and postprocess recovery passed')

from app.plugins.cloudsubscribefork.search.mikan.service import MikanSearchService
from app.plugins.cloudsubscribefork.core.search import SearchQuery
from app.db import SessionFactory
from app.db.models.systemconfig import SystemConfig
with SessionFactory() as fixture_db:
    SystemConfig.__table__.create(fixture_db.get_bind(), checkfirst=True)
searches = []
class AliasClient:
    def search_bangumis(self, keyword):
        return []  # The related-Bangumi shortcut must not be required.
    def search_html(self, keyword):
        searches.append(keyword)
        if keyword != '旧中文片名':
            return []
        return [dict(title=title, url='magnet:?xt=urn:btih:' + str(i) * 40)
                for i, title in enumerate([
                    '[桜都字幕组] 旧中文片名 [09][1080P][简繁内封]',
                    '[桜都字幕组] 无关的别部作品 [09][1080P][简繁内封]',
                    '旧中文片名 [09][1080P][简繁内封]',
                ], 1)]
media = SimpleNamespace(title='新中文片名', original_title='Original title',
                        names=['旧中文片名'], source_meta={},
                        category='日番', original_language='ja', genre_ids=[16])
found = MikanSearchService(AliasClient()).search(SearchQuery(media, MediaType.TV, season=1))
found = SearchHandler._prepare_source_results(
    handler, found, 'mikan', media, MediaType.TV, None, 1, [9], True)
assert searches[:2] == ['新中文片名', '旧中文片名'], searches
assert [row['title'] for row in found] == ['[桜都字幕组] 旧中文片名 [09][1080P][简繁内封]'], found
print('Mikan aliases searched and matched; unrelated titles and unnamed groups rejected')
