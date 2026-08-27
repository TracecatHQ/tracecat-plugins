# Expressions, conditions, and transforms

Authors reach for Python too fast. Before writing a script, walk down this ladder and stop at
the first rung that genuinely does the job:

1. **Inline expression** — `${{ ... }}` in an action argument. Fallbacks, casts, string
   building, indexing, arithmetic, comparisons.
2. **`run_if`** — gate whether an action runs at all, evaluated by the scheduler before the
   action is scheduled. No node, no output, no cost.
3. **`core.transform.*`** — a declarative, visible node for filtering, mapping, deduping,
   reshaping, and fan-out. The reviewer can read what it does from the graph.
4. **`core.script.run_python`** — real code, for real data plumbing.

Go down a rung only when the rung above cannot express the work, not when it merely feels
smaller. A `run_python` action that returns `len(items) > 0` is a rung-4 answer to a rung-1
question: it costs a sandbox start, hides the logic behind an opaque node, and forces the
reviewer to read a script to learn what a condition says.

## Expression grammar

The full operator set: `||` and `&&` (short-circuit or/and), `not`, comparisons
`== != > >= < <=`, membership `in` / `not in`, identity `is` / `is not`, arithmetic
`+ - * / %`, unary `-` and `+`, indexing `expr[...]`, list literals `[a, b]`, and dict literals
`{"k": v}`. Parentheses group.

**The ternary is Python-style — `a if cond else b`.** Widely-circulated examples write
`cond -> a : b` or treat `->` as a ternary operator; that is wrong. `->` is the **trailing
typecast** and takes a type on its right: `${{ TRIGGER.count -> int }}`. The prefix form
`int(TRIGGER.count)` is equivalent.

**`TYPE_SPECIFIER` is `int | float | str | bool` and nothing else.** There is no `datetime`
typecast — `${{ TRIGGER.ts -> datetime }}` fails to parse. (An internal Tracecat doc claims
otherwise; it is wrong.) Use `FN.to_datetime(...)` / `FN.to_isoformat(...)` for time values.
Note that `expects` field types are a *different* grammar that does include `datetime` — see
[trigger-inputs](trigger-inputs.md).

**Literals are `True`, `False`, and `None` — capitalized, Python-style.** Lowercase `true`,
`false`, and `null` are not literals in this grammar and are not identifiers either, so they
fail at parse time rather than resolving to something surprising.

The one gotcha this produces, worth memorizing on its own: **`${{ TRIGGER.x || false }}` does
not parse.** The parser rejects the `f`, because after `||` it expects an expression and
lowercase `false` matches no terminal. `${{ TRIGGER.x || False }}`, `${{ TRIGGER.x || 9 }}`,
and `${{ TRIGGER.x || "" }}` all parse fine. Same root cause as the capitalization rule — the
boolean fallback is the case where it bites, because JSON habits make `false` feel right.

## Contexts

`TRIGGER` (the trigger payload), `ACTIONS.<ref>.result` (an upstream action's output),
`SECRETS.<name>.<KEY>`, `VARS.<name>.<key>`, `ENV`, and `FN.<function>(...)`. Inside an action
template, `inputs` and `steps` address the template's own inputs and prior steps.

**The current `for_each` item is `var`, not `LOCAL`.** `${{ var.item.id }}` resolves;
`${{ LOCAL.item.id }}` fails to parse.

## `run_if`

`run_if` takes an expression and is evaluated per task in the scheduler. **A falsy result skips
the action** — the task never runs and its downstream edges are marked skipped. **An error
while evaluating the expression is a non-retryable failure, not a skip**: a `run_if` that
references a misspelled action ref or an unparseable literal fails the workflow rather than
quietly falling through. That asymmetry is why a `run_if` should be a plain readable
comparison, not a clever expression with several ways to blow up.

**You do not need to reuse conditions.** Putting the same `run_if` on three branches is
correct and readable — each branch states its own gate where a reviewer reads it. Do not add a
router `run_python` node whose only job is to emit booleans so the condition is written once:
that trades three legible expressions for one opaque node plus three
`${{ ACTIONS.router.result.is_x }}` indirections, and it moves branching logic out of the graph.

Reserve a router gate for genuinely multi-signal classification that an expression cannot do —
for example one webhook that must distinguish a Slack `url_verification` handshake from an
`app_mention` from a scheduled tick, where the discriminator is a different key in each shape.
Even then, have the router emit a small classification field and keep the branch conditions
readable off it.

## The transform actions

Thirteen `core.transform.*` actions exist. They are listed name-only in the DSL reference and
never demonstrated, which is why authors skip straight to `run_python`. Each one is a visible
node a reviewer can read:

- **`reshape`** — define the exact scalar, object, or list you want. The workhorse: renaming
  fields, building a payload, pinning a workflow's output shape.
- **`filter`** — keep list items matching a Python lambda string.
- **`is_in`** — keep list items that appear in a collection. Allowlist checks against a table
  lookup or a `VARS` list.
- **`not_in`** — the inverse. Denylist and suppression checks.
- **`deduplicate`** — collapse a list of objects to one per key tuple. It defaults to
  `persist: true`, which suppresses keys seen in *earlier runs* for `expire_seconds` (1 hour by
  default); pass `persist: false` for within-run dedupe only.
- **`is_duplicate`** — the single-object boolean form, always persistent. Use it as the cheap
  guard in front of an expensive agent run. It **records the key as seen as a side effect**, so
  a second call for the same object returns `true` — check once, then branch on the result.
- **`apply`** — run a lambda over a single value.
- **`map`** — run a lambda over each item of a list.
- **`drop_nulls`** — remove nulls from a list. Cheaper and clearer than a `filter` lambda.
- **`scatter`** — fan a list into parallel execution streams. The default for workflow-level
  loops; see [run-python](run-python.md) for the concurrency limits.
- **`gather`** — collect scattered streams back into one list. Add only when a downstream step
  needs the combined result.
- **`flatten_json`** — flatten a nested object into single-level dotted fields. Useful right
  before a table write.
- **`eval_jsonpaths`** — evaluate several JSONPath expressions against one object in a single
  node. Extracting six fields from a nested SIEM payload is one `eval_jsonpaths`, not six
  `reshape` actions or a script.

A chain of two or three transform actions is usually more reviewable than one script. Once the
chain would run past three or needs error handling, batching, or joins, that is the honest
signal to drop to `run_python`.
