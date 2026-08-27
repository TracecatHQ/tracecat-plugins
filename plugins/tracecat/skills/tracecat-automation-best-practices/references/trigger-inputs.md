# `entrypoint.expects` — the trigger input schema

`entrypoint.expects` declares what the workflow's trigger payload must look like. Every way a
workflow runs — webhook body, case event, schedule, or `core.workflow.run` `inputs` — is
validated against this schema **before dispatch**. Fields declared here are what
`${{ TRIGGER.<field> }}` expressions reference.

It lives in the draft at `/definition/entrypoint/expects` (patch it via `edit_workflow` like any
other path), or under `entrypoint:` in `create_workflow`'s `definition_yaml`. A bare top-level
`entrypoint:` outside `definition:` may parse but will not register trigger inputs at runtime.

## Field shape

`expects` is a mapping of field name to a field spec:

```yaml
entrypoint:
  ref: fetch_indicator
  expects:
    indicator:
      type: str
      description: The IOC to look up
    severity:
      type: enum["low", "medium", "high"]
      default: low
    tags:
      type: list[str]
      default: []
```

Each field spec supports:

- `type` (required) — a type string from the grammar below.
- `description` — human-readable, shown in the builder.
- `default` — when present, the field is **optional** and this value is used when the payload
  omits it. A field with **no `default` is required**: a payload missing it is rejected. An
  explicit `default: null` makes the field optional with a `None` default (distinct from
  omitting `default`, which makes it required).

## Type grammar

`type` accepts:

- Primitives: `int`, `str`, `bool`, `float`, `datetime`, `duration`, `any` (or `Any`), `None`.
- Lists: `list[<type>]` — e.g. `list[str]`, `list[dict[str, any]]`. A bare `list` is rejected;
  the item type is required.
- Dicts: `dict[<key type>, <value type>]`, or bare `dict` (equivalent to `dict[str, any]`).
- Unions with `|` — e.g. `str | None` (a common way to write "optional string"), `int | float`.
- Enums: `enum["a", "b", "c"]` — the payload value must be one of the quoted literals. At most
  20 values, compared case-insensitively for duplicates.
- References: `$SomeReference` — a named reference to another schema.

Note that this grammar is **not** the expression grammar. `datetime` and `duration` are valid
here and have no equivalent typecast in `${{ ... }}` expressions; see
[expressions-and-conditions](expressions-and-conditions.md).

Examples:

```yaml
expects:
  case_id:
    type: str
  count:
    type: int
    default: 1
  window:
    type: duration          # ISO 8601 duration, e.g. "PT1H"
  payload:
    type: dict[str, any]
    default: {}
  status:
    type: enum["open", "closed"] | None
    default: null
```

## Validation behavior

- A payload field that fails its type check returns a fixable error **naming the field** — fix
  the payload (or the schema) and retry; nothing runs on a failed validation.
- **Extra payload fields not declared in `expects` are rejected.** The generated model is built
  with `extra="forbid"`, so a webhook that sends five keys against a three-key schema fails
  outright rather than ignoring the surplus. Declare everything the trigger sends, or widen the
  schema with a `dict[str, any]` catch-all field.
- When `expects` is empty or absent, any JSON payload is accepted as-is. That is convenient
  while iterating and a liability in production: `validate_workflow` can pass while a later run
  silently resolves `${{ TRIGGER.whatever }}` to nothing. Declare every trigger input a workflow
  actually reads.
