import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('version_conflicts', Path(__file__).resolve().parents[1] / '.github/scripts/resolve_version_conflicts.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class VersionConflictTests(unittest.TestCase):
    def conflict(self, a, b):
        return f'<<<<<<< HEAD\n{a}\n=======\n{b}\n>>>>>>> upstream\n'

    def test_only_version(self):
        text = self.conflict('    plugin_version = "1.3.5.9"', '    plugin_version = "1.3.7"')
        self.assertEqual(module.resolve(text, 'plugins.v2/cloudsubscribefork/__init__.py'), '    plugin_version = "1.3.5.9"\n')

    def test_json_version(self):
        text = self.conflict('    "version": "1.3.5.9",', '    "version": "1.3.7",')
        self.assertNotIn('<<<<<<<', module.resolve(text, 'package.v2.json'))

    def test_business_logic_fails_closed(self):
        text = self.conflict('    plugin_version = "1.3.5.9"\n    enabled = True', '    plugin_version = "1.3.7"')
        with self.assertRaises(ValueError):
            module.resolve(text, 'plugins.v2/cloudsubscribefork/__init__.py')
        with self.assertRaises(ValueError):
            module.resolve(text, 'other.py')
