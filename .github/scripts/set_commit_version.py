#!/usr/bin/env python3
"""Derive the fork release version from the upstream version and commit."""

import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "package.v2.json"
PLUGIN = ROOT / "plugins.v2/cloudsubscribe/__init__.py"
MARKER = ROOT / ".github/UPSTREAM_COMMIT"


def upstream_package(commit: str) -> dict:
    raw = subprocess.check_output(
        ["git", "show", f"{commit}:package.v2.json"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    )
    return json.loads(raw)


def main() -> None:
    if len(sys.argv) not in {2, 4} or not re.fullmatch(r"[0-9a-fA-F]{40}", sys.argv[1]):
        raise SystemExit(
            "usage: set_commit_version.py <40-character-upstream-commit> "
            "[upstream-version commit-count]"
        )
    commit = sys.argv[1].lower()
    base = (
        sys.argv[2]
        if len(sys.argv) == 4
        else str(upstream_package(commit)["CloudSubscribe"]["version"])
    )
    commit_count = (
        int(sys.argv[3])
        if len(sys.argv) == 4
        else int(
            subprocess.check_output(
                ["git", "rev-list", "--count", commit],
                cwd=ROOT,
                text=True,
                encoding="utf-8",
            ).strip()
        )
    )
    # MoviePilot compares dot-separated numeric components. A PEP 440 local
    # version such as +plex.<sha> would be treated as older than upstream.
    # Last component tracks fork features without changing the upstream marker.
    version = f"{base}.{commit_count}.{int(commit[:8], 16)}.7"

    package = json.loads(PACKAGE.read_text(encoding="utf-8"))
    info = package["CloudSubscribe"]
    info["version"] = version
    history = info.setdefault("history", {})
    history[f"v{version}"] = (
        f"Plex compatibility build based on upstream {commit[:12]}"
    )
    PACKAGE.write_text(
        json.dumps(package, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    source = PLUGIN.read_text(encoding="utf-8")
    source, count = re.subn(
        r'(^\s*plugin_version\s*=\s*)"[^"]+"',
        rf'\g<1>"{version}"',
        source,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise SystemExit("plugin_version assignment not found")
    PLUGIN.write_text(source, encoding="utf-8")
    MARKER.write_text(commit + "\n", encoding="ascii")
    print(version)


if __name__ == "__main__":
    main()
