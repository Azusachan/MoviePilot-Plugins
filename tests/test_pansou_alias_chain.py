"""Offline alias-chain contracts.

Fixtures are synthetic, not claims about live metadata or resource availability.
Only the production service class is loaded; no app startup or cloud clients.
"""
import ast
import importlib.util
from pathlib import Path
import re
from types import SimpleNamespace
from typing import Any, Dict, List
import unicodedata
import unittest
from unittest.mock import Mock


SOURCE = Path(__file__).resolve().parents[1] / 'plugins.v2/cloudsubscribefork/search/pansou/service.py'
spec = importlib.util.spec_from_file_location('pansou_alias_helpers', SOURCE.parent.parent / 'mikan/titles.py')
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
service_class = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'PanSouSearchService')
media_type = SimpleNamespace(TV='tv', MOVIE='movie')
scope = dict(re=re, unicodedata=unicodedata, Any=Any, Dict=Dict, List=List,
             OwnerDelegator=object, MediaInfo=object, SearchQuery=object,
             MediaType=media_type, logger=Mock(),
             normalize_season=lambda value: 1 if value is None else int(value),
             format_search_log_prefix=lambda *args: 'alias-fixture',
             normalize_resource_type=lambda value: value,
             resource_type_name=lambda value, default: value,
             PANSOU_RESOURCE_TYPES=['115', 'magnet', 'ed2k'],
             normalize_magnets=lambda rows, source: rows,
             metadata_aliases=helpers.metadata_aliases, unique_titles=helpers.unique_titles)
exec(compile(ast.Module(body=[service_class], type_ignores=[]), str(SOURCE), 'exec'), scope)
Service = scope['PanSouSearchService']


def row(title, kind='tv series', url='ed2k://fixture'):
    return dict(title=title, tags=[kind], links=[dict(type='ed2k', url=url)])


class PanSouAliasChainTests(unittest.TestCase):
    def setUp(self):
        self.media = SimpleNamespace(title='不毛地带', original_title='不毛地帯',
                                     year='2009', names=['Fumo Chitai', 'The Waste Land'],
                                     en_title='The Waste Land')
        self.service = Service()
        self.service.__dict__.update(
            _pansou_client=Mock(), _pansou_result_limit=20,
            _resource_type_order_config=['115', 'ed2k', 'magnet'],
            _cloud_drive_key='115', _cloud_drive_resource_types={'115', 'ed2k', 'magnet'},
            _pansou_channels=[], _pansou_plugins=[], _pansou_filter={},
            _pansou_refresh=False, _pansou_concurrency=2)
        self.query = SimpleNamespace(mediainfo=self.media, media_type=media_type.TV,
                                     season=1, subscribe=object(),
                                     resource_list_mode=False, result_limit=None)

    def respond(self, keyword, **kwargs):
        # Nonempty Chinese results must not prevent trying a useful alias.
        rows = [row('Other Show 2009')] if keyword == '不毛地带' else []
        if keyword in self.media.names:
            rows = [row('Fumo Chitai 2009 S01E01')]
        return dict(results=rows, raw_count=len(rows))

    def test_metadata_aliases_reach_matching_allowlist(self):
        titles = Service._media_titles(self.media)
        self.assertIn('Fumo Chitai', titles)
        self.assertIn('The Waste Land', titles)

    def test_unrelated_chinese_results_fall_back_to_alias_and_survive_matching(self):
        self.service._pansou_client.request_search.side_effect = self.respond
        results = self.service.search(self.query)
        keywords = [c.kwargs['keyword'] for c in self.service._pansou_client.request_search.call_args_list]
        self.assertTrue(set(keywords) & set(self.media.names), keywords)
        self.assertEqual([r['title'] for r in results], ['Fumo Chitai 2009 S01E01'])
        self.assertEqual(len({r['url'] for r in results}), len(results))
        self.assertLessEqual(len(keywords), 6)
        self.assertEqual(self.media.title, '不毛地带')

    def test_explicit_alias_can_match_ed2k_and_magnet(self):
        for resource_type in ('ed2k', 'magnet'):
            candidate = row('Fumo.Chitai.2009.S01E01')
            candidate['links'][0]['type'] = resource_type
            groups = Service._normalize_results([candidate], '不毛地带',
                ['不毛地带', '不毛地帯', 'Fumo Chitai'], '2009', [resource_type], 20)
            self.assertEqual(len(groups[resource_type]), 1)

    def test_failed_keyword_does_not_block_aliases(self):
        def respond(keyword, **kwargs):
            if keyword == self.media.title:
                return {'error': 'fixture timeout'}
            return self.respond(keyword, **kwargs)
        self.service._pansou_client.request_search.side_effect = respond
        self.assertEqual(len(self.service.search(self.query)), 1)

    def test_keywords_bounded_deduplicated_and_metadata_preserved(self):
        self.media.names = ['Fumo Chitai', ' fumo chitai ', None, {}, *['Alias ' + str(i) for i in range(20)]]
        before = list(self.media.names)
        self.service._pansou_client.request_search.return_value = {'results': []}
        self.assertEqual(self.service.search(self.query), [])
        calls = self.service._pansou_client.request_search.call_args_list
        keywords = [c.kwargs['keyword'] for c in calls]
        self.assertEqual(len(keywords), 6)
        self.assertEqual(len({k.casefold() for k in keywords}), 6)
        self.assertEqual(self.media.names, before)
        for call in calls:
            self.assertEqual(call.kwargs['cloud_types'], ['115', 'ed2k', 'magnet'])

    def test_later_season_year_is_not_compared_to_debut(self):
        self.query.season = 2
        self.service._pansou_client.request_search.return_value = dict(
            results=[row('不毛地带 2010 S02E01')], raw_count=1)
        self.assertEqual(len(self.service.search(self.query)), 1)

    def test_unrelated_results_are_rejected_even_with_aliases(self):
        self.assertEqual(Service._normalize_results([row('Other Show 2009')],
            '不毛地带', ['不毛地带', 'Fumo Chitai'], '2009', ['ed2k'], 20), {})

    def test_movie_tag_is_rejected_for_tv(self):
        self.assertFalse(Service._media_type_matches({'tags': ['movie']}, media_type.TV))

    def test_explicit_wrong_year_without_tags_is_not_accepted_as_tv(self):
        # An untagged same-name film must not leak through first-season matching.
        self.service._pansou_client.request_search.return_value = dict(
            results=[row('不毛地带 1976', kind='')], raw_count=1)
        self.assertEqual(self.service.search(self.query), [])


if __name__ == '__main__':
    unittest.main()
