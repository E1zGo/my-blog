import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone


def uid():
    return uuid.uuid4().hex


def now():
    return datetime.now(timezone.utc).isoformat()


def dump(value):
    return json.dumps(value, ensure_ascii=False)


class Database:
    def __init__(self, directory):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "researchpilot.sqlite3"
        with self.connect() as con:
            con.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('admin','member')),
                    active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS workspaces (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS workspace_owners (
                    workspace_id TEXT PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
                    user_id TEXT NOT NULL REFERENCES users(id));
                CREATE INDEX IF NOT EXISTS workspace_owner_user ON workspace_owners(user_id);
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS invitations (
                    token_hash TEXT PRIMARY KEY, issuer_id TEXT NOT NULL REFERENCES users(id),
                    expires_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS auth_attempts (
                    key TEXT PRIMARY KEY, attempts INTEGER NOT NULL, window_start INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS sources (
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                    name TEXT NOT NULL, kind TEXT NOT NULL, checksum TEXT NOT NULL,
                    metadata TEXT NOT NULL, created_at TEXT NOT NULL,
                    UNIQUE(workspace_id, checksum));
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                    text TEXT NOT NULL, page INTEGER, locator TEXT NOT NULL,
                    vector TEXT, embedding_model TEXT);
                CREATE INDEX IF NOT EXISTS chunks_source ON chunks(source_id);
                CREATE TABLE IF NOT EXISTS log_documents (
                    source_id TEXT PRIMARY KEY REFERENCES sources(id) ON DELETE CASCADE,
                    text TEXT NOT NULL, checksum TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                    prompt TEXT NOT NULL, intent TEXT NOT NULL, mode TEXT NOT NULL,
                    status TEXT NOT NULL, answer TEXT NOT NULL DEFAULT '',
                    citations TEXT NOT NULL DEFAULT '[]', usage TEXT NOT NULL DEFAULT '{}',
                    error TEXT, created_at TEXT NOT NULL, finished_at TEXT);
                CREATE INDEX IF NOT EXISTS tasks_workspace ON tasks(workspace_id, created_at);
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    phase TEXT NOT NULL, message TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS imports (
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                    name TEXT NOT NULL, kind TEXT NOT NULL, size_bytes INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL, message TEXT NOT NULL DEFAULT '',
                    current_page INTEGER NOT NULL DEFAULT 0, total_pages INTEGER NOT NULL DEFAULT 0,
                    result TEXT, error TEXT, created_at TEXT NOT NULL, finished_at TEXT);
                CREATE INDEX IF NOT EXISTS imports_workspace ON imports(workspace_id, created_at);
                CREATE TABLE IF NOT EXISTS notes (
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                    title TEXT NOT NULL, category TEXT NOT NULL, body TEXT NOT NULL DEFAULT '',
                    source_id TEXT, source_name TEXT, evidence_key TEXT, evidence TEXT,
                    revision INTEGER NOT NULL DEFAULT 1, archived INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    UNIQUE(workspace_id, evidence_key));
                CREATE INDEX IF NOT EXISTS notes_workspace ON notes(workspace_id, updated_at);
                CREATE TABLE IF NOT EXISTS experiments (
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                    name TEXT NOT NULL, status TEXT NOT NULL, details TEXT NOT NULL,
                    plan TEXT, logs TEXT NOT NULL DEFAULT '[]',
                    revision INTEGER NOT NULL DEFAULT 1, archived INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS experiments_workspace ON experiments(workspace_id, updated_at);
            """)
            columns = {row["name"] for row in con.execute("PRAGMA table_info(tasks)")}
            if "source_ids" not in columns:
                con.execute("ALTER TABLE tasks ADD COLUMN source_ids TEXT NOT NULL DEFAULT '[]'")
            if "page_range" not in columns:
                con.execute("ALTER TABLE tasks ADD COLUMN page_range TEXT NOT NULL DEFAULT 'null'")
            columns = {row["name"] for row in con.execute("PRAGMA table_info(notes)")}
            if "source_page" not in columns:
                con.execute("ALTER TABLE notes ADD COLUMN source_page INTEGER")
            columns = {row["name"] for row in con.execute("PRAGMA table_info(chunks)")}
            if "structure" not in columns:
                con.execute("ALTER TABLE chunks ADD COLUMN structure TEXT NOT NULL DEFAULT '{}'")
            columns = {row["name"] for row in con.execute("PRAGMA table_info(imports)")}
            if "source_id" not in columns:
                con.execute("ALTER TABLE imports ADD COLUMN source_id TEXT")

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path, timeout=15)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        try:
            with con:
                yield con
        finally:
            con.close()

    def one(self, sql, args=()):
        with self.connect() as con:
            row = con.execute(sql, args).fetchone()
            return dict(row) if row else None

    def all(self, sql, args=()):
        with self.connect() as con:
            return [dict(r) for r in con.execute(sql, args).fetchall()]

    def execute(self, sql, args=()):
        with self.connect() as con:
            con.execute(sql, args)

    def event(self, task_id, phase, message, data=None):
        self.execute("INSERT INTO events(task_id,phase,message,data,created_at) VALUES (?,?,?,?,?)",
                     (task_id, phase, message, dump(data or {}), now()))

    def task(self, task_id):
        task = self.one("SELECT * FROM tasks WHERE id=?", (task_id,))
        if task:
            task["source_ids"] = json.loads(task["source_ids"])
            task["page_range"] = json.loads(task["page_range"])
            task["citations"] = json.loads(task["citations"])
            task["usage"] = json.loads(task["usage"])
            task["events"] = self.all("SELECT * FROM events WHERE task_id=? ORDER BY id", (task_id,))
            for event in task["events"]:
                event["data"] = json.loads(event["data"])
        return task
