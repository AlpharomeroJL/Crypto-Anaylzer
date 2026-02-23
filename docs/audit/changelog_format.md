# Changelog format

- **File:** `CHANGELOG.md` at repo root.
- **Latest release:** First header of the form `## [X.Y.Z] - YYYY-MM-DD` or `## [vX.Y.Z]` is the current release. Version must match `crypto_analyzer.__version__` (see `crypto_analyzer._version`).
- **Check:** Run `python tools/check_version_changelog.py` from repo root. CI and release workflows use this to enforce consistency.
- **Releases:** When cutting a release, add a new `## [X.Y.Z] - YYYY-MM-DD` section at the top (below the intro). Use the actual release date (e.g. today’s date when tagging). Do not leave "Unreleased" as the first release header when tagging.
