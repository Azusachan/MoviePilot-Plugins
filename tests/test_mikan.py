import ast
import importlib.util
from pathlib import Path
import re
import unittest
from types import MappingProxyType
from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import parse_qs, quote, urljoin, urlparse
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
SEARCH = ROOT / "plugins.v2/cloudsubscribefork/search"
spec = importlib.util.spec_from_file_location("mikan_matching_test", SEARCH / "matching.py")
matching = importlib.util.module_from_spec(spec)
spec.loader.exec_module(matching)
namespace = dict(re=re, BeautifulSoup=BeautifulSoup, parse_qs=parse_qs, quote=quote,
                 urljoin=urljoin, urlparse=urlparse, title_matches=matching.title_matches,
                 extract_season=matching.extract_season)
fspec=importlib.util.spec_from_file_location('fansubs_for_mikan_test',SEARCH/'fansubs.py')
fansubs=importlib.util.module_from_spec(fspec)
fspec.loader.exec_module(fansubs)
namespace.update(Any=Any, Dict=Dict, Iterable=Iterable, List=List, Optional=Optional,
                 title_without_season=matching.title_without_season,
                 subtitle_policy_priority=fansubs.fansub_priority)
tree = ast.parse((SEARCH / "subs_filter.py").read_text(encoding="utf-8"))
tree.body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
exec(compile(tree, "subs_filter.py", "exec"), namespace)
namespace['mikan_file_candidates'] = namespace['anime_file_candidates']
# Test the native parser without constructing a network client.
tree = ast.parse((SEARCH / 'mikan/client.py').read_text(encoding='utf-8'))
client = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'MikanClient')
method = next(node for node in client.body if isinstance(node, ast.FunctionDef) and node.name == 'parse_rows')
namespace.update(parse_size_str=lambda value: 0, MikanClientError=RuntimeError)
exec(compile(ast.Module(body=[method], type_ignores=[]), 'mikan/client.py', 'exec'), namespace)
native_parse_rows = namespace['parse_rows']
namespace['parse_rows'] = lambda html, base_url: native_parse_rows(SimpleNamespace(base_url=base_url), html)


class MikanTests(unittest.TestCase):
    def test_immutable_cloud_file_is_preserved(self):
        spec=importlib.util.spec_from_file_location('file_parser_test',SEARCH.parent/'utils/file_parser.py')
        parser=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(parser)
        item=MappingProxyType({'name':'Example.mkv','is_dir':False})
        parsed = list(parser.MediaFileParser.iter_files([item]))[0]
        self.assertEqual(parsed['name'], item['name'])
        self.assertNotIn('_relative_path', item)
        self.assertEqual(parsed['_relative_path'], 'Example.mkv')
    def test_real_file_bilingual_identity_and_episode(self):
        release='[桜都字幕组] 示例 / Example [08][简繁内封]'
        good={'name':'[Sakurato] Example [08][1080p][CHS&CHT].mkv'}
        rows=[good,{'name':'[Sakurato] Other [08][CHS].mkv'},
              {'name':'[Sakurato] Example [07][CHS].mkv'},
              {'name':'[Sakurato] Example [08][无字幕].mkv'}]
        result=namespace['mikan_file_candidates'](rows,release,1,[8])
        self.assertEqual(result,{8:[good]})
        self.assertIs(result[8][0],good)
        self.assertEqual(namespace['mikan_file_candidates'](rows,release,2,[8]),{8:[]})
    def test_anime_episode_brackets(self):
        parse = namespace['release_episodes']
        self.assertEqual(parse('[桜都字幕组] Example [08][1080P][简繁内封]'), [8])
        self.assertEqual(parse('[Group] Example [01-03][2026][1080]'), [1,2,3])
        self.assertEqual(parse('[Group] Example - 08v2 [1080p]'), [8])
        self.assertEqual(parse('[Group] Example [1080][2026]'), [])

    def test_magnet_extraction_and_duplicate_hash(self):
        row = '<tr><td><a href="/Home/Episode/abc">[Group] Example [08]</a></td><td><a href="magnet:?xt=urn:btih:' + 'a' * 40 + '&amp;tr=https://tracker.example">magnet</a></td></tr>'
        result = namespace["parse_rows"]('<table>' + row * 2 + '</table>', 'https://mikanani.me')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["source_url"], 'https://mikanani.me/Home/Episode/abc')
        self.assertIn('dn=', result[0]["url"])

    def test_invalid_magnet_rejected(self):
        html = '<tr><td><a href="/Home/Episode/x">Example</a><a href="magnet:?xt=bad">M</a></td></tr>'
        self.assertEqual(namespace["parse_rows"](html, 'https://mikanani.me'), [])

    def test_current_mikan_clipboard_attribute(self):
        html = '<tr><td><a href="/Home/Episode/x">Example [08]</a><a data-clipboard-text="magnet:?xt=urn:btih:' + 'b' * 40 + '">copy</a></td></tr>'
        self.assertEqual(len(namespace["parse_rows"](html, 'https://mikanani.me')), 1)

    def test_multilingual_release_match(self):
        match = namespace["release_matches"]
        self.assertTrue(match('[桜都字幕组] 在超市后门吸烟的二人 / Super no Ura de Yani Suu Futari [08][1080P]', ['在超市后门吸烟的二人'], 1))
        self.assertTrue(match('[LoliHouse] Example / Other - 08 [WebRip]', ['Example'], 1))
        self.assertFalse(match('[Group] Example Extra [08]', ['Example'], 1))
        self.assertFalse(match('[Group] Example S02 - 08', ['Example'], 1))
        self.assertFalse(match('[Group] Example - 08', ['Example'], 2))


if __name__ == '__main__':
    unittest.main()
