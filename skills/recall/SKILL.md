---
name: recall
description: Search and recall information from previous coding agent sessions (Claude Code, Codex, Gemini CLI, OpenCode). Use when the user asks to recall, remember, or search past sessions for relevant context, code, decisions, or conversations.
keywords: [recall, remember, sessions, history, past, previous, context, search sessions]
user_invocable: true
allowed-tools:
  - Bash
  - Agent
---

# Recall — Search Previous Agent Sessions

Helper script: `~/.claude/skills/recall/recall.py`

Supported engines: **Claude Code** (CC), **Codex** (CX), **Gemini CLI** (GM), **OpenCode** (OC)

## Modes

### 1. `list` — Browse recent sessions (cheapest)
Shows engine, date, project, first user message as title, session ID.
```bash
python3 ~/.claude/skills/recall/recall.py list                         # all engines, last 20
python3 ~/.claude/skills/recall/recall.py list -e claude               # Claude Code only
python3 ~/.claude/skills/recall/recall.py list -e codex -p myproject   # Codex, filter by project
python3 ~/.claude/skills/recall/recall.py list -n 50                   # more results
```

### 2. `overview` — Session arc (token-efficient, cached)
Samples beginning + middle + end of a session to show its direction without reading everything.
Overviews are **cached in SQLite** (`~/.claude/skills/recall/cache.db`) for instant repeated access. Cache is automatically invalidated when the session file changes (mtime comparison).
```bash
python3 ~/.claude/skills/recall/recall.py overview <session_id>
python3 ~/.claude/skills/recall/recall.py overview <session_id> -n 5       # 5 messages per section
python3 ~/.claude/skills/recall/recall.py overview <session_id> --no-cache # force regeneration
```

### 3. `full` — Complete conversation text (no tool calls/thinking/system)
Pure user messages and assistant text responses only. Use when you need the actual content.
```bash
python3 ~/.claude/skills/recall/recall.py full <session_id>
python3 ~/.claude/skills/recall/recall.py full <session_id> -n 30      # first 30 messages only
```

### 4. `cache` — Manage overview cache
```bash
python3 ~/.claude/skills/recall/recall.py cache stats   # show entry count / size
python3 ~/.claude/skills/recall/recall.py cache clear   # delete cache.db (always safe)
```

### 5. `search` — Keyword search across sessions
All terms must match (AND logic). Sorted by most recent first. Searches across all engines by default.
```bash
python3 ~/.claude/skills/recall/recall.py search "docker traefik"
python3 ~/.claude/skills/recall/recall.py search "auth" -e claude -p router
python3 ~/.claude/skills/recall/recall.py search "wireguard" -n 30
```

## Workflow

### Default behaviors

1. **Auto-filter by current project**: When the user does not specify a project, automatically add `-p <current_project_name>` (derived from the working directory basename). Only omit `-p` when the user explicitly asks for "all projects" or "all sessions".
2. **Auto-escalate to `overview`**: When the user asks for a "summary" of sessions, don't stop at `list`. After listing, run `overview` on each session to provide actual content summaries — not just titles. Batch overview calls in the subagent to keep it efficient.

**IMPORTANT: Always delegate recall work to a subagent** using the Agent tool with `model: "haiku"` (cheap and fast — this is just log reading, no reasoning needed). This keeps session log data out of the main context window and saves tokens/cost.

Example delegation:
```
Agent(
  subagent_type="general-purpose",
  model="haiku",
  description="Recall past VPN sessions",
  prompt="Use the recall helper script at ~/.claude/skills/recall/recall.py to find information about VPN tunnel setup. Steps: 1) Run `python3 ~/.claude/skills/recall/recall.py search 'wireguard vpn'` to find relevant sessions. 2) For promising matches, run `python3 ~/.claude/skills/recall/recall.py overview <session_id>` to get context. 3) If you need full details, use the `full` mode. Summarize your findings concisely: what was done, what decisions were made, what the current state is."
)
```

When delegating to a subagent:
1. Include the full path to the script in the prompt
2. Tell the subagent which mode(s) to use and in what order
3. Tell it what specific information to look for
4. Ask it to **summarize concisely** — don't dump raw logs back

### Mode escalation within the subagent

1. **Start with `search`** to find relevant sessions by keyword
2. **Use `overview`** on promising session IDs to understand the arc
3. **Use `full`** only if the subagent needs actual conversation details
4. **Use `list`** when no keywords are known — browse recent sessions first

## Flags

- `-e, --engine ENGINE` — filter by engine: `claude`, `codex`, `gemini`, `opencode` (omit for all)
- `-p, --project PATTERN` — filter sessions by project directory name (substring match, case-insensitive)
- `-n, --limit N` — limit results/messages

The `--engine` flag can go before or after the mode:
```bash
python3 recall.py -e codex list
python3 recall.py list -e codex
```

## What gets stripped (all engines)

- Tool use blocks and tool results
- Thinking/reasoning blocks
- System/developer messages
- Metadata entries (isMeta, environment context, AGENTS.md instructions)
- Subagent/sidechain messages

Only **user text** and **assistant text responses** are shown.

## Engine session locations

| Engine | Location | Format |
|--------|----------|--------|
| Claude Code | `~/.claude/projects/*/` | JSONL |
| Codex | `~/.codex/sessions/` | JSONL |
| Gemini CLI | `~/.gemini/tmp/{hash}/chats/` | JSON |
| OpenCode | `~/.local/share/opencode/opencode.db` | SQLite |

## Tips

- **Always use a subagent** — session logs are large; keep them out of main context
- Session IDs support prefix matching — you can use just the first few chars
- `list` reads only metadata — fast even with thousands of sessions
- Use `-e` to narrow to a specific engine when you know which agent was used
- For broad searches across many projects, spawn multiple subagents in parallel (one per engine)
