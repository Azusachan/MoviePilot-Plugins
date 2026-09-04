# CloudSubscribe Plex compatibility fork

This fork tracks `odomu/MoviePilot-Plugins` and publishes CloudSubscribe builds
that use MoviePilot's generic media-server API when calculating existing TV
episodes. This removes the upstream Emby-only gate while preserving the
Emby-specific path and media-stream logic used elsewhere.

## Versioning

Published versions use:

`<upstream-version>.<upstream-commit-count>.<short-commit-as-decimal>`

Only numeric components are used because MoviePilot's version comparator treats
unknown text components as older than a normal release. The full commit remains
available in `.github/UPSTREAM_COMMIT` and in each release note.

`.github/UPSTREAM_COMMIT` records the exact upstream source commit.

## Automated updates

`sync-upstream.yml` checks upstream daily and can also be run manually. It:

1. Rebuilds the tracked tree from the newest upstream `main` commit.
2. Applies the fail-closed Plex patch.
3. Derives a commit-based version.
4. Runs unit tests, Python compilation, and the frontend build.
5. Pushes and publishes a release only when every step succeeds.

If upstream changes a patch marker, the action stops before publishing. Do not
edit generated upstream files directly; update the patch script and tests.
# Mikan search

The fork includes a public Mikan search provider, defaulting to https://mikanani.me.
Enable `mikan` in search source order and `magnet` in resource types. It searches
up to three title aliases, matches release titles, deduplicates info hashes,
and reuses the existing subscription filtering and 115 offline pipeline.
The configurable URL, request interval, timeout and result limit are exposed in
the Mikan settings tab. No Mikan account is required. Later seasons without an
explicit season marker are conservatively rejected; full absolute-number mapping
and per-show RSS/subgroup pinning are not implemented yet.

Fork revision `.1` adds Mikan. Upstream sync preserves the provider, UI field file,
integration script and tests, then reapplies integration with exact markers.
An upstream marker conflict stops the release for review.
# Personal anime subtitle policy (fork revision 2)

Fork revision 3 supplies explicit season/episode fields for Mikan `[08]`,
`[01-03]`, and ` - 08v2` titles. Resolution and year tags are not episode numbers.
This avoids unnecessary remote torrent metadata lookups during offline submission.

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
