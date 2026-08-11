# Tracecat MCP connection

## Tracecat Cloud

The bundled endpoint is:

```text
https://platform.tracecat.com/mcp
```

Use the client's OAuth flow when supported. Agent Plugins v1 intentionally leaves OAuth discovery, interaction, and credential storage to the client, so the plugin does not contain credentials or authorization headers.

If a client does not support MCP OAuth, configure a Tracecat personal access token in that client's secure MCP settings as an `Authorization: Bearer ...` header. Never commit that header to this repository or place it in a skill file.

## Self-hosted Tracecat

Override the Tracecat MCP URL in the client's local configuration with the deployment's `/mcp` endpoint. The portable and native manifests intentionally use Tracecat Cloud as their safe default and do not interpolate environment variables into remote URLs.

## Connection checks

After connecting:

1. Call `list_workspaces`.
2. Complete the client's authentication prompt if one appears.
3. If no workspace is visible, verify account access and the Tracecat Agent Add-ons entitlement rather than guessing an ID.
4. Treat authorization failures as connection or account configuration failures, not as malformed plugin configuration.
