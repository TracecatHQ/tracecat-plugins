# Slack message style

How a Tracecat Slack-posting agent should format what it sends. Applies to any inline
`ai.agent` or preset holding a Slack post-message tool. **Encode the relevant subset of this
guide inline in that agent's `instructions` field** — the agent reads its own instructions, not
this file.

This guide is generic craft. Automation-specific rules belong in that automation's own prompt:
console links, table names, risk scoring, scope families, resource identifiers, and Slack
action IDs.

Reference inputs: [incident.io's Slack message polish
notes](https://incident.io/changelog/polishing-our-slack-messages) and [Brex's security alert
automation write-up](https://medium.com/brexeng/elevating-security-alert-management-using-automation-828004ad596c).

## Design principles

The message should help the operator decide what to do next.

- Put the answer in the parent reply. Put supporting detail in thread replies.
- If the agent is invoked from Slack, always post back to the original Slack thread. A useful
  answer in the agent transcript is not a user-visible response.
- Use stable message shapes. Operators should know where to look for status, evidence, and
  actions.
- Keep high-volume output compact. Summarize first, then expand only when the user asks or
  clicks a control.
- Avoid noisy labels. Do not escalate wording beyond what the data proves.
- Make actions explicit. Buttons should correspond to concrete follow-ups, not vague "learn
  more" paths.
- Keep links out of the main body. Put console links and run links in Slack `context` blocks.

## Message shapes

Choose one response mode before rendering, then keep it fixed for the whole answer:

```json
{
  "messages": ["summary", "review_candidates"],
  "limit": null,
  "include_detail": false
}
```

Use that plan to select data first, then render from the selected data. Do not add extra
message types after rendering starts.

### Summary

Every answer starts with a compact parent reply. Use three blocks when there is enough context:

1. Title `section`: one bold line that answers the question.
2. Body `section`: one short sentence or 2-4 bullets.
3. Stats `context`: compact counts, freshness, review level, and links.

```json
[
  {"type": "section", "text": {"type": "mrkdwn", "text": "*No access grants need follow-up*"}},
  {"type": "section", "text": {"type": "mrkdwn", "text": "- Checked privileged access and broad data scopes.\n- Treated approved internal services as baseline.\n- Found no active grants with unclear ownership plus broad permissions."}},
  {"type": "context", "elements": [{"type": "mrkdwn", "text": "<https://example.com/security/access|Open access console> | Items reviewed: 18 | Users: 42 | Review level: default"}]}
]
```

Use one block for simple conversational thread follow-ups when a structured answer is not
needed.

### Review candidates

Use this shape when a small number of items needs human context. Do not use code-block tables
for triage findings.

```json
[
  {"type": "section", "text": {"type": "mrkdwn", "text": "*Review 2 access grants*"}},
  {"type": "context", "elements": [{"type": "mrkdwn", "text": "<https://example.com/security/access|Open access console> | Items reviewed: 18 | Users: 42 | Review level: default"}]},
  {"type": "section", "text": {"type": "mrkdwn", "text": "*Unclear app identity*\n> *Used by:* `<principal@example.com>`\n> *Access:* Admin settings, audit logs\n> *Check:* Who owns this app?\n> *Check:* Is admin audit access expected?\n> *ID:* `<resource_id>`"}},
  {"type": "divider"},
  {"type": "section", "text": {"type": "mrkdwn", "text": "*Example support tool*\n> *Used by:* `<principal@example.com>`\n> *Access:* Mail write\n> *Check:* Should this tool modify mail?\n> *ID:* `<resource_id>`"}},
  {"type": "actions", "block_id": "<automation>.audit_actions.v1", "elements": [
    {"type": "button", "text": {"type": "plain_text", "text": "Review privileged items", "emoji": false}, "action_id": "<automation>.review_privileged_items.v1", "value": "review_privileged_items"},
    {"type": "button", "text": {"type": "plain_text", "text": "Be more critical", "emoji": false}, "action_id": "<automation>.be_more_critical.v1", "value": "be_more_critical"}
  ]},
  {"type": "context", "elements": [{"type": "mrkdwn", "text": "Privileged items have more than basic profile, sign-in, or read-only access."}]}
]
```

Rules:

- The title carries the action. Do not add an `Action:` line.
- Put the object name on its own bold line.
- Candidate detail uses quoted lines with bold prefixes.
- Include one or two concrete triage questions.
- Show full identifiers when the user needs to copy them into a console.
- Wrap identifiers, emails, usernames, and scope names in inline code.
- Separate multiple candidates with dividers.
- Buttons must be real Slack `actions` blocks. Do not render fake button labels as normal
  mrkdwn text.
- Put button explanations in a `context` block under the buttons.

### Inventory table

Use a second thread reply with one `section` block containing a fenced code table when listing
two or more non-triage rows.

```json
[
  {"type": "section", "text": {"type": "mrkdwn", "text": "*Top access grants by user count* - sorted by users\n```\nSTATUS    ITEM                           ACCESS  USERS  ID\nHIGH      Example support tool                3      8  <short_id>\nMEDIUM    Example analytics app               2      4  <short_id>\nLOW       Example read-only app               1      2  <short_id>\n```"}},
  {"type": "context", "elements": [{"type": "mrkdwn", "text": "<https://example.com/security/access|Open access console>"}]}
]
```

Rules:

- Define the table columns in the automation instructions.
- Use literal spaces for alignment.
- Truncate display-only IDs in tables when needed, but keep full IDs in triage and specific-ID
  answers.
- If links are present, include a Slack `context` block.
- Do not use Slack `table` or `rich_text` blocks for high-volume lists.
- Continue in thread if the user asked for complete output and Slack limits require splitting.

### Detail expansion

Use detail sections only when the user asks for details or clicks an expansion button.

```json
[
  {"type": "section", "text": {"type": "mrkdwn", "text": "*Example support tool*\n8 users | 3 privileged permissions\n`mail.write`, `audit.read`, `admin.settings.read`"}},
  {"type": "divider"},
  {"type": "section", "text": {"type": "mrkdwn", "text": "*Example analytics app*\n4 users | 2 permissions\n`reports.read`, `profile.read`"}}
]
```

Each item should have a bold item name, a compact count subtitle, and inline-code chips for
permissions, labels, or other compact details.

## Slack mrkdwn

Slack `mrkdwn` is not GitHub Markdown, and the differences are the ones that show up as visibly
broken messages.

- Bold uses single asterisks: `*bold*`. **Never use double asterisks** — Slack renders them
  literally.
- Links use `<https://example.com|label>`. A bare `[label](url)` renders as its raw source.
- Inline code uses backticks.
- Do not use Markdown headings. `#` renders literally; use a bold first line instead.
- Use `section`, `context`, `divider`, and `actions` blocks.
- Avoid `header` blocks unless the workflow needs the larger visual treatment.
- The `text` argument of the post-message tool is the notification preview. Mirror the title in
  one plain sentence with no mrkdwn.

## Reaction lifecycle

A Slack-posting workflow triggered by `app_mention` should handle processing reactions in the
workflow, outside the review agent:

1. The workflow adds `:eyes:` to the mention.
2. The workflow fetches the Slack thread and includes it in the agent prompt.
3. The agent posts the styled reply in the original thread with its Slack post-message tool.
4. The workflow removes `:eyes:`.

The review agent must not call reaction tools. If a data lookup fails, the agent should still
post a concise warning in-thread — for example `:warning: *Could not fetch access grants*` plus
one concrete failure reason.

For Slack app mentions and Slack button actions, **posting to Slack is the completion
condition**. The agent must use the original `channel` and `thread_ts` from the workflow
prompt. Do not return a final text-only answer instead of posting, including for capability
questions such as "do you have access to that data source?".

## Before posting

Author-time criteria for reviewing a Slack-posting agent's output. Encode the ones that apply
to the automation; do not paste the whole list into the prompt as an end-of-prompt validation
checklist, which bloats the prompt and drifts out of sync with the rules above.

- Exactly one summary reply exists.
- Triage findings are compact blocks, not code-block tables.
- Links appear only in Slack `context` blocks.
- Any controls are real Slack `actions` blocks.
- Button labels have no emoji and no "Further actions" heading.
- Candidate details include the fields required by the automation instructions.
- Full copyable IDs are used where the user needs console lookup.
- No fake button text appears in normal mrkdwn.
- No double-asterisk bold.
- No alarmist wording unsupported by evidence.

## When to deviate

Use plain conversational mrkdwn for follow-up questions inside an existing Slack thread when
the user is narrowing or clarifying an earlier answer. Switch back to structured blocks only
when the user asks for a fresh audit, raw inventory, table, or button-style follow-up.
