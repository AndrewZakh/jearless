# Branch protection recipes (task tooling/54)

The constitution: **main accepts changes only through PRs/MRs**. Nothing
automatic writes main — and, since the two-phase release (tooling/51), not
even the release does. The emergency admin-bypass valve stays explicit: a
burning production allows a direct hotfix, and every use becomes a ledger
scar in `.jearless/doctor_ignore` — visibility, not prohibition, now with
the platform's teeth.

## GitHub

Settings → Rules → Rulesets (or Branches → Add branch protection rule) on `main`:

- **Require a pull request before merging** — bypass: emergency only (every
  bypass use lands in the ledger with its cause)
- **Require status checks to pass**: `tests`, `sprint dashboard` (the gate
  and the dashboard from `.github/workflows/`)
- **Block force pushes**; **Restrict deletions** — the history IS the database
- Repo setting → General → Pull Requests → **Allow only merge commits**
  (squash and rebase are disabled repo-wide: the changelog reads the branch
  name from the merge subject)

## GitLab

Settings → Repository → Protected branches, `main`:

- **Allowed to merge**: Maintainers; **Allowed to push and merge**: No one
  (MR-only)
- **Allowed to force push**: off
- Settings → Merge requests → Merge method: **merge commit**
- The dashboard: `examples/gitlab-ci-dashboard.yml` (the sticky MR note)

## The tooling side

The local half of the constitution ships with the tool: the version hook
ignores the forge-ride prefixes (`registry/`, `ledger/`, `archive/`,
`release/` — see `.version-hook.yml`; the hook fails closed on unmatched
names, so every new tool prefix ships with its rule), and the pre-commit
hook refuses duplicate registry keys before the commit lands.
