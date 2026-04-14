#!/usr/bin/env python3
"""
recall.py — Agent-agnostic session log reader.

Supports: Claude Code, Codex, Gemini CLI, OpenCode

Modes:
  list     — List recent sessions with title/date/project (cheap metadata scan)
  overview — Sample beginning + middle + end of a session (token-efficient arc)
  full     — Full conversation, text only (no tools/thinking/system)
  search   — Keyword search across sessions
  cache    — Manage cached overviews

Usage:
  python3 recall.py list [--engine ENGINE] [--project PATTERN] [--all-projects] [--limit N]
  python3 recall.py overview <session_id> [--engine ENGINE] [--project PATTERN] [--all-projects]
  python3 recall.py full <session_id> [--engine ENGINE] [--project PATTERN] [--all-projects] [--limit N]
  python3 recall.py search <query> [--engine ENGINE] [--project PATTERN] [--all-projects] [--limit N]
  python3 recall.py cache {stats,clear}
"""

import json, os, sys, glob, argparse, re, sqlite3, time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


# ─── Constants ───────────────────────────────────────────────────────────────

ENGINES = ("claude", "codex", "gemini", "opencode")

CLAUDE_DIR = os.environ.get("CLAUDE_PROJECTS_DIR", os.path.expanduser("~/.claude/projects"))
CODEX_DIR = os.environ.get("CODEX_SESSIONS_DIR", os.path.expanduser("~/.codex/sessions"))
GEMINI_DIR = os.environ.get("CCBOX_GEMINI_DIR", os.path.expanduser("~/.gemini"))
OPENCODE_DB = os.environ.get(
    "CCBOX_OPENCODE_DB_PATH",
    os.path.expanduser(
        os.path.join(os.environ.get("XDG_DATA_HOME", "~/.local/share"), "opencode", "opencode.db")
    ),
)

# Codex metadata prefixes to skip in user messages
CODEX_META_PREFIXES = (
    "# AGENTS.md",
    "<environment_context>",
    "<INSTRUCTIONS>",
    "<skill>",
    "<turn_aborted>",
    "<permissions",
)

ENGINE_LABELS = {"claude": "CC", "codex": "CX", "gemini": "GM", "opencode": "OC"}
SEARCH_NOISE_PATTERNS = (
    "use recall skill",
    "recall helper script",
    "global recall searches were run",
    "only one prior session matched",
    "use the recall helper script",
    "run broad searches across all projects",
    "run `python3 <recall.py> search",
    "steps:\n1. run",
)


def _get_default_cache_root() -> str:
    xdg_cache_home = os.environ.get("XDG_CACHE_HOME")
    if xdg_cache_home:
        return os.path.expanduser(xdg_cache_home)
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Caches")
    return os.path.expanduser("~/.cache")


def get_cache_db_path() -> str:
    override = os.environ.get("AGENTINIT_RECALL_CACHE_DB")
    if override:
        return os.path.expanduser(override)
    return os.path.join(_get_default_cache_root(), "agentinit", "recall", "cache.db")


# ─── SessionFile ─────────────────────────────────────────────────────────────

@dataclass
class SessionFile:
    engine: str
    session_id: str
    project: str
    filepath: str
    mtime: float
    cwd: str | None = None


# ─── Project name helpers ────────────────────────────────────────────────────

def _decode_claude_project(encoded: str) -> str:
    parts = encoded.lstrip("-").split("-")
    meaningful = [p for p in parts if p and p not in ("Users",)]
    if len(meaningful) >= 2:
        return "/".join(meaningful[-2:])
    return "/".join(meaningful) if meaningful else encoded


def _project_from_cwd(cwd: str) -> str:
    parts = Path(cwd).parts
    return "/".join(parts[-2:]) if len(parts) >= 2 else (parts[-1] if parts else cwd)


# ─── Text extraction ─────────────────────────────────────────────────────────

def _extract_claude_text(entry: dict) -> str | None:
    msg = entry.get("message", {})
    content = msg.get("content", "")
    if isinstance(content, str):
        return content if content.strip() else None
    if isinstance(content, list):
        texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        return "\n".join(texts) if texts else None
    return None


def _extract_codex_text(payload: dict) -> str | None:
    content = payload.get("content", [])
    if not isinstance(content, list):
        return None
    texts = [b.get("text", "") for b in content
             if isinstance(b, dict) and b.get("type") in ("input_text", "output_text")]
    return "\n".join(texts) if texts else None


def _is_codex_meta(text: str) -> bool:
    stripped = text.strip()
    return any(stripped.startswith(p) for p in CODEX_META_PREFIXES)


# ─── Session scanners ────────────────────────────────────────────────────────

def _get_claude_sessions(project_pattern: str | None = None) -> list[SessionFile]:
    if not os.path.isdir(CLAUDE_DIR):
        return []
    if project_pattern:
        all_dirs = glob.glob(os.path.join(CLAUDE_DIR, "*"))
        dirs = [d for d in all_dirs if project_pattern.lower() in os.path.basename(d).lower()]
        files = []
        for d in dirs:
            files.extend(glob.glob(os.path.join(d, "*.jsonl")))
    else:
        files = glob.glob(os.path.join(CLAUDE_DIR, "*", "*.jsonl"))

    sessions = []
    for f in files:
        key = os.path.basename(os.path.dirname(f))
        sid = os.path.basename(f).replace(".jsonl", "")
        sessions.append(SessionFile("claude", sid, _decode_claude_project(key), f, os.path.getmtime(f)))
    return sessions


def _get_codex_sessions(project_pattern: str | None = None) -> list[SessionFile]:
    if not os.path.isdir(CODEX_DIR):
        return []
    sessions = []
    for root, _dirs, fnames in os.walk(CODEX_DIR):
        for fname in fnames:
            if not fname.endswith(".jsonl"):
                continue
            filepath = os.path.join(root, fname)
            try:
                with open(filepath, "r") as f:
                    meta = json.loads(f.readline())
                if meta.get("type") != "session_meta":
                    continue
                p = meta["payload"]
                sid, cwd = p["id"], p.get("cwd", "")
                project = _project_from_cwd(cwd) if cwd else sid[:12]
            except (json.JSONDecodeError, KeyError, IOError):
                continue
            if project_pattern and project_pattern.lower() not in project.lower() \
                    and (not cwd or project_pattern.lower() not in cwd.lower()):
                continue
            sessions.append(SessionFile("codex", sid, project, filepath, os.path.getmtime(filepath), cwd))
    return sessions


_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _get_gemini_sessions(project_pattern: str | None = None) -> list[SessionFile]:
    tmp = os.path.join(GEMINI_DIR, "tmp")
    if not os.path.isdir(tmp):
        return []
    sessions = []
    for dname in os.listdir(tmp):
        if not _HEX64.match(dname):
            continue
        chats = os.path.join(tmp, dname, "chats")
        if not os.path.isdir(chats):
            continue
        for fname in os.listdir(chats):
            if not fname.startswith("session-") or not fname.endswith(".json"):
                continue
            filepath = os.path.join(chats, fname)
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)
                sid = data.get("sessionId", fname[8:-5])  # strip session- and .json
                project_hash = data.get("projectHash", dname)
                proj_label = f"gemini/{project_hash[:12]}"
            except (json.JSONDecodeError, IOError):
                continue
            if project_pattern and project_pattern.lower() not in proj_label.lower():
                continue
            sessions.append(SessionFile("gemini", sid, proj_label, filepath, os.path.getmtime(filepath)))
    return sessions


def _get_opencode_sessions(project_pattern: str | None = None) -> list[SessionFile]:
    if not os.path.isfile(OPENCODE_DB):
        return []
    try:
        conn = sqlite3.connect(f"file:{OPENCODE_DB}?mode=ro", uri=True)
        rows = conn.execute(
            "SELECT s.id, s.title, s.directory, s.time_created, "
            "COALESCE(MAX(m.time_created), s.time_created) AS last_activity, p.worktree "
            "FROM session s "
            "JOIN project p ON p.id = s.project_id "
            "LEFT JOIN message m ON m.session_id = s.id "
            "WHERE s.time_archived IS NULL "
            "GROUP BY s.id, s.title, s.directory, s.time_created, p.worktree "
            "ORDER BY last_activity DESC"
        ).fetchall()
        conn.close()
    except (sqlite3.Error, IOError):
        return []

    sessions = []
    for sid, title, directory, time_created, last_activity, worktree in rows:
        cwd = worktree or directory or ""
        project = _project_from_cwd(cwd) if cwd else (title or sid[:12])
        if project_pattern and project_pattern.lower() not in project.lower() \
                and (not cwd or project_pattern.lower() not in cwd.lower()):
            continue
        mtime_ms = last_activity or time_created or 0
        mtime = mtime_ms / 1000.0
        sessions.append(SessionFile("opencode", sid, project, OPENCODE_DB, mtime, cwd))
    return sessions


def get_all_sessions(engine: str | None = None, project: str | None = None) -> list[SessionFile]:
    scanners = {
        "claude": _get_claude_sessions,
        "codex": _get_codex_sessions,
        "gemini": _get_gemini_sessions,
        "opencode": _get_opencode_sessions,
    }
    if engine:
        fn = scanners.get(engine)
        if not fn:
            print(f"Unknown engine: {engine}. Available: {', '.join(ENGINES)}", file=sys.stderr)
            return []
        return sorted(fn(project), key=lambda s: s.mtime, reverse=True)

    all_s = []
    for fn in scanners.values():
        all_s.extend(fn(project))
    return sorted(all_s, key=lambda s: s.mtime, reverse=True)


# ─── Message parsers ─────────────────────────────────────────────────────────

def _parse_claude(filepath: str) -> list[dict]:
    messages = []
    with open(filepath, "r") as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
            except (json.JSONDecodeError, ValueError):
                continue
            if entry.get("type") not in ("user", "assistant"):
                continue
            if entry.get("isMeta", False) or entry.get("isSidechain", False):
                continue
            text = _extract_claude_text(entry)
            if text:
                messages.append({"type": entry["type"], "timestamp": entry.get("timestamp", ""), "text": text})
    return messages


def _parse_codex(filepath: str) -> list[dict]:
    messages = []
    with open(filepath, "r") as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
            except (json.JSONDecodeError, ValueError):
                continue
            if entry.get("type") != "response_item":
                continue
            payload = entry.get("payload", {})
            if payload.get("type") != "message":
                continue
            role = payload.get("role", "")
            if role not in ("user", "assistant"):
                continue
            text = _extract_codex_text(payload)
            if not text:
                continue
            if role == "user" and _is_codex_meta(text):
                continue
            messages.append({"type": "user" if role == "user" else "assistant",
                             "timestamp": entry.get("timestamp", ""), "text": text})
    return messages


def _parse_gemini(filepath: str) -> list[dict]:
    try:
        with open(filepath, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return []
    messages = []
    for msg in data.get("messages", []):
        t = msg.get("type", "")
        content = msg.get("content", "")
        if t == "user":
            mt = "user"
        elif t == "gemini":
            mt = "assistant"
        else:
            continue
        if content and isinstance(content, str) and content.strip():
            messages.append({"type": mt, "timestamp": msg.get("timestamp", ""), "text": content})
    return messages


def _parse_opencode(session: SessionFile) -> list[dict]:
    if not os.path.isfile(OPENCODE_DB):
        return []
    try:
        conn = sqlite3.connect(f"file:{OPENCODE_DB}?mode=ro", uri=True)
        msg_rows = conn.execute(
            "SELECT id, time_created, data FROM message WHERE session_id = ? ORDER BY time_created",
            (session.session_id,),
        ).fetchall()
        part_rows = conn.execute(
            "SELECT message_id, data FROM part WHERE session_id = ? ORDER BY rowid",
            (session.session_id,),
        ).fetchall()
        conn.close()
    except (sqlite3.Error, IOError):
        return []

    parts_by_msg: dict[str, list[dict]] = {}
    for mid, pdata in part_rows:
        parts_by_msg.setdefault(mid, [])
        try:
            parts_by_msg[mid].append(json.loads(pdata) if isinstance(pdata, str) else pdata)
        except (json.JSONDecodeError, ValueError):
            pass

    messages = []
    for mid, tc, dstr in msg_rows:
        try:
            md = json.loads(dstr) if isinstance(dstr, str) else dstr
        except (json.JSONDecodeError, ValueError):
            continue
        role = md.get("role", "")
        if role not in ("user", "assistant"):
            continue
        texts = [p.get("text", "") or p.get("content", "")
                 for p in parts_by_msg.get(mid, []) if p.get("type") == "text"]
        text = "\n".join(t for t in texts if t)
        if not text:
            continue
        ts = ""
        if tc:
            try:
                ts = datetime.fromtimestamp(tc / 1000.0, tz=timezone.utc).isoformat()
            except (ValueError, OSError):
                pass
        messages.append({"type": role, "timestamp": ts, "text": text})
    return messages


def parse_messages(session: SessionFile) -> list[dict]:
    if session.engine == "claude":
        return _parse_claude(session.filepath)
    if session.engine == "codex":
        return _parse_codex(session.filepath)
    if session.engine == "gemini":
        return _parse_gemini(session.filepath)
    if session.engine == "opencode":
        return _parse_opencode(session)
    return []


# ─── Session metadata helpers ────────────────────────────────────────────────

def _get_timestamp(session: SessionFile) -> str:
    try:
        if session.engine == "claude":
            with open(session.filepath, "r") as f:
                for line in f:
                    e = json.loads(line.strip())
                    if e.get("timestamp"):
                        return e["timestamp"]
        elif session.engine == "codex":
            with open(session.filepath, "r") as f:
                return json.loads(f.readline()).get("payload", {}).get("timestamp", "")
        elif session.engine == "gemini":
            with open(session.filepath, "r") as f:
                return json.load(f).get("startTime", "")
        elif session.engine == "opencode" and session.mtime:
            return datetime.fromtimestamp(session.mtime, tz=timezone.utc).isoformat()
    except Exception:
        pass
    return ""


def _get_title(session: SessionFile) -> str:
    try:
        if session.engine == "claude":
            with open(session.filepath, "r") as f:
                for line in f:
                    e = json.loads(line.strip())
                    if e.get("type") == "user" and not e.get("isMeta"):
                        t = _extract_claude_text(e)
                        if t:
                            return t.split("\n")[0][:80]
        elif session.engine == "codex":
            with open(session.filepath, "r") as f:
                n = 0
                for line in f:
                    n += 1
                    if n > 250:
                        break
                    e = json.loads(line.strip())
                    if e.get("type") != "response_item":
                        continue
                    p = e.get("payload", {})
                    if p.get("type") == "message" and p.get("role") == "user":
                        t = _extract_codex_text(p)
                        if t and not _is_codex_meta(t):
                            return t.split("\n")[0][:80]
        elif session.engine == "gemini":
            with open(session.filepath, "r") as f:
                data = json.load(f)
            for msg in data.get("messages", []):
                if msg.get("type") == "user":
                    c = msg.get("content", "")
                    if c and isinstance(c, str):
                        return c.split("\n")[0][:80]
        elif session.engine == "opencode":
            conn = sqlite3.connect(f"file:{OPENCODE_DB}?mode=ro", uri=True)
            row = conn.execute("SELECT title FROM session WHERE id = ?", (session.session_id,)).fetchone()
            conn.close()
            if row and row[0]:
                return row[0][:80]
    except Exception:
        pass
    return ""


# ─── Helpers ─────────────────────────────────────────────────────────────────

def format_ts(ts_str: str) -> str:
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        return ts_str[:16] if ts_str else "?"


def find_session(session_id: str, engine: str | None = None, project: str | None = None) -> SessionFile | None:
    for s in get_all_sessions(engine, project):
        if s.session_id == session_id or s.session_id.startswith(session_id):
            return s
    return None


def _resolve_project(args) -> str | None:
    if getattr(args, "all_projects", False):
        return None
    return getattr(args, "project", None)


def _normalize_search_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _text_is_noise(text: str) -> bool:
    normalized = _normalize_search_text(text)
    return any(pattern in normalized for pattern in SEARCH_NOISE_PATTERNS)


def _term_regex(term: str) -> re.Pattern[str]:
    pieces = [re.escape(part) for part in term.split()]
    pattern = r"\b" + r"\s+".join(pieces) + r"\b"
    return re.compile(pattern, re.IGNORECASE)


def _term_positions(text: str, query_terms: list[str]) -> list[int]:
    positions = []
    for term in query_terms:
        match = _term_regex(term).search(text)
        if match:
            positions.append(match.start())
    return positions


def _make_snippet(text: str, query_terms: list[str], *, max_chars: int = 400) -> str:
    positions = _term_positions(text, query_terms)
    if positions:
        start = max(0, min(positions) - 100)
        end = min(len(text), start + max_chars)
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(text) else ""
        return prefix + text[start:end] + suffix
    trimmed = text[:max_chars]
    return trimmed + ("..." if len(text) > max_chars else "")


def _score_match(session: SessionFile, title: str, text: str, query: str, query_terms: list[str]) -> tuple[int, bool]:
    normalized_query = _normalize_search_text(query)
    text_lower = text.lower()
    title_lower = title.lower()
    project_lower = session.project.lower()
    title_and_text = f"{title}\n{text}"

    exact_query = bool(normalized_query and _term_regex(normalized_query).search(_normalize_search_text(text)))
    all_terms_in_text = all(_term_regex(term).search(text_lower) for term in query_terms)
    all_terms_in_title = bool(title_lower) and all(_term_regex(term).search(title_lower) for term in query_terms)
    if not (all_terms_in_text or all_terms_in_title or exact_query):
        return 0, False

    score = 0
    if exact_query:
        score += 120
    if all_terms_in_text:
        score += 80
    if all_terms_in_title:
        score += 60
    score += sum(20 for term in query_terms if _term_regex(term).search(title_lower))
    score += sum(10 for term in query_terms if _term_regex(term).search(project_lower))
    score += min(len(query_terms), 6) * 3
    if not _text_is_noise(title_and_text):
        score += 15
    return score, True


# ─── MODE: list ──────────────────────────────────────────────────────────────

def cmd_list(args):
    sessions = get_all_sessions(args.engine, _resolve_project(args))
    limit = args.limit or 20

    print(f"{'#':>3}  {'Eng':4}  {'Date':16}  {'Project':30}  Title")
    print(f"{'─'*3}  {'─'*4}  {'─'*16}  {'─'*30}  {'─'*50}")

    count = 0
    for session in sessions:
        if count >= limit:
            break
        title = _get_title(session)
        if not title:
            continue
        count += 1
        date_str = format_ts(_get_timestamp(session))
        eng = ENGINE_LABELS.get(session.engine, "??")
        print(f"{count:>3}  {eng:4}  {date_str:16}  {session.project:30}  {title}")
        print(f"     {'':4}  {'':16}  {'':30}  sid:{session.session_id}")

    if count == 0:
        print("No sessions found.")


# ─── Overview cache ──────────────────────────────────────────────────────────

def _get_cache_conn():
    cache_db = get_cache_db_path()
    Path(cache_db).expanduser().parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(cache_db)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS overview_cache (
        engine      TEXT NOT NULL,
        session_id  TEXT NOT NULL,
        sample_size INTEGER NOT NULL,
        mtime       REAL NOT NULL,
        overview    TEXT NOT NULL,
        cached_at   REAL NOT NULL,
        PRIMARY KEY (engine, session_id, sample_size)
    )""")
    return conn


def _cache_get(engine: str, session_id: str, sample_size: int, current_mtime: float) -> str | None:
    try:
        conn = _get_cache_conn()
        row = conn.execute(
            "SELECT overview, mtime FROM overview_cache WHERE engine=? AND session_id=? AND sample_size=?",
            (engine, session_id, sample_size),
        ).fetchone()
        conn.close()
        if row and row[1] == current_mtime:
            return row[0]
    except (sqlite3.Error, OSError):
        pass
    return None


def _cache_put(engine: str, session_id: str, sample_size: int, mtime: float, overview_text: str):
    try:
        conn = _get_cache_conn()
        conn.execute(
            "INSERT OR REPLACE INTO overview_cache (engine, session_id, sample_size, mtime, overview, cached_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (engine, session_id, sample_size, mtime, overview_text, time.time()),
        )
        conn.commit()
        conn.close()
    except (sqlite3.Error, OSError):
        pass


def _cache_clear():
    cache_db = get_cache_db_path()
    if not os.path.isfile(cache_db):
        print("No cache to clear.")
        return
    os.remove(cache_db)
    # Also remove WAL/SHM files if present
    for suffix in ("-wal", "-shm"):
        p = cache_db + suffix
        if os.path.isfile(p):
            os.remove(p)
    print("Cache cleared.")


def _cache_stats():
    cache_db = get_cache_db_path()
    if not os.path.isfile(cache_db):
        print("No cache exists yet.")
        return
    try:
        conn = _get_cache_conn()
        count = conn.execute("SELECT COUNT(*) FROM overview_cache").fetchone()[0]
        oldest = conn.execute("SELECT MIN(cached_at) FROM overview_cache").fetchone()[0]
        newest = conn.execute("SELECT MAX(cached_at) FROM overview_cache").fetchone()[0]
        conn.close()
    except (sqlite3.Error, OSError) as e:
        print(f"Error reading cache: {e}")
        return
    cache_files = [cache_db, cache_db + "-wal", cache_db + "-shm"]
    size_kb = sum(os.path.getsize(path) for path in cache_files if os.path.isfile(path)) / 1024
    print(f"Cache entries: {count}")
    print(f"Database size: {size_kb:.1f} KB")
    if oldest:
        print(f"Oldest entry:  {datetime.fromtimestamp(oldest).strftime('%Y-%m-%d %H:%M')}")
    if newest:
        print(f"Newest entry:  {datetime.fromtimestamp(newest).strftime('%Y-%m-%d %H:%M')}")


# ─── MODE: overview ──────────────────────────────────────────────────────────

def _generate_overview(session: SessionFile, sample_size: int) -> str | None:
    messages = parse_messages(session)
    if not messages:
        return None

    total = len(messages)

    begin_idx = list(range(min(sample_size, total)))
    mid_idx = list(range((mid_s := total // 2 - sample_size // 2), min(mid_s + sample_size, total))) \
        if total > sample_size * 2 else []
    end_idx = list(range(max(total - sample_size, sample_size), total)) if total > sample_size else []

    seen: set[int] = set()
    all_idx: list[int] = []
    for idx_list in [begin_idx, mid_idx, end_idx]:
        for i in idx_list:
            if i not in seen:
                seen.add(i)
                all_idx.append(i)

    lines: list[str] = []
    eng = ENGINE_LABELS.get(session.engine, "??")
    lines.append(f"Session overview: [{eng}] {session.project}")
    lines.append(f"Total messages: {total}  |  Showing: {len(all_idx)} samples")
    lines.append(f"{'═'*70}\n")

    prev_section = None
    for i in all_idx:
        section = "BEGINNING" if i in begin_idx else ("MIDDLE" if i in set(mid_idx) else "END")
        if section != prev_section:
            if prev_section:
                lines.append(f"\n  {'· · ·':^66}\n")
            lines.append(f"── {section} ({i+1}/{total}) ──")
            prev_section = section

        m = messages[i]
        role = "USER" if m["type"] == "user" else "ASSISTANT"
        lines.append(f"\n[{role}] {format_ts(m['timestamp'])}")
        text = m["text"]
        if len(text) > 500:
            text = text[:500] + " [...]"
        lines.append(text)

    lines.append(f"\n{'═'*70}")
    return "\n".join(lines)


def cmd_overview(args):
    session = find_session(args.session_id, args.engine, _resolve_project(args))
    if not session:
        print(f"Session not found: {args.session_id}")
        sys.exit(1)

    sample_size = args.limit or 3
    no_cache = getattr(args, "no_cache", False)

    if not no_cache:
        cached = _cache_get(session.engine, session.session_id, sample_size, session.mtime)
        if cached is not None:
            print(cached)
            return

    overview = _generate_overview(session, sample_size)
    if overview is None:
        print("No conversation messages found in session.")
        return

    _cache_put(session.engine, session.session_id, sample_size, session.mtime, overview)
    print(overview)


# ─── MODE: full ──────────────────────────────────────────────────────────────

def cmd_full(args):
    session = find_session(args.session_id, args.engine, _resolve_project(args))
    if not session:
        print(f"Session not found: {args.session_id}")
        sys.exit(1)

    messages = parse_messages(session)
    if not messages:
        print("No conversation messages found in session.")
        return

    limit = args.limit or len(messages)
    eng = ENGINE_LABELS.get(session.engine, "??")
    print(f"Session: [{eng}] {session.project}")
    print(f"Messages: {min(limit, len(messages))}/{len(messages)}")
    print(f"{'═'*70}\n")

    for m in messages[:limit]:
        role = "USER" if m["type"] == "user" else "ASSISTANT"
        print(f"[{role}] {format_ts(m['timestamp'])}")
        print(m["text"])
        print()


# ─── MODE: search ────────────────────────────────────────────────────────────

def cmd_search(args):
    query_terms = args.query.lower().split()
    sessions = get_all_sessions(args.engine, _resolve_project(args))
    limit = args.limit or 15
    results = []

    for session in sessions:
        title = _get_title(session)
        best = None

        for m in parse_messages(session):
            score, matched = _score_match(session, title, m["text"], args.query, query_terms)
            if not matched:
                continue
            candidate = {
                "engine": session.engine,
                "project": session.project,
                "session": session.session_id,
                "type": m["type"],
                "timestamp": m["timestamp"],
                "text": m["text"],
                "title": title,
                "score": score,
                "mtime": session.mtime,
                "noise": _text_is_noise(f"{title}\n{m['text']}"),
            }
            if best is None or candidate["score"] > best["score"] or (
                candidate["score"] == best["score"] and candidate["timestamp"] > best["timestamp"]
            ):
                best = candidate

        if best is not None:
            results.append(best)

    results.sort(key=lambda r: (r["noise"], -r["score"], -r["mtime"]))
    results = results[:limit]

    if not results:
        print(f"No matches for: {args.query}")
        return

    print(f"Found {len(results)} session matches for: {args.query}\n")

    for i, r in enumerate(results, 1):
        role = "USER" if r["type"] == "user" else "ASSISTANT"
        eng = ENGINE_LABELS.get(r["engine"], "??")
        print(f"[{i}] {role} | [{eng}] {format_ts(r['timestamp'])} | {r['project']}")
        print(f"    sid:{r['session']}")
        if r["title"]:
            print(f"    title:{r['title']}")
        print(f"    score:{r['score']}")
        print(f"    {_make_snippet(r['text'], query_terms)}\n")


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Recall — Agent-agnostic session reader")
    parser.add_argument("--engine", "-e", choices=ENGINES, help="Filter by engine")
    sub = parser.add_subparsers(dest="mode")

    p_list = sub.add_parser("list", help="List recent sessions")
    p_list.add_argument("--project", "-p", help="Filter by project name pattern")
    p_list.add_argument("--all-projects", action="store_true", help="Search/list across all projects")
    p_list.add_argument("--limit", "-n", type=int, help="Max sessions (default: 20)")
    p_list.add_argument("--engine", "-e", choices=ENGINES, dest="sub_engine", help="Filter by engine")

    p_over = sub.add_parser("overview", help="Session arc: beginning + middle + end")
    p_over.add_argument("session_id", help="Session UUID (or prefix)")
    p_over.add_argument("--project", "-p", help="Filter by project name pattern")
    p_over.add_argument("--all-projects", action="store_true", help="Search/list across all projects")
    p_over.add_argument("--limit", "-n", type=int, help="Messages per section (default: 3)")
    p_over.add_argument("--engine", "-e", choices=ENGINES, dest="sub_engine", help="Filter by engine")
    p_over.add_argument("--no-cache", action="store_true", help="Skip cache, regenerate overview")

    p_full = sub.add_parser("full", help="Full conversation, text only")
    p_full.add_argument("session_id", help="Session UUID (or prefix)")
    p_full.add_argument("--project", "-p", help="Filter by project name pattern")
    p_full.add_argument("--all-projects", action="store_true", help="Search/list across all projects")
    p_full.add_argument("--limit", "-n", type=int, help="Max messages to show")
    p_full.add_argument("--engine", "-e", choices=ENGINES, dest="sub_engine", help="Filter by engine")

    p_search = sub.add_parser("search", help="Keyword search across sessions")
    p_search.add_argument("query", help="Search query (space-separated terms, all must match)")
    p_search.add_argument("--project", "-p", help="Filter by project name pattern")
    p_search.add_argument("--all-projects", action="store_true", help="Search/list across all projects")
    p_search.add_argument("--limit", "-n", type=int, help="Max results (default: 15)")
    p_search.add_argument("--engine", "-e", choices=ENGINES, dest="sub_engine", help="Filter by engine")

    p_cache = sub.add_parser("cache", help="Manage the overview cache")
    p_cache.add_argument("action", choices=["clear", "stats"], help="clear: delete cache, stats: show cache info")

    args = parser.parse_args()

    # Merge engine from global or subcommand level
    if not hasattr(args, "sub_engine") or args.sub_engine is None:
        pass  # use global --engine
    else:
        args.engine = args.sub_engine

    if args.mode == "list":
        cmd_list(args)
    elif args.mode == "overview":
        cmd_overview(args)
    elif args.mode == "full":
        cmd_full(args)
    elif args.mode == "search":
        cmd_search(args)
    elif args.mode == "cache":
        if args.action == "clear":
            _cache_clear()
        elif args.action == "stats":
            _cache_stats()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
