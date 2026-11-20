# CI dashboard examples (task tooling/50)

The sprint dashboard rides the forge — never the tree. The rule and its
reason live in the manifest's decision history: auto-committed reports
resurrect the post-merge writer, and a CI commit-back breaks "nothing
automatic writes main".

- **GitHub**: shipped live in this repo —
  [.github/workflows/sprint-comment.yml](../.github/workflows/sprint-comment.yml).
  On every PR it renders the current sprint's gantt, burn-down and kanban
  (mermaid renders in comments) into ONE sticky note per PR.
- **GitLab**: [gitlab-ci-dashboard.yml](gitlab-ci-dashboard.yml) — the same
  three charts into ONE sticky MR note via the notes API. Needs `GL_TOKEN`.
- Plain text is portable: every chart is also printable (`jear board`,
  `jear burndown`, `jear plan <file> --gantt`).

The tree holds exactly one kind of report — the release-time frozen slice
(`.jearless/reports/`), written by the human-run release step.
