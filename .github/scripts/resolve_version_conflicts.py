"""Resolve only numeric version assignments; never resolve business logic."""
import re
import subprocess
from pathlib import Path

PATTERN = re.compile(r'^<<<<<<<[^\n]*\n(.*?)^=======\n(.*?)^>>>>>>>[^\n]*(?:\n|$)', re.M | re.S)
ALLOWED = {'package.v2.json', 'plugins.v2/cloudsubscribefork/__init__.py'}


def resolve(text, path):
    rule = (r'\s*"version": "\d+(?:\.\d+)+",\s*' if path == 'package.v2.json'
            else r'\s*plugin_version = "\d+(?:\.\d+)+"\s*')
    matches = list(PATTERN.finditer(text))
    if path not in ALLOWED or not matches:
        raise ValueError('Not a recognized version conflict')
    for match in matches:
        if not all(re.fullmatch(rule, part) for part in match.groups()):
            raise ValueError('Non-version conflict requires review')
    return PATTERN.sub(lambda m: m.group(1), text)


def main():
    paths = subprocess.check_output(['git', 'diff', '--name-only', '--diff-filter=U'], text=True).splitlines()
    if not paths or not set(paths) <= ALLOWED:
        raise SystemExit('Non-version merge conflicts require review')
    changes = {path: resolve(Path(path).read_text(encoding='utf-8'), path) for path in paths}
    for path, text in changes.items():
        Path(path).write_text(text, encoding='utf-8')
    subprocess.run(['git', 'add', '--', *paths], check=True)


if __name__ == '__main__':
    main()
