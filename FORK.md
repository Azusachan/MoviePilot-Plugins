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
