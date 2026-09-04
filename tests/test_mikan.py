import ast
import importlib.util
from pathlib import Path
import re
import unittest
from types import MappingProxyType
from urllib.parse import parse_qs, quote, urljoin, urlparse
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
SEARCH = ROOT / "plugins.v2/cloudsubscribe/search"
spec = importlib.util.spec_from_file_location("mikan_matching_test", SEARCH / "matching.py")
matching = importlib.util.module_from_spec(spec)
spec.loader.exec_module(matching)
namespace = dict(re=re, BeautifulSoup=BeautifulSoup, parse_qs=parse_qs, quote=quote,
                 urljoin=urljoin, urlparse=urlparse, title_matches=matching.title_matches,
                 extract_season=matching.extract_season)
fspec=importlib.util.spec_from_file_location('fansubs_for_mikan_test',SEARCH/'fansubs.py')
fansubs=importlib.util.module_from_spec(fspec)
fspec.loader.exec_module(fansubs)
namespace['fansub_priority']=fansubs.fansub_priority
tree = ast.parse((SEARCH / "mikan.py").read_text(encoding="utf-8"))
tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
exec(compile(tree, "mikan.py", "exec"), namespace)


class MikanTests(unittest.TestCase):
    def test_immutable_cloud_file_is_preserved(self):
        spec=importlib.util.spec_from_file_location('file_parser_test',SEARCH.parent/'utils/file_parser.py')
        parser=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(parser)
        item=MappingProxyType({'name':'Example.mkv','is_dir':False})
        self.assertIs(list(parser.MediaFileParser.iter_files([item]))[0],item)
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
