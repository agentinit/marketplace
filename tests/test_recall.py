import importlib.util
import os
import sqlite3
import sys
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
