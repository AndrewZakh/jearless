# Release checklist (printed by every release)

1. The tag is pushed — but the release is LOCAL until published:
   `uv build && uv publish`
2. Metadata (pyproject classifiers/urls) changed since the last release?
   Rehearse on TestPyPI first: `uv publish --publish-url https://test.pypi.org/legacy/`
   (separate account/token).
3. Verify: the JSON API (`pypi.org/pypi/jearless/json`) is the ground truth;
   a fresh install may need `--refresh` while uv's index cache catches up.
4. The dashboard may be stale: `jear sprint --write` and commit it.
