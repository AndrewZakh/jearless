# Release checklist (printed at finalize — task tooling/51)

0. The flow: `jear release` prepared release/<tag> (the artifacts branch) →
   its PR merged → `jear release --finalize <tag>` landed the tag on the
   merge commit.
1. The tag is pushed — but the release is LOCAL until published:
   `uv build && uv publish`
2. Metadata (pyproject classifiers/urls) changed since the last release?
   Rehearse on TestPyPI first: `uv publish --publish-url https://test.pypi.org/legacy/`
   (separate account/token).
3. Verify: the JSON API (`pypi.org/pypi/jearless/json`) is the ground truth;
   a fresh install may need `--refresh` while uv's index cache catches up.
4. The dashboard is on demand (`jear sprint`) — nothing to refresh.
5. Recovery, the rare case: the artifacts commit reached the server but the
   tag push failed? The local tag usually already exists (the release step
   created it): push it — `git push origin refs/tags/<tag>`. Only when the
   local tag is missing too, create it on the release commit's SHA and push.
   The release step does not need a rerun.
