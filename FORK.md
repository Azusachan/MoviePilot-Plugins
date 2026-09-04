# CloudSubscribe Plex compatibility fork

This fork tracks `odomu/MoviePilot-Plugins` and publishes CloudSubscribe builds
that use MoviePilot's generic media-server API when calculating existing TV
episodes. This removes the upstream Emby-only gate while preserving the
Emby-specific path and media-stream logic used elsewhere.

## Versioning

Published versions use:

`<upstream-version>.<upstream-commit-count>.<short-commit-as-decimal>.<fork-revision>`

Only numeric components are used because MoviePilot's version comparator treats
unknown text components as older than a normal release. The full commit remains
available in `.github/UPSTREAM_COMMIT` and in each release note.

`.github/UPSTREAM_COMMIT` records the exact upstream source commit.

## Automated updates

`sync-upstream.yml` checks upstream daily and can also be run manually. It:

1. Creates a `codex/sync-upstream-<full-SHA>` branch from upstream and opens a PR
   against fork `main` **before** attempting the merge.
2. Merges fork `main` into that branch using `git merge --no-ff`. Conflicts are
   never auto-resolved: the merge is aborted and the PR stays visibly conflicting.
3. Checks the fail-closed Plex/Mikan integration and derives a commit-based version.
4. Runs backend tests, compilation, and a frontend build, publishing the
   `upstream-sync/validation` commit status and failure comments on the PR.
5. After successful validation, merges the exact tested PR head using a merge
   commit, then explicitly dispatches `plugins-release.yml` for CloudSubscribe.

No rebase, tree replacement, force push, or direct push to `main` is used.
An existing unresolved sync PR is resumed rather than creating daily duplicates.
If `main` advances during tests, the run stops and must be rerun to merge/retest.
Resolve conflicts or failed integration on the PR branch, push normally, and rerun
the sync workflow; blocked PRs are never silently discarded. A closed unmerged PR
may be proposed again if its upstream commit remains unmerged.

GitHub Actions must be allowed to create PRs in repository Actions settings.
The workflow explicitly records validation status and dispatches release; it does
not rely on `GITHUB_TOKEN` PR/push events automatically triggering other workflows.
The release workflow builds assets after merging; failed releases remain visible
as failed Actions runs and can be retried manually. Patch scripts remain
compatibility assertions, not a mechanism to overwrite conflicts.
# Mikan search

The fork includes a public Mikan search provider, defaulting to https://mikanani.me.
Enable `mikan` in search source order and `magnet` in resource types. It searches
up to three title aliases, matches release titles, deduplicates info hashes,
and reuses the existing subscription filtering and 115 offline pipeline.
The configurable URL, request interval, timeout and result limit are exposed in
the Mikan settings tab. No Mikan account is required. Later seasons without an
explicit season marker are conservatively rejected; full absolute-number mapping
and per-show RSS/subgroup pinning are not implemented yet.

Fork revision `.1` adds Mikan. Normal merges preserve fork changes and history.
Integration scripts check exact markers; a conflict stops the PR for review.
# Personal anime subtitle policy (fork revision 2)

Fork revision 3 supplies explicit season/episode fields for Mikan `[08]`,
`[01-03]`, and ` - 08v2` titles. Resolution and year tags are not episode numbers.
This avoids unnecessary remote torrent metadata lookups during offline submission.

Fork revision 4 reserves pending Magnet episodes per subscription/season, avoiding
simultaneous downloads of simplified/traditional/embedded variants of one episode.
Reservations disappear with the pending task; failures can be retried later.

Fork revision 5 preserves immutable CloudFile objects during file-tree traversal.
Mikan finalization validates actual filenames against the bilingual aliases in the
already-matched release, explicit episode number, season and Chinese fansub tags.
Other sources retain the normal platform matcher. Native file identities are kept
intact for cloud move and playback URL generation.

Fork revision 6 treats MoviePilot's Plex void refresh return as an accepted
request (exceptions and False still fail), not evidence of completed indexing.

Mikan results, and Japanese-animation candidates from all other automated search
sources, require both a named translation group in release tags and an explicit
Chinese-language marker. No-group, explicitly unsubtitled, and encode-only releases
(including LoliHouse or Nix-Raws without a translation-group credit) are rejected.
This is conservative title-based filtering, not inspection of subtitle tracks.
Unknown explicitly named `字幕组/字幕社/字幕屋` remain fallback candidates. English-only
unknown group names are rejected until added to the alias list.

Subjective preference tiers (equal rank within a tier): SweetSub / 千夏 / 拨雪寻春 /
喵萌奶茶屋; then 诸神 / 澄空 / 华盟 / 北宇治 / 霜庭云花; then 桜都 / 豌豆 / 动漫国 /
极影; then other named groups. Preferences precede episode coverage within the
existing resource-type, availability and official-source ordering. No automatic
replacement of already-owned episodes is enabled. Applies to new candidates only,
never renames or rejects files already in the library.

Reference checked 2026-09-05: https://flynncao.uk/posts/translation-group-review/
and community discussion https://bangumi.tv/group/topic/385688 . These are opinions,
not universal scores; the second/third tiers include coverage-oriented fallback
choices rather than claiming every group has been scientifically ranked.
The policy is maintained in `search/fansubs.py`, covered by tests and preserved
by upstream-sync. Mikan UI describes the active policy.
