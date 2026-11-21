"""A Git merge strategy comparing upstream snapshots in the installed plugin namespace."""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


ROOTS = (b"plugins.v2/cloudsubscribe/", b"frontend/cloudsubscribe/")
SOURCE_EXTENSIONS = (b".py", b".js", b".vue", b".json", b".html", b".ts")
IDENTITY = re.compile(rb"CloudSubscribe(?!Fork)|cloudsubscribe(?!fork)")


def git(*args, data=None, env=None):
    return subprocess.check_output(["git", *args], input=data, env=env)


def project(commit, cache):
    entries = []
    seen = set()
    sources = {}
    for record in git("ls-tree", "-rz", commit).split(b"\0"):
        if not record:
            continue
        meta, path = record.split(b"\t", 1)
        mode, kind, oid = meta.split()
        mapped = path
        for root in ROOTS:
            if path.startswith(root):
                mapped = root[:-1] + b"fork/" + path[len(root):]
                break
        if mapped in seen:
            raise ValueError(f"Upstream paths collide at {mapped!r}")
        seen.add(mapped)
        source = ((mapped != path or path.startswith(b"tests/")) and path.endswith(SOURCE_EXTENSIONS)
                  or path == b"package.v2.json")
        if source and mode in (b"100644", b"100755") and oid not in cache:
            sources[oid] = None
        entries.append((mode, oid, mapped, source))

    # Batch reads keep the two projections inexpensive, including on Windows.
    batch = git("cat-file", "--batch", data=b"".join(oid + b"\n" for oid in sources))
    offset = 0
    for oid in sources:
        header_end = batch.index(b"\n", offset)
        object_id, kind, size = batch[offset:header_end].split()
        if object_id != oid or kind != b"blob":
            raise ValueError("Unexpected object in upstream tree")
        start = header_end + 1
        content = batch[start:start + int(size)]
        offset = start + len(content) + 1
        updated = IDENTITY.sub(lambda m: m[0] + (b"Fork" if m[0][0:1] == b"C" else b"fork"), content)
        cache[oid] = oid if updated == content else git("hash-object", "-w", "--stdin", data=updated).strip()

    with tempfile.TemporaryDirectory() as temp:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(temp) / "index"))
        records = b"".join(mode + b" " + (cache.get(oid, oid) if source and mode in (b"100644", b"100755") else oid)
                           + b"\t" + path + b"\0" for mode, oid, path, source in entries)
        git("update-index", "-z", "--index-info", data=records, env=env)
        tree = git("write-tree", env=env).strip().decode()
    return git("commit-tree", tree, "-m", f"Temporary fork namespace view of {commit}").strip().decode()


def main(args):
    if len(args) != 4 or args[1] != "--":
        raise SystemExit("Expected exactly one merge base and one upstream head")
    base, _, ours, theirs = args
    marker = git("show", f"{ours}:.github/UPSTREAM_COMMIT").decode().strip()
    if base != marker:
        raise SystemExit("Upstream merge base differs from the last validated upstream commit")
    cache = {}
    # Git writes the ordinary merge index (including conflict stages). The outer
    # git merge records the actual upstream SHA as parent, never these scratch commits.
    return subprocess.call(["git", "merge-recursive", project(base, cache), "--", ours, project(theirs, cache)])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
