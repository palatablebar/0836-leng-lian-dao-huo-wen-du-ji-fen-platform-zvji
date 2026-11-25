import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init()

    def connect(self):
        connection = sqlite3.connect(self.path, timeout=8)
        connection.row_factory = sqlite3.Row
        return connection

    def init(self):
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS runs(
              id TEXT PRIMARY KEY,
              request_key TEXT UNIQUE NOT NULL,
              created_at TEXT NOT NULL,
              profile TEXT NOT NULL,
              status TEXT NOT NULL,
              revision INTEGER NOT NULL,
              payload TEXT NOT NULL,
              comment TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS corrections(
              id TEXT PRIMARY KEY,
              run_id TEXT NOT NULL,
              seq INTEGER NOT NULL,
              request_key TEXT UNIQUE NOT NULL,
              base_revision INTEGER NOT NULL,
              comment TEXT NOT NULL DEFAULT '',
              fixes TEXT NOT NULL,
              submitted_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS corrections_by_run ON corrections(run_id, seq);
            ''')

    def find_by_request(self, request_key):
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE request_key=?", (request_key,)).fetchone()
        return dict(row) if row else None

    def create(self, request_key, profile, payload):
        existing = self.find_by_request(request_key)
        if existing:
            return existing
        run_id = uuid.uuid4().hex[:12]
        with self.connect() as db:
            db.execute("INSERT INTO runs(id,request_key,created_at,profile,status,revision,payload) VALUES(?,?,?,?,?,?,?)",
                       (run_id, request_key, datetime.now(timezone.utc).isoformat(), profile, "DRAFT", 0,
                        json.dumps(payload, ensure_ascii=False)))
        return self.get(run_id)

    def get(self, run_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        return dict(row) if row else None

    def review(self, run_id, decision, comment, expected_revision):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                return None, "missing"
            if row["revision"] != expected_revision:
                return None, "stale"
            db.execute("UPDATE runs SET status=?, revision=revision+1, comment=? WHERE id=?",
                       (decision, comment, run_id))
        return self.get(run_id), None

    def corrections(self, run_id):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM corrections WHERE run_id=? ORDER BY seq", (run_id,)).fetchall()
        return [dict(row) for row in rows]

    def find_correction(self, request_key):
        with self.connect() as db:
            row = db.execute("SELECT * FROM corrections WHERE request_key=?", (request_key,)).fetchone()
        return dict(row) if row else None

    def record_correction(self, run_id, request_key, base_revision, comment, fixes, recompute):
        """Atomically record one correction and recompute the run payload.

        ``recompute(profile, corrections)`` returns the new payload.  Everything
        runs under a single ``BEGIN IMMEDIATE`` so two reviewers submitting
        concurrently cannot lose each other's correction.  Returns
        ``(run_row, correction_row, status)`` with status ``created``,
        ``existing`` (an idempotent retry) or ``missing`` (unknown run).
        """
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            run = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if run is None:
                return None, None, "missing"
            existing = db.execute("SELECT * FROM corrections WHERE request_key=?", (request_key,)).fetchone()
            if existing is not None:
                return dict(run), dict(existing), "existing"
            seq = db.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM corrections WHERE run_id=?",
                             (run_id,)).fetchone()[0]
            correction_id = uuid.uuid4().hex[:12]
            db.execute(
                "INSERT INTO corrections(id,run_id,seq,request_key,base_revision,comment,fixes,submitted_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (correction_id, run_id, seq, request_key, base_revision, comment,
                 json.dumps(fixes, ensure_ascii=False), datetime.now(timezone.utc).isoformat()))
            rows = db.execute("SELECT * FROM corrections WHERE run_id=? ORDER BY seq", (run_id,)).fetchall()
            payload = recompute(run["profile"], [dict(row) for row in rows])
            db.execute("UPDATE runs SET payload=?, status='DRAFT', revision=revision+1, comment='' WHERE id=?",
                       (json.dumps(payload, ensure_ascii=False), run_id))
            correction = db.execute("SELECT * FROM corrections WHERE id=?", (correction_id,)).fetchone()
            run = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        return dict(run), dict(correction), "created"
