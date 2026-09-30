"""Local SQLite run history with a lease to prevent overlapping writers."""

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


class Store:
    def __init__(self, directory: Path):
        if directory.is_symlink():
            raise ValueError("Evidence storage must not be a symlink.")
        directory.mkdir(exist_ok=True)
        self.path = directory / "runs.sqlite3"
        if self.path.is_symlink():
            raise ValueError("Evidence database must not be a symlink.")
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute(
                "CREATE TABLE IF NOT EXISTS runs "
                "(id TEXT PRIMARY KEY, created REAL, lease_until REAL, state TEXT, data TEXT)"
            )

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def begin(self, run: dict, lease_seconds: int):
        now = time.time()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute(
                "SELECT 1 FROM runs WHERE state='running' AND lease_until>?", (now,)
            ).fetchone():
                raise ValueError("Another check run is active for this project.")
            db.execute("UPDATE runs SET state='interrupted' WHERE state='running'")
            db.execute(
                "INSERT INTO runs VALUES (?, ?, ?, 'running', ?)",
                (run["run_id"], now, now + lease_seconds, json.dumps(run)),
            )

    def finish(self, run: dict, state: str):
        with self.connection() as db:
            db.execute(
                "UPDATE runs SET state=?, data=? WHERE id=?",
                (state, json.dumps(run), run["run_id"]),
            )
            db.execute(
                "DELETE FROM runs WHERE state!='running' AND id NOT IN "
                "(SELECT id FROM runs ORDER BY created DESC LIMIT 50)"
            )

    def get(self, run_id: str | None = None) -> dict | None:
        with self.connection() as db:
            if run_id is None:
                row = db.execute(
                    "SELECT state, data FROM runs ORDER BY created DESC LIMIT 1"
                ).fetchone()
            else:
                row = db.execute("SELECT state, data FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            return None
        result = json.loads(row[1])
        result["state"] = row[0]
        return result
