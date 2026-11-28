# Security policy

jearless is a small command-line tool. It reads your git repository and its
own YAML files, and it talks to a forge only to open pull requests. Still, if
you find a weakness, please report it.

## What jearless touches

- **Reads**: git history, refs and remotes, `.jearless/*.yml`, `.jearless.toml`.
- **Writes**: the registry, plans and release artifacts — as files you review
  in a pull request before they reach main.
- **Runs**: `git` and `gh`. They are found on `PATH`; nothing is downloaded
  or executed at runtime.
- **Network**: through git and `gh`, plus one request of its own — to the
  GitLab API when `GL_TOKEN` (or `GITLAB_TOKEN`) and the CI variables are set.

There is no server, no daemon and no background process.

## Secrets

jearless stores no credentials. It relies on the tokens already available to
`gh`, or on the `GL_TOKEN` (or `GITLAB_TOKEN`) environment variable, which it
reads and sends only to the GitLab API.
Do not put tokens into `.jearless/`, `.jearless.toml`, task descriptions or
commit messages — the registry is committed to the repository, so anything
written there is public.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting: the **Report a vulnerability**
button under the repository's **Security** tab. If the button is not there,
open a regular issue asking for a private contact, without the details.

Please do not open a public issue with the specifics of an unpatched problem.

## The dashboards workflow

The sprint-comment workflow installs the pull request's own jearless
(`pip install .`) and runs it with the `pull-requests: write` permission.
Fork pull requests receive a read-only token, so the exposure is
same-repository only. The pattern must not move to `pull_request_target` —
if a trigger change is ever proposed, this note is the tripwire.

## What to expect

This is a one-maintainer project without a fixed response window. Reports are
read in order of arrival; a fix lands as a pull request and is announced in
the changelog of the next release.

## Supported versions

Only the latest release receives fixes. The tool has no long-lived service
component, so upgrading is a reinstall.
