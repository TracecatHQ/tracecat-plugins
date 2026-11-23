# Forms in Workspace Chat

A form turns a workflow's `entrypoint.expects` input schema into a page people fill in.
Submitting it runs the workflow's published version with trigger type `form`; each answer
arrives as `TRIGGER.<input name>`. A workflow has at most one form. The form config is stored
on the form, not in the workflow definition, so never edit form layout through
`core.workflow.edit_workflow`.

Forms tools appear only when the organization has the Forms feature. If no `core.forms.*` tool
is exposed, say that Forms is unavailable in this workspace instead of editing workflow inputs to
imitate one.

## Tools

| Task | Workspace Chat action | Notes |
| --- | --- | --- |
| Find a form | `core.forms.list_forms` | Paginate with `next_cursor`; absence from page one is not absence |
| Read a form | `core.forms.get_form(form_id=...)` | Returns status, config, issues, URL, and workflow |
| Create or change a form | `core.forms.update_form(workflow_id=..., config=..., status=...)` | Creates the form when the workflow has none |
| Read submissions | `core.forms.list_submissions`, `core.forms.get_submission` | Only when exposed; never by default |

`update_form` takes the workflow ID, not the form ID. `config` replaces the whole stored config:
read it with `get_form` first, change only what the user asked for, and send the full result.
Omit `config` to change only `status`. Omit `status` to leave it unchanged.

## Authoring flow

1. Identify the workflow. When the chat page context names a form, that is "this form": call
   `get_form` with that ID. Otherwise use a workflow or form ID from the conversation, or find the
   form with `list_forms`.
2. Read the workflow's inputs with `core.workflow.get_workflow`. Every form field must name an
   input in `entrypoint.expects`. To ask for something new, add the input to the workflow first
   (JSON Patch on `/definition/entrypoint/expects`), then reference it from the form.
3. Write the config, call `update_form`, and read the returned `issues`. Errors reject the
   config; warnings are saved. Fix errors and retry with the corrected whole config.
4. Set `status="online"` only when the user asks to open the form. It needs a published
   workflow; publishing is a separate, user-requested step.

## Config shape

All keys are optional. With an empty config the form shows every input in schema order, titled
and described from the workflow.

```yaml
title: Laptop request
description: Request a new laptop from IT. Markdown is allowed.
success_message: Thanks, IT will follow up within a day.
layout:
  - heading: Device
  - field: model
    widget: cards
    options:
      - value: mbp14
        label: MacBook Pro 14"
        description: For engineering
      - value: mba13
        label: MacBook Air 13"
  - field: reason
    widget: long_text
    help: Why do you need it?
  - divider: true
  - notice: Approvals take one business day.
    tone: info
  - field: requester_email
    autofill: requester.email
    hidden: true
  - field: receipt
    widget: file
    accept: [".pdf", "image/*"]
    max_files: 1
```

Layout entries, each a single-key mapping plus its options:

- `field: <input name>` with optional `label`, `help`, `placeholder`, `widget`, `options`,
  `visible_if`, `autofill`, `hidden`, and for files `accept` and `max_files`.
- `heading: <text>`, `text: <markdown>`, `notice: <text>` with `tone` of `info`, `success`,
  `warning`, or `danger`, and `divider: true`.

Widgets: `text`, `long_text`, `number`, `toggle`, `select`, `multi_select`, `cards`, `tags`,
`date`, `datetime`, `user`, `file`. A widget must suit the input type; for example `toggle`
needs a `bool` input and `multi_select` needs a list. `options` is a list of
`{value, label, description}`; for an enum input, values must be members of the enum.

`visible_if: {field: <input name>, equals: <value>}` shows a field only while another field
has that value. `autofill` is one of `requester`, `requester.user_id`, `requester.email`,
`requester.first_name`, `requester.last_name`, or `submission.id`; pair it with `hidden: true`
when the requester should not see or edit it. A `file` field with `max_files` above 1 needs a
`list[dict]` input.

Inputs left out of `layout` are appended in schema order. An optional input that cannot be
rendered produces a warning and takes its default.

## Do not

- Do not put form config in the workflow definition or invent a form ID.
- Do not bring a form online, publish its workflow, or delete submissions unless asked.
- Do not echo submission contents or uploaded files beyond what the user asked to see.
