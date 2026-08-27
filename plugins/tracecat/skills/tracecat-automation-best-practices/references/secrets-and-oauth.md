# Secrets and OAuth tokens

Two kinds of credential resolve through the same `SECRETS` context, with different naming
rules. Getting the name wrong is the single most common validation failure in an otherwise
correct workflow, because the expression looks right.

## Workspace secrets

A secret you store under Credentials is referenced as `${{ SECRETS.<name>.<KEY> }}`, where
`<name>` is the secret's name and `<KEY>` is one of its keys. Secrets are scoped to an
environment (`default` unless the action overrides it), resolve at execution time, and are
never rendered into an agent's prompt by the `ai.preset_agent` injection path.

```yaml
headers:
  X-API-Key: ${{ SECRETS.crowdstrike.CROWDSTRIKE_API_KEY }}
```

## OAuth tokens

An OAuth integration's token is exposed as a synthetic secret whose name and key are both
**derived from the provider ID** — you do not choose either one.

- The secret **name** is `<provider_id>_oauth`.
- The secret **key** is `<PROVIDER_ID_UPPER>_USER_TOKEN` for the `authorization_code` grant, or
  `<PROVIDER_ID_UPPER>_SERVICE_TOKEN` for the `client_credentials` grant. `<PROVIDER_ID_UPPER>`
  is the complete provider ID uppercased, keeping its underscores and any numeric suffix.

This is enforced, not conventional. The expression validator parses any secret name ending in
`_oauth`, derives the expected prefix from the provider ID, and rejects anything else with
`OAuth token must be <PREFIX>_SERVICE_TOKEN or <PREFIX>_USER_TOKEN`. A `SLACK_TOKEN` or a
`slack_oauth.ACCESS_TOKEN` fails validation before the workflow ever runs.

Single grant type — a built-in `authorization_code` provider:

```yaml
headers:
  Authorization: "Bearer ${{ SECRETS.google_drive_oauth.GOOGLE_DRIVE_USER_TOKEN }}"
```

When the workspace may have connected either grant type for the same provider, fall back
across both:

```yaml
headers:
  Authorization: "Bearer ${{ SECRETS.azure_log_analytics_oauth.AZURE_LOG_ANALYTICS_USER_TOKEN || SECRETS.azure_log_analytics_oauth.AZURE_LOG_ANALYTICS_SERVICE_TOKEN }}"
```

**Caveat: the validator walks both sides of a `||`.** It does not short-circuit the way the
runtime does, so every branch is checked against what is actually connected. A same-provider
two-grant fallback like the one above is safe — both branches name the same provider, and the
validator is checking the token naming rule. A fallback across two *different* providers
(`${{ SECRETS.okta_oauth.OKTA_USER_TOKEN || SECRETS.entra_oauth.ENTRA_USER_TOKEN }}`) can raise
a validation error when only one of them is connected, even though the expression would resolve
correctly at runtime. Pick one provider per expression, and branch on `run_if` if you genuinely
need two.

## Provider IDs

The expression needs the provider's **exact ID**, never its display name.

- **Built-in providers** have stable lowercase IDs assigned by Tracecat, with underscores
  between words: `slack`, `google_drive`, `microsoft_sentinel`.
- **Custom providers** derive their ID from the provider name (or the requested ID), slugified
  with underscores and prefixed `custom_`. `My Security API` becomes `custom_my_security_api`,
  so the key is `CUSTOM_MY_SECURITY_API_SERVICE_TOKEN`. If that ID is already taken for the
  same grant type, Tracecat appends `_1`, `_2`, and so on — and the suffix is part of the key.
- The `custom_mcp_` namespace is **reserved** for the MCP OAuth discovery pipeline. A custom
  provider whose slug would land there is renamed to `custom_oauth_<name>` instead.

**Call `list_integrations` to read the exact provider ID before writing the expression.** Never
guess one from a display name, and never assume a vendor's marketing name matches its slug.

## Rules

- Reference secrets; do not read, print, echo, or persist their values. There is no legitimate
  reason for a workflow to return a token in an action output.
- Non-secret configuration — base URLs, tenant IDs, project IDs, queue names — belongs in
  `${{ VARS.<name>.<key> }}`, not in a secret.
- Prefer `ai.preset_agent` when an agent needs a credential: it injects secrets server-side, so
  the model never sees the value. `ai.agent` and `ai.action` resolve expressions into arguments
  the model can read.
