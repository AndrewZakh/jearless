# Release checklist (printed by every release)

1. The tag is pushed — but the release is LOCAL until published:
   `uv build && uv publish`
2. Metadata (pyproject classifiers/urls) changed since the last release?
   Rehearse on TestPyPI first: `uv publish --publish-url https://test.pypi.org/legacy/`
   (separate account/token).
3. Verify: the JSON API (`pypi.org/pypi/jearless/json`) is the ground truth;
   a fresh install may need `--refresh` while uv's index cache catches up.
4. The dashboard is on demand (`jear sprint`) — nothing to refresh.
5. Recovery, the rare case: the artifacts commit reached the server but the
   tag push failed? Tag that commit by hand — `git tag <tag> <sha> && git
   push origin <tag>` — the tag must land on the artifacts commit; the
   release step does not need a rerun.
