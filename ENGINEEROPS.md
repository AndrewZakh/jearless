# EngineerOps — Concept 0.1

> Status: Concept. The philosophy jearless grew out of — and one that is
> wider than the tool. Not a specification and not a roadmap: hardening the
> concept into a rigid system would be premature.

## The thesis

**A task is an intent to spend resources on changing reality. Reporting is
the way to explain why those resources were spent and what the organization
received in return.**

The traditional approach confuses the two: the management system becomes the
reporting system. EngineerOps separates them.

## The main goal

Let the engineer spend more time creating engineering outcomes — and less
time explaining how those outcomes are created.

## Principles

- **The engineer comes first.**
- **The process rests on artifacts**, not on forms and not on statuses.
- **The history of the work is preserved** by the same mechanism that
  preserves its results.
- **Traceable provenance** — for every outcome.
- **Reporting is assembled automatically** wherever possible — from
  artifacts, not from forms.
- **AI helps turn unstructured activity into structured knowledge.**
- **Analytics rests on real evidence.**
- **Judging a person remains a human's job.**

## The artifact model L1–L4

The levels are not file types and not mandatory lifecycle stages. They are
levels of maturity and practical completeness of an outcome.

| Level | Meaning | Examples |
|---------|-------|---------|
| L1 — Activity | Recorded activity | A dialogue, an observation, an idea, an experiment |
| L2 — Knowledge | Knowledge gained | A study, a hypothesis, a specification |
| L3 — Engineering | A solution built | Code, a model, a calculation, a design, a prototype |
| L4 — Outcome | A practical result | An adoption, a release, production, an accepted result |

Common artifact properties: `id`, provenance, links.

## Git — a mechanism, not the foundation

Git is an excellent mechanism for one region of EngineerOps. Engineering
artifacts are wider: dialogues, observations, studies, calculations,
production results. The philosophy does not demand everything be stored in
git — it demands provenance be preserved. jearless is the git-native
implementation of the engineering contour of this philosophy; the wider
regions of EngineerOps belong to other tools and other carriers, connected
by provenance.

## Boundaries and chaos

- **People matter more than processes** ("Individuals and interactions over
  processes and tools" — inherited).
- **Chaos is data, not a violation.** An unplanned task is shown by the
  retrospective, counted by the report, absorbed by the registry. Discipline
  lives in visibility, not in prohibition.
- **Reporting answers "what"; the retrospective answers "why".** Git knows
  the facts; people know the reasons.
- **Judging a person remains a human's job.** AI does not judge — it turns
  unstructured activity into structured knowledge.

## Slogans

- Engineering without Reporting.
- Engine without J(G)ears.
- Engineering without the excess fat.

## The link to jearless

[jearless](README.md) is the git-native implementation of the engineering
contour of this philosophy: tasks, state derived from history, reporting
assembled from merges, the provenance audit. The philosophy is deliberately
wider than the tool: the tool is obliged to stay narrow.
