#!/usr/bin/env bash
# Open a visible PR BEFORE attempting a merge. Never rewrite published history.
set -euo pipefail
git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git remote add upstream https://github.com/odomu/MoviePilot-Plugins.git || true
git fetch upstream main
git fetch origin main
base="$(git rev-parse origin/main)"
# Resume the oldest unresolved sync instead of opening daily duplicate PRs.
pending="$(gh pr list --base main --state open --limit 100 --json number,headRefName \
  --jq '[.[] | select(.headRefName | startswith("codex/sync-upstream-"))] | sort_by(.number) | .[0] // empty')"
if [ -n "$pending" ]; then
  branch="$(jq -r .headRefName <<<"$pending")"
  pr="$(jq -r .number <<<"$pending")"
  upstream_sha="${branch#codex/sync-upstream-}"
  [[ "$upstream_sha" =~ ^[0-9a-f]{40}$ ]]
  git fetch origin "refs/heads/$branch"
  git switch -c "$branch" FETCH_HEAD
else
  upstream_sha="$(git rev-parse upstream/main)"
  if git merge-base --is-ancestor "$upstream_sha" origin/main; then
    echo 'changed=false' >> "$GITHUB_OUTPUT"
    echo 'Upstream already merged; nothing to do.'
    exit 0
  fi
  branch="codex/sync-upstream-$upstream_sha"
  # Start from the fork, not raw upstream: GITHUB_TOKEN cannot push a branch
  # whose workflow files differ from the fork without workflows permission.
  # A visible target marker lets us open the PR before attempting the merge.
  if git ls-remote --exit-code --heads origin "$branch" >/dev/null; then
    git fetch origin "refs/heads/$branch"
    git switch -c "$branch" FETCH_HEAD
  else
    git switch -c "$branch" "$base"
    printf '%s\n' "$upstream_sha" > .github/UPSTREAM_TARGET
    git add .github/UPSTREAM_TARGET
    git commit -m "sync: propose upstream ${upstream_sha:0:12}"
    git push origin "HEAD:refs/heads/$branch"
  fi
  pr="$(gh pr create --base main --head "$branch" \
    --title "sync: merge upstream ${upstream_sha:0:12}" \
    --body "Merge upstream commit $upstream_sha while retaining fork history. No rebase, tree replacement, force push or automatic conflict resolution. Validation and merge run: $RUN_URL")"
  pr="${pr##*/}"
fi
{
  echo "PR_NUMBER=$pr"
  echo "SYNC_BRANCH=$branch"
  echo "UPSTREAM_SHA=$upstream_sha"
  echo "BASE_SHA=$base"
} >> "$GITHUB_ENV"
echo 'changed=true' >> "$GITHUB_OUTPUT"
gh api "repos/$GH_REPO/statuses/$(git rev-parse HEAD)" \
  -f state=pending -f context=upstream-sync/validation \
  -f target_url="$RUN_URL" -f description='Checking merge conflicts and fork compatibility'
published="$(git rev-parse HEAD)"
for target in "$base" "$upstream_sha"; do
  if ! git merge --no-ff --no-edit "$target"; then
    conflicts="$(git diff --name-only --diff-filter=U)"
    git merge --abort
    gh pr comment "$pr" --body "Upstream merge blocked by conflicts in:

$conflicts

Resolve by merging upstream commit $upstream_sha and current main into this PR branch, then rerun. No conflict-marker commit or automatic resolution was pushed. Run: $RUN_URL"
    exit 1
  fi
done
# Workflow changes need a separately authorized human/App push. Keep the PR
# visible and fail instead of silently dropping upstream workflow edits.
if ! git diff --quiet "$published" HEAD -- .github/workflows; then
  gh pr comment "$pr" --body "The merge changes GitHub workflow files. GITHUB_TOKEN lacks workflows permission; push the reviewed merge with an authorized account, then rerun. Run: $RUN_URL"
  exit 1
fi
git push origin "HEAD:refs/heads/$branch"
