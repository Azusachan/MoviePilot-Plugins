"""Compatibility entry point: Plex now uses the native upstream resolver."""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).with_name('validate_fork.py')), run_name='__main__')
