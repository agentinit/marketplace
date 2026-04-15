import importlib.util
import os
import sqlite3
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch


sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "skills" / "recall" / "recall.py"


def _load_recall_module():
    spec = importlib.util.spec_from_file_location("recall_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


recall = _load_recall_module()


class CachePathTests(unittest.TestCase):
    def test_cache_db_path_honors_explicit_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_db = os.path.join(tmpdir, "custom-recall.db")
            with patch.dict(os.environ, {"AGENTINIT_RECALL_CACHE_DB": cache_db}, clear=False):
                self.assertEqual(recall.get_cache_db_path(), cache_db)

    def test_cache_db_path_uses_user_cache_dir_not_skill_directory(self):
        original_override = os.environ.pop("AGENTINIT_RECALL_CACHE_DB", None)
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                with patch.dict(os.environ, {"XDG_CACHE_HOME": tmpdir}, clear=False):
                    cache_db = recall.get_cache_db_path()

                self.assertEqual(cache_db, os.path.join(tmpdir, "agentinit", "recall", "cache.db"))
                self.assertFalse(cache_db.startswith(str(MODULE_PATH.parent)))
        finally:
            if original_override is not None:
                os.environ["AGENTINIT_RECALL_CACHE_DB"] = original_override

    def test_cache_connection_creates_parent_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_db = os.path.join(tmpdir, "nested", "cache.db")
            with patch.dict(os.environ, {"AGENTINIT_RECALL_CACHE_DB": cache_db}, clear=False):
                conn = recall._get_cache_conn()
                conn.close()

            self.assertTrue(Path(cache_db).is_file())


class OpenCodeSessionTests(unittest.TestCase):
    def test_opencode_sessions_sort_and_invalidate_by_last_activity(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "opencode.db")
            conn = sqlite3.connect(db_path)
            conn.executescript(
                """
                CREATE TABLE project (
                    id TEXT PRIMARY KEY,
                    worktree TEXT
                );
                CREATE TABLE session (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    directory TEXT,
                    time_created INTEGER,
                    time_archived INTEGER,
                    project_id TEXT
                );
                CREATE TABLE message (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    time_created INTEGER,
                    data TEXT
                );
                """
            )
            conn.execute("INSERT INTO project (id, worktree) VALUES (?, ?)", ("project-a", "/workspace/project-a"))
            conn.execute("INSERT INTO project (id, worktree) VALUES (?, ?)", ("project-b", "/workspace/project-b"))
            conn.execute(
                "INSERT INTO session (id, title, directory, time_created, time_archived, project_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("session-a", "Session A", "/workspace/project-a", 1000, None, "project-a"),
            )
            conn.execute(
                "INSERT INTO session (id, title, directory, time_created, time_archived, project_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("session-b", "Session B", "/workspace/project-b", 4000, None, "project-b"),
            )
            conn.execute(
                "INSERT INTO message (id, session_id, time_created, data) VALUES (?, ?, ?, ?)",
                ("msg-a1", "session-a", 5000, "{}"),
            )
            conn.commit()
            conn.close()

            with patch.object(recall, "OPENCODE_DB", db_path):
                sessions = recall._get_opencode_sessions()

            self.assertEqual([session.session_id for session in sessions], ["session-a", "session-b"])
            self.assertEqual(sessions[0].mtime, 5.0)
            self.assertEqual(sessions[0].project, "workspace/project-a")


class SearchBehaviorTests(unittest.TestCase):
    def test_all_projects_ignores_project_filter(self):
        args = SimpleNamespace(project="aconnect", all_projects=True)
        self.assertIsNone(recall._resolve_project(args))

    def test_search_title_only_match_does_not_show_unrelated_message_body(self):
        session = recall.SessionFile("claude", "title-session", "net/vpn", "/tmp/title.jsonl", 10.0)
        messages = [
            {
                "type": "assistant",
                "timestamp": "2026-04-14T09:00:00+00:00",
                "text": "still unrelated",
            },
            {
                "type": "assistant",
                "timestamp": "2026-04-14T09:01:00+00:00",
                "text": "also unrelated",
            },
        ]

        args = SimpleNamespace(
            query="wireguard vpn",
            engine=None,
            project=None,
            all_projects=True,
            limit=10,
        )

        with patch.object(recall, "get_all_sessions", return_value=[session]), \
             patch.object(recall, "parse_messages", return_value=messages), \
             patch.object(recall, "_get_title", return_value="Wireguard VPN setup issue"), \
             patch.object(recall, "_get_timestamp", return_value="2026-04-14T08:59:00+00:00"):
            buf = io.StringIO()
            with redirect_stdout(buf):
                recall.cmd_search(args)

        output = buf.getvalue()
        self.assertIn("[1] SESSION | [CC] 2026-04-14 08:59 | net/vpn", output)
        self.assertIn("title:Wireguard VPN setup issue", output)
        self.assertIn("matched on session title", output)
        self.assertNotIn("still unrelated", output)
        self.assertNotIn("also unrelated", output)

    def test_search_returns_one_best_match_per_session_and_downranks_noise(self):
        noisy = recall.SessionFile("codex", "noise-session", "git/aconnect", "/tmp/noise.jsonl", 20.0)
        relevant = recall.SessionFile("claude", "real-session", "sh/trino", "/tmp/real.jsonl", 10.0)

        messages = {
            noisy.session_id: [
                {
                    "type": "assistant",
                    "timestamp": "2026-04-14T09:00:00+00:00",
                    "text": "Use the recall helper script to find split sessions and summarize them.",
                },
                {
                    "type": "assistant",
                    "timestamp": "2026-04-14T09:01:00+00:00",
                    "text": "Global recall searches were run for split and related terms.",
                },
            ],
            relevant.session_id: [
                {
                    "type": "user",
                    "timestamp": "2026-04-09T06:04:00+00:00",
                    "text": "TrinoExternalError name=ICEBERG_CANNOT_OPEN_SPLIT while reading the partition.",
                },
                {
                    "type": "assistant",
                    "timestamp": "2026-04-09T06:05:00+00:00",
                    "text": "The split failure comes from corrupted parquet files in the Iceberg partition.",
                },
            ],
        }
        titles = {
            noisy.session_id: "use recall skill to get the sessions when we've been fixing split errors",
            relevant.session_id: "analyze the script please.",
        }

        args = SimpleNamespace(
            query="split",
            engine=None,
            project="aconnect",
            all_projects=True,
            limit=10,
        )

        with patch.object(recall, "get_all_sessions", return_value=[noisy, relevant]), \
             patch.object(recall, "parse_messages", side_effect=lambda session: messages[session.session_id]), \
             patch.object(recall, "_get_title", side_effect=lambda session: titles[session.session_id]):
            buf = io.StringIO()
            with redirect_stdout(buf):
                recall.cmd_search(args)

        output = buf.getvalue()
        self.assertIn("Found 2 session matches for: split", output)
        self.assertEqual(output.count("sid:noise-session"), 1)
        self.assertEqual(output.count("sid:real-session"), 1)
        self.assertLess(output.index("sid:real-session"), output.index("sid:noise-session"))


if __name__ == "__main__":
    unittest.main()
