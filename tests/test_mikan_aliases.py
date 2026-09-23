import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

path = Path(__file__).resolve().parents[1] / 'plugins.v2/cloudsubscribefork/search/mikan/titles.py'
spec = importlib.util.spec_from_file_location('mikan_titles', path)
titles = importlib.util.module_from_spec(spec)
spec.loader.exec_module(titles)


class AliasTests(unittest.TestCase):
    def test_old_translation_is_searched_early(self):
        media = SimpleNamespace(names=['Portuguese name', '旧中文片名', '新中文片名', 'English name'])
        aliases = titles.metadata_aliases(media)
        keys = titles.search_keywords(['新中文片名', '原題', 'English name'], aliases)
        self.assertEqual(keys[:2], ['新中文片名', '旧中文片名'])
        self.assertEqual(keys.count('新中文片名'), 1)

    def test_invalid_aliases_are_not_stringified(self):
        self.assertEqual(titles.metadata_aliases(SimpleNamespace(names='not a list')), [])
        media = SimpleNamespace(names=[None, {}, '  Old title ', 'old TITLE', 'x' * 201])
        self.assertEqual(titles.metadata_aliases(media), ['Old title'])

    def test_requests_are_bounded_and_metadata_unchanged(self):
        names = ['别名' + str(i) for i in range(20)]
        media = SimpleNamespace(names=names)
        self.assertEqual(len(titles.search_keywords(['Title'], titles.metadata_aliases(media))), 6)
        self.assertEqual(media.names, names)

    def test_does_not_learn_aliases_from_results(self):
        self.assertEqual(titles.metadata_aliases(SimpleNamespace(title='Other show')), [])
