"""Fail closed on identity drift, stale adapters, and broken relative imports."""
import ast
import json
import re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / 'plugins.v2/cloudsubscribefork'
assert 'CloudSubscribeFork' in json.loads((ROOT / 'package.v2.json').read_text(encoding='utf-8'))
assert not (PLUGIN / 'search/mikan.py').exists(), 'Legacy Mikan module shadows native package'
for path in PLUGIN.rglob('*.py'):
    source = path.read_text(encoding='utf-8')
    assert not re.search(r'CloudSubscribe(?!Fork)|cloudsubscribe(?!fork)', source), path
    tree = ast.parse(source, filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.level or not node.module:
            continue
        base = path.parent
        for _ in range(node.level - 1):
            base = base.parent
        target = base.joinpath(*node.module.split('.'))
        assert target.with_suffix('.py').is_file() or (target / '__init__.py').is_file(), (path, node.module)
print('Fork identity and relative imports validated')
