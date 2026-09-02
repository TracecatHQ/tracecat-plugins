# Tracecat agent plugins

Tracecat's public-facing agent package for working with the Tracecat MCP server and platform.

The package at `plugins/tracecat/` follows the Agent Plugins v1 layout and also carries native manifests for Codex and Claude Code. It contains one Tracecat plugin whose skills disclose domain guidance progressively:

```text
plugins/tracecat/
├── plugin.json                             # Agent Plugins v1
├── mcp.json                                # portable Tracecat MCP connection
├── .codex-plugin/plugin.json               # Codex metadata
├── .claude-plugin/plugin.json              # Claude Code metadata
├── .mcp.json                               # native Codex and Claude MCP config
└── skills/
    ├── tracecat-mcp/                       # connect, route, navigate safely
    ├── tracecat-automation-best-practices/ # workflow, table, run-python, preset authoring
    ├── tracecat-slackbot-best-practices/   # Slack-facing automations and chatops
    ├── tracecat-workspace-chat/            # in-product tool and local-docs adapter
    └── tracecat-manage-skills/             # transfer a skill directory over MCP
```

Every skill carries an `agents/openai.yaml` interface stub for Codex, and pushes detail into its
own `references/` directory so agents load it only when the task calls for it. `tracecat-mcp` is
the entry point: it covers connection and tool routing, and hands off to the domain skills.

Three of these skills are also consumed by Tracecat itself. The in-product Workspace Chat copilot
stages `tracecat-workspace-chat`, `tracecat-automation-best-practices`, and
`tracecat-slackbot-best-practices` from this repository. The Tracecat application image adds the
matching product documentation under the adapter's `references/docs/` directory at build time, so
this repository remains the single authoring home for the skills without duplicating product docs.

## Install

The repository currently requires access to the private `TracecatHQ/tracecat-plugins` repository.

### Codex

```bash
codex plugin marketplace add https://github.com/TracecatHQ/tracecat-plugins.git
codex plugin add tracecat@tracecat
```

### Claude Code

Run these commands inside Claude Code:

```text
/plugin marketplace add TracecatHQ/tracecat-plugins
/plugin install tracecat@tracecat
```

### Agent Plugins v1 clients

Install or load the `plugins/tracecat/` directory from this repository using the client's Git or local-directory flow. Agent Plugins v1 standardizes the package format, not a universal installation command.

The bundled MCP configuration targets Tracecat Cloud at `https://platform.tracecat.com/mcp`. Self-hosted users should override the URL in their client configuration.

## Updates

Marketplace installations retain their Git source. Claude Code can apply marketplace and plugin updates automatically when its auto-update setting is enabled. Current Codex clients refresh the marketplace and then reinstall from the new snapshot:

```bash
codex plugin marketplace upgrade tracecat
codex plugin add tracecat@tracecat
```

Every released change must bump all three plugin manifests together.

## Validate

```bash
python3 -m unittest discover -s tests
python3 scripts/validate_manifests.py
claude plugin validate --strict plugins/tracecat
claude plugin validate --strict .
```

The repository CI validates the Agent Plugins schemas and checks that the universal, Codex, and Claude manifests share the same name and version.
