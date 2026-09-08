"""Exercise the real merge script against disposable local Git repositories."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / '.github/scripts/prepare-upstream-pr.sh'


@unittest.skipUnless(shutil.which('bash') and shutil.which('git'), 'requires bash/git')
class UpstreamMergeTests(unittest.TestCase):
    def test_no_change(self):
        self.exercise('unchanged')

    def test_clean_merge_preserves_both_histories(self):
        self.exercise('clean')

    def test_conflict_leaves_upstream_pr_branch_and_main_untouched(self):
        self.exercise('conflict')

    def test_workflow_permission_failure_leaves_visible_pr(self):
        self.exercise('workflow')

    def exercise(self, mode):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            repo = root / 'work'
            repo.mkdir()
            (repo / '.github').mkdir()
            (repo / '.github/fixture').write_text('fixture\n')
            def git(*args, cwd=repo):
                return subprocess.check_output(['git', *args], cwd=cwd, text=True,
                                               stderr=subprocess.PIPE).strip()
            git('init', '-b', 'main')
            git('config', 'user.name', 'Test')
            git('config', 'user.email', 'test@example.invalid')
            (repo / 'shared').write_text('base\n')
            git('add', '.')
            git('commit', '-m', 'base')
            base = git('rev-parse', 'HEAD')
            git('init', '--bare', str(root / 'origin.git'))
            git('init', '--bare', str(root / 'upstream.git'))
            git('remote', 'add', 'origin', str(root / 'origin.git'))
            git('remote', 'add', 'upstream', str(root / 'upstream.git'))
            (repo / ('shared' if mode == 'conflict' else 'fork')).write_text('fork\n')
            git('add', '.')
            git('commit', '-m', 'fork')
            fork = git('rev-parse', 'HEAD')
            git('push', 'origin', 'main')
            git('switch', '-c', 'upstream-work', base)
            if mode != 'unchanged':
                (repo / ('shared' if mode == 'conflict' else 'upstream')).write_text('upstream\n')
                if mode == 'workflow':
                    (repo / '.github/workflows').mkdir(parents=True, exist_ok=True)
                    (repo / '.github/workflows/new.yml').write_text('name: upstream\n')
                git('add', '.')
                git('commit', '-m', 'upstream')
            upstream = git('rev-parse', 'HEAD')
            git('push', 'upstream', 'HEAD:main')
            git('switch', 'main')
            binpath = root / 'bin'
            binpath.mkdir()
            gh = binpath / 'gh'
            gh.write_text('#!/usr/bin/env bash\n'
                          'echo "$*" >> "$TEST_GH_LOG"\n'
                          'if [[ "$1 $2" == "pr create" ]]; then\n'
                          ' echo https://github.com/example/fork/pull/1\nfi\n')
            gh.chmod(0o755)
            env = dict(os.environ, PATH=str(binpath) + os.pathsep + os.environ['PATH'],
                       GITHUB_OUTPUT=str(root / 'output'), GITHUB_ENV=str(root / 'env'),
                       GH_REPO='example/fork', RUN_URL='https://example.invalid/run',
                       TEST_GH_LOG=str(root / 'gh.log'), GIT_TERMINAL_PROMPT='0')
            result = subprocess.run(['bash'], input=SCRIPT.read_text(encoding='utf-8'),
                                    cwd=repo, env=env, text=True, capture_output=True)
            self.assertEqual(git('rev-parse', 'refs/heads/main', cwd=root / 'origin.git'), fork)
            if mode == 'unchanged':
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('changed=false', (root / 'output').read_text())
                self.assertNotIn('pr create', (root / 'gh.log').read_text())
                return
            branch = 'codex/sync-upstream-' + upstream
            published = git('rev-parse', 'refs/heads/' + branch, cwd=root / 'origin.git')
            self.assertIn('pr create', (root / 'gh.log').read_text())
            if mode in {'conflict', 'workflow'}:
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(git('merge-base', published, fork), fork)
                self.assertNotEqual(published, upstream)
                self.assertIn('pr comment', (root / 'gh.log').read_text())
                self.assertFalse((repo / '.git/MERGE_HEAD').exists())
                if mode == 'workflow':
                    self.assertIn('workflows permission', (root / 'gh.log').read_text())
            else:
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(git('merge-base', published, fork), fork)
                self.assertEqual(git('merge-base', published, upstream), upstream)
                self.assertEqual(len(git('show', '-s', '--format=%P', published).split()), 2)


if __name__ == '__main__':
    unittest.main()
