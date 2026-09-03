# Graph shape

Authors over-connect Tracecat graphs. Two habits produce it: an edge from every producer to
every consumer so the data "reaches" the action that needs it, and a `run_if` on every branch
repeating a condition an ancestor already enforced. Neither is required by the engine, and both
are paid for by whoever reads the workflow next.

Prefer linear over parallel, readability over full connectedness. Fewer edges is the metric.

## `depends_on` is execution order, not data wiring

An action can read `ACTIONS.<ref>.result` from any ancestor, not only from a direct parent.
Expression validation checks that the referenced ref exists in the workflow, not that it is a
direct parent, so a transitive path is enough. If `create_case` depends on `triage_alert`,
which depends on `fetch_alert`, then `create_case` reads `${{ ACTIONS.fetch_alert.result }}`
with no edge of its own, and adding that edge buys nothing.

So `depends_on` answers exactly one question: **must this action wait for that one?** Add the
edge when the answer is yes. Never add it to make a value reachable.

## One chain by default

Each action depends on the action before it and reads whatever else it needs from further
upstream. Branch only when two pieces of work are genuinely independent and worth running
concurrently, and rejoin only when a later action needs results from more than one branch. One
parent is the norm; more than one is a deliberate join with a strategy you chose.

## Worked example

The graph below is what over-connection looks like: every consumer is wired to every producer,
and the escalation condition is restated on each downstream action.

```yaml
# BEFORE - nine edges, two guards, one real path
actions:
  - ref: fetch_alert
    action: core.http_request
    args:
      url: https://siem.internal.example/api/alerts/${{ TRIGGER.alert_id }}
      method: GET

  - ref: enrich_ip
    action: core.http_request
    depends_on:
      - fetch_alert
    args:
      url: https://intel.internal.example/api/ip/${{ ACTIONS.fetch_alert.result.data.src_ip }}
      method: GET

  - ref: score_alert
    action: core.script.run_python
    depends_on:
      - fetch_alert   # redundant: already an ancestor through enrich_ip
      - enrich_ip
    args:
      inputs:
        alert: ${{ ACTIONS.fetch_alert.result.data }}
        reputation: ${{ ACTIONS.enrich_ip.result.data }}
      script: |
        def main(alert: dict, reputation: dict) -> dict:
            score = int(reputation["risk"]) + int(alert["weight"])
            return {"score": score, "escalate": score >= 70}

  - ref: triage_alert
    action: ai.agent
    depends_on:
      - fetch_alert   # redundant
      - enrich_ip     # redundant
      - score_alert
    run_if: ${{ ACTIONS.score_alert.result.escalate }}
    args:
      user_prompt: Investigate this alert and summarize what an analyst should do next.
      instructions: You are a SOC analyst. Be specific and cite the enrichment you used.
      model:
        name: claude-sonnet-4-5
        provider: anthropic

  - ref: create_case
    action: core.cases.create_case
    depends_on:
      - fetch_alert   # redundant
      - score_alert   # redundant
      - triage_alert
    run_if: ${{ ACTIONS.score_alert.result.escalate }}   # restates an upstream gate
    args:
      summary: ${{ ACTIONS.fetch_alert.result.data.title }}
      description: ${{ ACTIONS.triage_alert.result }}
      priority: high
      severity: medium
```

The extra edges are worse than noise. With three parents, whether `create_case` runs now
depends on join semantics rather than on the one condition the author meant to express, and a
reader has to work that out for a workflow that has no real join.

The same workflow as a chain. The redundant edges are gone, downstream actions read from
ancestors, and the escalation condition is stated once.

```yaml
# AFTER - four edges, one guard, the path is the graph
actions:
  - ref: fetch_alert
    action: core.http_request
    args:
      url: https://siem.internal.example/api/alerts/${{ TRIGGER.alert_id }}
      method: GET

  - ref: enrich_ip
    action: core.http_request
    depends_on:
      - fetch_alert
    args:
      url: https://intel.internal.example/api/ip/${{ ACTIONS.fetch_alert.result.data.src_ip }}
      method: GET

  - ref: score_alert
    action: core.script.run_python
    depends_on:
      - enrich_ip
    args:
      inputs:
        alert: ${{ ACTIONS.fetch_alert.result.data }}       # ancestor, no edge needed
        reputation: ${{ ACTIONS.enrich_ip.result.data }}
      script: |
        def main(alert: dict, reputation: dict) -> dict:
            score = int(reputation["risk"]) + int(alert["weight"])
            return {"score": score, "escalate": score >= 70}

  - ref: triage_alert
    action: ai.agent
    depends_on:
      - score_alert
    run_if: ${{ ACTIONS.score_alert.result.escalate }}       # the only gate in the workflow
    args:
      user_prompt: Investigate this alert and summarize what an analyst should do next.
      instructions: You are a SOC analyst. Be specific and cite the enrichment you used.
      model:
        name: claude-sonnet-4-5
        provider: anthropic

  - ref: create_case
    action: core.cases.create_case
    depends_on:
      - triage_alert
    args:
      summary: ${{ ACTIONS.fetch_alert.result.data.title }}  # ancestor, no edge needed
      description: ${{ ACTIONS.triage_alert.result }}
      priority: high
      severity: medium
```

Nothing about execution changed except that it became legible. `create_case` still runs only on
escalation, because a skipped `triage_alert` skips everything below it.

## How skips actually travel

- A skipped task marks its outgoing edges skipped.
- A task whose dependency edges are **all** skipped is skipped in turn, and the skip keeps
  travelling. On a chain, one `run_if` therefore gates every action below it. Repeating the
  condition downstream is dead weight, and a stale copy of it is a bug waiting for the day the
  two conditions diverge.
- A task with a mix of skipped and surviving parents is not force-skipped, and its
  `join_strategy` decides what happens next. This is the case where a `run_if` on the task
  itself earns its place.
- A failure is not a skip. When an action fails, its non-error edges are pruned, so anything
  hanging off the default success edge does not run. Do not write a `run_if` that asks whether
  the parent succeeded; add an explicit `<ref>.error` dependency when you want a failure path.

```yaml
  - ref: alert_on_fetch_failure
    action: core.script.run_python
    depends_on:
      - fetch_alert.error
    args:
      inputs:
        alert_id: ${{ TRIGGER.alert_id }}
      script: |
        def main(alert_id: str) -> dict:
            return {"unfetched_alert": alert_id}
```

## When a join is correct

A join is correct when a later action genuinely needs results from work that ran on separate
paths, and that work was worth separating in the first place: two independent lookups against
different systems, not two halves of one sequential thought.

```yaml
  - ref: triage_alert
    action: ai.agent
    depends_on:
      - enrich_ip
      - fetch_asset_owner
    join_strategy: all
    args:
      user_prompt: |
        Reputation: ${{ ACTIONS.enrich_ip.result.data }}
        Asset owner: ${{ ACTIONS.fetch_asset_owner.result.data }}
      instructions: You are a SOC analyst. Recommend a next action and name the owner to page.
      model:
        name: claude-sonnet-4-5
        provider: anthropic
```

`join_strategy: all` is the default: every parent must have completed on a surviving path. Use
it when the joining action needs all of the inputs, which is the usual case.

`join_strategy: any` runs the action as soon as one parent survives. Use it for alternate paths
to the same outcome — a paging step reachable from either an on-call lookup or a fallback
rotation. Under `any`, a partially skipped upstream still fires the join, so put the guard on
the join task when only some of those paths should reach it:

```yaml
  - ref: page_on_call
    action: core.script.run_python
    depends_on:
      - lookup_primary_on_call
      - lookup_fallback_rotation
    join_strategy: any
    run_if: ${{ ACTIONS.score_alert.result.escalate }}
    args:
      inputs:
        score: ${{ ACTIONS.score_alert.result.score }}
      script: |
        def main(score: int) -> dict:
            return {"paged": True, "score": score}
```

## Scatter and gather are not branching

Branching is an authoring choice about two different pieces of work. Scatter is fan-out over
the items of a list at runtime: the stream count comes from the data, and the graph still
shows one node whatever the list length. Do not model per-item work as parallel branches, and
do not read a scatter as a readability failure — a scatter and the actions below it are a
straight line.

Add `core.transform.gather` only when a downstream action needs the combined list; omit it
otherwise. For fanout limits, batching, and when to keep the loop inside a script instead, see
[run-python](run-python.md).
