import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location('fansubs_test', Path(__file__).resolve().parents[1] / 'plugins.v2/cloudsubscribe/search/fansubs.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class FansubTests(unittest.TestCase):
    def test_reject_no_group_raw_or_encoding_only(self):
        for title in ('Example [简体内嵌]', '[LoliHouse] Example [无字幕]',
                      '[Nix-Raws] Example [简繁内封]', '[桜都字幕组] Example [无字幕][简体]',
                      '[SweetSub] Example [English]', '[1080p] Example [CHS]'):
            self.assertIsNone(policy.fansub_priority(title), title)

    def test_translation_collaboration_and_language(self):
        self.assertEqual(policy.fansub_priority('[喵萌奶茶屋&LoliHouse] Example [CHS&CHT]'),400)
        self.assertEqual(policy.fansub_priority('【桜都字幕组】Example [简体内嵌]'),200)
        self.assertEqual(policy.fansub_priority('[某某字幕组] Example [繁體內嵌]'),100)

    def test_stable_tiers_and_no_mutation(self):
        rows = [{'title': t} for t in ['[桜都字幕组] X [CHS]', '[千夏字幕组] X [繁體]', '[SweetSub] X [CHS]', 'X [CHS]']]
        result = policy.filter_fansubs(rows)
        self.assertEqual([r['fansub_priority'] for r in result],[400,400,200])
        self.assertNotIn('fansub_priority',rows[0])

    def test_only_japanese_animation(self):
        self.assertTrue(policy.is_japanese_anime(SimpleNamespace(original_language='ja',genre_ids=[16])))
        self.assertTrue(policy.is_japanese_anime(SimpleNamespace(category='动画/日番')))
        self.assertFalse(policy.is_japanese_anime(SimpleNamespace(original_language='en',genre_ids=[16])))
        self.assertFalse(policy.is_japanese_anime(SimpleNamespace(original_language='ja',genre_ids=[18])))
