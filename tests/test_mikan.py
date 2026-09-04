import ast
import importlib.util
from pathlib import Path
import re
import unittest
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
tree = ast.parse((SEARCH / "mikan.py").read_text(encoding="utf-8"))
tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
exec(compile(tree, "mikan.py", "exec"), namespace)


class MikanTests(unittest.TestCase):
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
