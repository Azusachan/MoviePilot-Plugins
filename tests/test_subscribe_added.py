"""Test the real event methods without starting MoviePilot or making downloads."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
tree = ast.parse((ROOT / 'plugins.v2/cloudsubscribe/core/hook/events.py').read_text(encoding='utf-8'))
handler = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'PluginEventHandler')
handler.bases = []
handler.body = [n for n in handler.body if isinstance(n, ast.FunctionDef)
                and n.name in {'on_subscribe_added', '_get_subscribe_id_from_event'}]
namespace = {'Event': object, 'Optional': __import__('typing').Optional, 'logger': Mock()}
exec(compile(ast.Module(body=[handler], type_ignores=[]), 'events.py', 'exec'), namespace)


class SubscribeAddedTests(unittest.TestCase):
    def setUp(self):
        self.owner = namespace['PluginEventHandler']()
        self.owner._enabled = True
        self.owner._takeover_new_subscribes = True
        self.owner._is_subscribe_excluded = Mock(return_value=False)
        self.owner.queue_subscribe_search = Mock(return_value=True)

    def send(self, data):
        self.owner.on_subscribe_added(SimpleNamespace(event_data=data))

    def test_movie_and_tv_use_single_subscription_queue(self):
        for sid in (1, 2):
            self.send({'subscribe_id': sid})
            self.owner.queue_subscribe_search.assert_called_with(subscribe_id=sid, subscribe_state='N')

    def test_disabled_or_takeover_off_never_queue(self):
        for enabled, takeover in ((False, True), (True, False), (False, False)):
            self.owner._enabled, self.owner._takeover_new_subscribes = enabled, takeover
            self.send({'subscribe_id': 2})
        self.owner.queue_subscribe_search.assert_not_called()

    def test_excluded_subscription_never_queues(self):
        self.owner._is_subscribe_excluded.return_value = True
        self.send({'subscribe_id': 2})
        self.owner.queue_subscribe_search.assert_not_called()

    def test_invalid_id_never_becomes_all_subscriptions(self):
        for data in ({}, {'id': 0}, {'id': -1}, {'id': 'bad'}):
            self.send(data)
        self.owner.on_subscribe_added(None)
        self.owner.queue_subscribe_search.assert_not_called()

    def test_supported_event_payload_shapes(self):
        for data in ({'id': '2'}, {'subscribe': {'id': 2}}):
            self.send(data)
            self.owner.queue_subscribe_search.assert_called_with(subscribe_id=2, subscribe_state='N')

    def test_queue_shutdown_does_not_fall_back_to_direct_download(self):
        self.owner.queue_subscribe_search.return_value = False
        self.send({'subscribe_id': 2})
        self.owner.queue_subscribe_search.assert_called_once_with(subscribe_id=2, subscribe_state='N')
