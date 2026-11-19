# COOKBOOK.md — the query cookbook

The registry is data — the questions answer by one-liners, not by reading
docs. Every query here is verified against this repository's registry
(re-verified 2026-11-19: 30 live tasks, 55 pt).

## The stack

`yq` (mikefarah — `brew install yq`) converts YAML→JSON, `jq` aggregates:

```sh
yq -o=json tasks.yml | jq '<query>'
```

Archive files are the same shape — the same queries work against
`archive_<tag>.yml`; their union is what `jear report` computes internally
(one database, queried directly).

## The questions

### Total effort (points across the live registry)

```sh
yq -o=json tasks.yml | jq '[.tasks[][] | select(.story_points) | .story_points] | add'
```

### Effort per project

```sh
yq -o=json tasks.yml | jq '.tasks | to_entries | map({(.key): ([.value[] | select(.story_points) | .story_points] | add)})'
```

### Task count

```sh
yq -o=json tasks.yml | jq '[.tasks[][]] | length'
```

### Tasks with dependencies (blocked candidates)

```sh
yq -o=json tasks.yml | jq '[.tasks[][] | select(.depends_on) | {id, summary, depends_on}]'
```

### The big ones (≥3 pt)

```sh
yq -o=json tasks.yml | jq '[.tasks[][] | select(.story_points >= 3) | {id, summary, story_points}]'
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
