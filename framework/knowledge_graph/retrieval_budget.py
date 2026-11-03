"""R1-only reservations; the historical annotation ledgers are never opened."""
from contextlib import contextmanager
import sqlite3
import time

from .acceptance_budget import Budget, BudgetStop
from .contracts import stable_digest


class RetrievalEmbeddingBudget(Budget):
    @contextmanager
    def connect(self):
        # sqlite3.Connection's context manager commits but does not close the
        # handle. Explicit closure also permits clean shutdown on Windows.
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def __init__(self, path, manifest, *, amendment=None):
        self.manifest = manifest
        self.allowed = {item["case_id"]: item for item in manifest["requests"]}
        caps = manifest["proposed_caps"]
        super().__init__(path, total=caps["tokens"], stability=caps["tokens"], requests=caps["attempts"])
        with self.connect() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS r1_identity (id INTEGER PRIMARY KEY CHECK(id=1), digest TEXT NOT NULL)")
            identity = stable_digest(manifest)
            connection.execute("INSERT OR IGNORE INTO r1_identity VALUES(1,?)", (identity,))
            previous = connection.execute("SELECT digest FROM r1_identity WHERE id=1").fetchone()[0]
            if previous != identity:
                if (not amendment or amendment.get("previous_manifest_identity") != previous
                        or amendment.get("new_manifest_identity") != identity or amendment.get("caps") != caps):
                    raise BudgetStop("R1_manifest_changed_use_new_authorization")
                connection.execute("CREATE TABLE IF NOT EXISTS r1_amendments (previous TEXT, current TEXT, authorization TEXT, created REAL)")
                connection.execute("INSERT INTO r1_amendments VALUES(?,?,?,?)", (previous, identity, amendment["user_confirmation"], time.time()))
                connection.execute("UPDATE r1_identity SET digest=? WHERE id=1", (identity,))

    def remaining_attempts(self, case_id):
        with self.connect() as connection:
            used = connection.execute("SELECT count(*) FROM attempts WHERE job=?", (case_id,)).fetchone()[0]
        return max(0, self.allowed[case_id]["maximum_attempts"]-used)

    def reserve_query(self, case_id, payload):
        expected = self.allowed.get(case_id)
        if not expected or payload != expected["payload"]:
            raise BudgetStop("query_not_in_authorized_R1_manifest")
        reservation = expected["reserved_tokens_per_attempt"]
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            attempts = connection.execute("SELECT job,reserved,charged,state FROM attempts").fetchall()
            if (len(attempts) >= self.requests or sum(charged if charged is not None else reserved for _, reserved, charged, _ in attempts)+reservation > self.total
                    or sum(job == case_id for job, *_ in attempts) >= expected["maximum_attempts"]):
                raise BudgetStop("R1_request_or_token_budget_reached")
            if sum(state == "inflight" for *_, state in attempts) >= 2:
                raise BudgetStop("R1_concurrency_limit")
            cursor = connection.execute("INSERT INTO attempts(phase,job,reserved,state,created) VALUES(?,?,?,?,?)",
                                        ("R1_query_embedding", case_id, reservation, "inflight", time.time()))
            return cursor.lastrowid
