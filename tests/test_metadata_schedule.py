"""Scheduled sync must validate metadata without overriding reserved GITHUB_* env."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / '.github/scripts/get_plugin_meta.py'
spec = importlib.util.spec_from_file_location('metadata_schedule', SCRIPT)
metadata = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metadata)


class ScheduleMetadataTests(unittest.TestCase):
    def test_schedule_uses_explicit_manual_validation(self):
        with patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'schedule'}), \
             patch.object(sys, 'argv', [str(SCRIPT), '--manual']), \
             patch.object(metadata, 'manual_plugins', return_value=[{'id': 'fixture'}]) as manual, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            metadata.main()
        manual.assert_called_once()
        self.assertIn('fixture', output.getvalue())

    def test_unknown_trigger_without_explicit_mode_still_fails_closed(self):
        with patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'schedule'}), \
             patch.object(sys, 'argv', [str(SCRIPT)]), self.assertRaises(ValueError):
            metadata.main()
