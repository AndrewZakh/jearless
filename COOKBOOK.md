# COOKBOOK.md — the query cookbook

The registry is data — the questions answer by one-liners, not by reading
docs. Every query here is verified against this repository's registry
(re-verified 2026-11-25: 13 live tasks, 22 pt).

## The stack

`yq` (mikefarah — `brew install yq`) converts YAML→JSON, `jq` aggregates:

```sh
yq -o=json .jearless/tasks.yml | jq '<query>'
```

Archive files live next to the registry and share its shape, so the same
queries work against them — for example the tasks archived at a release:

```sh
yq -o=json .jearless/archive_v1.0.0.yml | jq '[.tasks[][]] | length'
```

`yq` reads one file at a time, so a total across every archive is a shell
loop — here the number of tasks archived to date:

```sh
for f in .jearless/archive_*.yml; do yq -o=json "$f" | jq '[.tasks[][]] | length'; done | jq -s 'add'
```

The registry plus the archives is what jearless calls the union — the
identity of every task ever recorded, which `jear report` reads.

## The questions

### Total effort (points across the live registry)

```sh
yq -o=json .jearless/tasks.yml | jq '[.tasks[][] | select(.story_points) | .story_points] | add'
```

### Effort per project

```sh
yq -o=json .jearless/tasks.yml | jq '.tasks | to_entries | map({(.key): ([.value[] | select(.story_points) | .story_points] | add)})'
```

### Task count

```sh
yq -o=json .jearless/tasks.yml | jq '[.tasks[][]] | length'
```

### Tasks with dependencies (blocked candidates)

```sh
yq -o=json .jearless/tasks.yml | jq '[.tasks[][] | select(.depends_on) | {id, summary, depends_on}]'
```

### The big ones (≥3 pt)

```sh
yq -o=json .jearless/tasks.yml | jq '[.tasks[][] | select(.story_points >= 3) | {id, summary, story_points}]'
```

## jmespath: extraction yes, aggregation no

jmespath is the portable extraction language (ecosystem: AWS CLI, GitHub),
and extraction works:

```
tasks.*[*].story_points      # every story point, flattened
tasks.*[?depends_on]         # entries carrying depends_on
```

But two hard limits were verified empirically on the python lib (1.1.0):
a literal array (`sum([1,2,3])`) does not parse — the grammar has no
multi-element literal arrays — and `sum()` over a hash-wildcard projection
raises a type error ("received: list"). Aggregation lives in jq; jmespath
is the portability layer, not the calculator.
