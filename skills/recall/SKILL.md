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

Use the bundled `recall.py` from the installed skill directory.

Common AgentInit install paths:
- Project install: `.agents/skills/recall/recall.py`
- Global Claude Code install: `~/.claude/skills/recall/recall.py`
- Global Codex install: `~/.codex/skills/recall/recall.py`
- Global Gemini install: `~/.gemini/skills/recall/recall.py`

Examples below use `<recall.py>` as a stand-in for the actual installed path.

Supported engines: **Claude Code** (CC), **Codex** (CX), **Gemini CLI** (GM), **OpenCode** (OC)

## Modes

### 1. `list` — Browse recent sessions (cheapest)
Shows engine, date, project, first user message as title, session ID.
```bash
python3 <recall.py> list                         # all engines, last 20
python3 <recall.py> list -e claude               # Claude Code only
python3 <recall.py> list -e codex -p myproject   # Codex, filter by project
python3 <recall.py> list -n 50                   # more results
```

### 2. `overview` — Session arc (token-efficient, cached)
Samples beginning + middle + end of a session to show its direction without reading everything.
Overviews are **cached in SQLite** in the user cache directory outside the repo worktree.
- macOS default: `~/Library/Caches/agentinit/recall/cache.db`
- Linux default: `$XDG_CACHE_HOME/agentinit/recall/cache.db` or `~/.cache/agentinit/recall/cache.db`
- Override: `AGENTINIT_RECALL_CACHE_DB=/custom/path/cache.db`

Cache is automatically invalidated when the source session changes.
```bash
python3 <recall.py> overview <session_id>
python3 <recall.py> overview <session_id> -n 5       # 5 messages per section
python3 <recall.py> overview <session_id> --no-cache # force regeneration
```

### 3. `full` — Complete conversation text (no tool calls/thinking/system)
Pure user messages and assistant text responses only. Use when you need the actual content.
```bash
python3 <recall.py> full <session_id>
python3 <recall.py> full <session_id> -n 30      # first 30 messages only
```

### 4. `cache` — Manage overview cache
```bash
python3 <recall.py> cache stats   # show entry count / size
python3 <recall.py> cache clear   # delete cache.db (always safe)
```

### 5. `search` — Keyword search across sessions
All terms must match (AND logic). Sorted by most recent first. Searches across all engines by default.
```bash
python3 <recall.py> search "docker traefik"
python3 <recall.py> search "auth" -e claude -p router
python3 <recall.py> search "wireguard" -n 30
```

## Workflow

### Default behaviors

1. **Auto-filter by current project**: When the user does not specify a project, automatically add `-p <current_project_name>` (derived from the working directory basename). Only omit `-p` when the user explicitly asks for "all projects" or "all sessions".
2. **Auto-escalate to `overview`**: When the user asks for a "summary" of sessions, don't stop at `list`. After listing, run `overview` on each session to provide actual content summaries — not just titles. Batch overview calls in the subagent to keep it efficient.

Project filtering works best for Claude Code, Codex, and OpenCode because those backends expose a cwd/worktree. Gemini CLI sessions currently expose only a `projectHash`, so `-p` matches that hash label rather than the original project directory.

**IMPORTANT: Prefer delegating recall work to a cheap subagent** when the current agent supports delegation. This keeps raw session logs out of the main context window and saves tokens/cost.

Example delegation prompt:
```
Use the recall helper script at <recall.py> to find information about VPN tunnel setup.
Steps:
1. Run `python3 <recall.py> search 'wireguard vpn'` to find relevant sessions.
2. For promising matches, run `python3 <recall.py> overview <session_id>` to get context.
3. If you need full details, use the `full` mode.
Summarize the findings concisely: what was done, what decisions were made, and what the current state is.
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
- Gemini note: `-p` filters by the Gemini project hash label because Gemini session files do not expose the original cwd

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
