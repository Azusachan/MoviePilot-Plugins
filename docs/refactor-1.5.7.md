# Upstream 1.5.7 integration

Pinned upstream: `c80e55662ee25e49f5dce405d5c5a27ba73b6cc1`.
Merge parent: the stable fork main; no rebase or history replacement.

## Ownership

- Native upstream search/drive definition discovery and Vue configuration UI.
- Native Mikan package replaces the fork's obsolete single-file adapter.
- Native `MediaServerResolver` replaces the fork's Plex resolver.
- Native immediate subscription queue and pending reservation implementation;
  original behavior tests now target these implementations.
- Fork keeps its identity, configuration prefix and `cloudsubscribefork.db` name.
- Fork retains Japanese-animation subtitle provenance/preferences at the common
  search result boundary, after upstream source-specific filters.
- Conservative title matching remains the default: substring matching must be
  explicitly requested, not silently match another series/sequel.
- Legacy patch entry points now validate rather than modifying source text.

## Release gate

Integration branch must not publish a stable release. Required checks: unit
fixtures, relative-import/identity validation, frontend build, runtime import
with declared dependencies, and database compatibility. Production is not
mounted in test containers, and no subscription/download worker is started.
Only merge this PR after these checks pass; main publishes the stable release.

Real subscription transfer and Plex visibility require a separate production
acceptance check; fixture tests do not claim to prove resource availability.
