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
- [quote_mermaid_labels.py](quote_mermaid_labels.py) — a small filter both
  dashboard jobs pipe the board through. Parentheses in an unquoted kanban
  label break mermaid's parser; the filter quotes the card labels and leaves
  the rest untouched.

Both jobs show the sprint view: the latest plan's cards plus any unplanned
work in progress. Pass `--all` to `jear board` in a job to see the whole
working set instead.

## Protecting main

[branch-protection.md](branch-protection.md) — the settings that make the
charter enforceable: pull requests only, required checks, no force pushes, no
deletions, merge commits only. One recipe for GitHub, one for GitLab.

The tree holds exactly one kind of report — the release-time frozen slice
(`.jearless/reports/`), written by the human-run release step.
