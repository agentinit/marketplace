# AgentInit Marketplace

Default marketplace for [agentinit](https://github.com/agentinit/agentinit) — skills, MCP servers, and rules for AI coding agents.

## Structure

```
skills/       Reusable agent skills (SKILL.md + supporting files)
mcps/         MCP server configurations (.mcp.json)
rules/        Rule templates for agent configuration
```

## Adding a skill

Create a directory under `skills/` with a `SKILL.md` file containing YAML frontmatter:

```yaml
---
name: my-skill
description: What this skill does
keywords: [keyword1, keyword2]
user_invocable: true
---

# Skill instructions here...
```

## Installing from this marketplace

```bash
agentinit plugins search                        # list all available items
agentinit plugins install agentinit/<name>       # install a skill/mcp/rule
```
