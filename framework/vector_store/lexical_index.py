"""Persistent, incrementally tokenized lexical index with a durable repair journal."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import uuid

import jieba

VERSION = "jieba-casefold-fts5-bm25-v1"


def tokenize(text):
    return [term.casefold() for term in jieba.lcut(text) if any(char.isalnum() for char in term)]


def filter_sql(filters, column="d.metadata"):
    """Compile supported Chroma predicates; unsupported operators fail closed."""
    if not filters:
        return "1", []
    if not isinstance(filters, dict):
        raise ValueError("invalid_lexical_filter")
    clauses, values = [], []
    for key, expected in filters.items():
        if key in ("$and", "$or"):
            if not isinstance(expected, list) or not expected:
                raise ValueError("empty_lexical_logical_filter")
            parts = [filter_sql(item, column) for item in expected]
            clauses.append("("+(" AND " if key == "$and" else " OR ").join(part[0] for part in parts)+")")
            values.extend(value for part in parts for value in part[1])
            continue
        if not isinstance(key, str) or key.startswith("$"):
            raise ValueError("unsupported_lexical_filter")
        path = "$."+json.dumps(key, ensure_ascii=False)
        operations = expected if isinstance(expected, dict) else {"$eq": expected}
        if not operations:
            raise ValueError("empty_lexical_field_filter")
        for operation, value in operations.items():
            expression = "json_extract("+column+",?)"
            if operation in ("$eq", "$ne"):
                clauses.append(expression+(" IS ?" if operation == "$eq" else " IS NOT ?"))
                values.extend([path, value])
            elif operation in ("$in", "$nin"):
                if not isinstance(value, list):
                    raise ValueError("invalid_lexical_membership_filter")
                clauses.append(("NOT " if operation == "$nin" else "")+"EXISTS (SELECT 1 FROM json_each(?) membership WHERE membership.value IS "+expression+")")
                values.extend([json.dumps(value, ensure_ascii=False), path])
            elif operation in ("$gt", "$gte", "$lt", "$lte"):
                clauses.append(expression+{"$gt": ">", "$gte": ">=", "$lt": "<", "$lte": "<="}[operation]+"?")
                values.extend([path, value])
            else:
                raise ValueError("unsupported_lexical_filter_operator")
    return " AND ".join("("+clause+")" for clause in clauses) or "1", values


class LexicalIndex:
    def __init__(self, path, collection):
        self.path, self.collection = str(path), collection
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.metrics = {"tokenized_rows": 0, "max_write_batch": 0, "searches": 0, "returned_rows": 0}
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS lexical_collection(name TEXT PRIMARY KEY,version TEXT NOT NULL,state TEXT NOT NULL,source_count INTEGER);
                CREATE TABLE IF NOT EXISTS lexical_document(rowid INTEGER PRIMARY KEY,collection TEXT NOT NULL,id TEXT NOT NULL,content TEXT NOT NULL,metadata TEXT NOT NULL,content_hash TEXT NOT NULL,UNIQUE(collection,id));
                CREATE INDEX IF NOT EXISTS idx_lexical_collection ON lexical_document(collection);
                CREATE INDEX IF NOT EXISTS idx_lexical_document_id ON lexical_document(collection,json_extract(metadata,'$.document_id'));
                CREATE INDEX IF NOT EXISTS idx_lexical_source ON lexical_document(collection,json_extract(metadata,'$.source'));
                CREATE VIRTUAL TABLE IF NOT EXISTS lexical_fts USING fts5(terms,content='');
                CREATE TABLE IF NOT EXISTS lexical_terms(rowid INTEGER PRIMARY KEY,terms TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS lexical_operation(id TEXT PRIMARY KEY,collection TEXT NOT NULL,selector TEXT NOT NULL,state TEXT NOT NULL,created REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_lexical_operation_state ON lexical_operation(collection,state);
            """)
            row = connection.execute("SELECT version FROM lexical_collection WHERE name=?", (collection,)).fetchone()
            if not row:
                connection.execute("INSERT INTO lexical_collection VALUES (?,?,?,NULL)", (collection, VERSION, "missing"))
            elif row[0] != VERSION:
                connection.execute("UPDATE lexical_collection SET version=?,state='rebuild_required' WHERE name=?", (VERSION, collection))

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=15)
        connection.execute("PRAGMA busy_timeout=15000")
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback(); raise
        finally:
            connection.close()

    def health(self):
        with self.connect() as connection:
            state, count = connection.execute("SELECT state,source_count FROM lexical_collection WHERE name=?", (self.collection,)).fetchone()
            rows = connection.execute("SELECT count(*) FROM lexical_document WHERE collection=?", (self.collection,)).fetchone()[0]
            pending = connection.execute("SELECT count(*) FROM lexical_operation WHERE collection=? AND state='pending'", (self.collection,)).fetchone()[0]
        return {"state": "dirty" if pending else state, "base_state": state, "rows": rows, "pending_operations": pending, "source_count": count,
                "version": VERSION, "metrics": dict(self.metrics)}

    def mark_ready(self):
        with self.connect() as connection:
            count = connection.execute("SELECT count(*) FROM lexical_document WHERE collection=?", (self.collection,)).fetchone()[0]
            connection.execute("UPDATE lexical_collection SET state='ready',source_count=? WHERE name=?", (count, self.collection))

    def _remove(self, connection, where, values):
        removed = 0
        # Bounded deletion batches also support contentless FTS on older SQLite.
        while True:
            rows = connection.execute("SELECT d.rowid,t.terms FROM lexical_document d JOIN lexical_terms t ON t.rowid=d.rowid WHERE d.collection=? AND ("+where+") LIMIT 500", [self.collection, *values]).fetchall()
            if not rows:
                break
            for rowid, terms in rows:
                connection.execute("INSERT INTO lexical_fts(lexical_fts,rowid,terms) VALUES('delete',?,?)", (rowid, terms))
                connection.execute("DELETE FROM lexical_terms WHERE rowid=?", (rowid,))
                connection.execute("DELETE FROM lexical_document WHERE rowid=?", (rowid,))
            removed += len(rows)
        return removed

    def _upsert(self, connection, values):
        if len(values) > 500:
            raise ValueError("lexical_write_batch_exceeds_500")
        self.metrics["max_write_batch"] = max(self.metrics["max_write_batch"], len(values))
        for identifier, text, metadata in values:
            digest = hashlib.sha256(text.encode()).hexdigest()
            raw = json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            previous = connection.execute("SELECT rowid,content_hash,metadata FROM lexical_document WHERE collection=? AND id=?", (self.collection, identifier)).fetchone()
            if previous and previous[1] == digest:
                if previous[2] != raw:
                    connection.execute("UPDATE lexical_document SET metadata=? WHERE rowid=?", (raw, previous[0]))
                continue
            if previous:
                self._remove(connection, "d.id=?", [identifier])
            terms = " ".join(tokenize(text)); self.metrics["tokenized_rows"] += 1
            cursor = connection.execute("INSERT INTO lexical_document(collection,id,content,metadata,content_hash) VALUES(?,?,?,?,?)",
                                        (self.collection, identifier, text, raw, digest))
            rowid = cursor.lastrowid
            connection.execute("INSERT INTO lexical_terms VALUES (?,?)", (rowid, terms))
            connection.execute("INSERT INTO lexical_fts(rowid,terms) VALUES (?,?)", (rowid, terms))

    def upsert(self, values):
        with self.connect() as connection:
            self._upsert(connection, values)

    def begin_rebuild(self):
        with self.connect() as connection:
            connection.execute("UPDATE lexical_collection SET state='building' WHERE name=?", (self.collection,))
            self._remove(connection, "1", [])

    def finish_rebuild(self, expected_count):
        with self.connect() as connection:
            count = connection.execute("SELECT count(*) FROM lexical_document WHERE collection=?", (self.collection,)).fetchone()[0]
            if count != expected_count:
                raise ValueError("lexical_bootstrap_count_mismatch")
            connection.execute("UPDATE lexical_collection SET state='ready',source_count=? WHERE name=?", (count, self.collection))
            connection.execute("UPDATE lexical_operation SET state='reconciled' WHERE collection=? AND state='pending'", (self.collection,))

    def begin_operation(self, selector):
        identifier = uuid.uuid4().hex
        with self.connect() as connection:
            connection.execute("INSERT INTO lexical_operation VALUES (?,?,?,'pending',?)",
                               (identifier, self.collection, json.dumps(selector, sort_keys=True), time.time()))
        return identifier

    def pending(self):
        with self.connect() as connection:
            return [(identifier, json.loads(selector)) for identifier, selector in connection.execute(
                "SELECT id,selector FROM lexical_operation WHERE collection=? AND state='pending' ORDER BY created", (self.collection,))]

    def reconcile(self, operation_id, selector, batches, source_count):
        """Caller reads only the selected source scope; replacement commits atomically."""
        with self.connect() as connection:
            if "ids" in selector:
                identifiers = selector["ids"]
                where = "d.id IN ("+",".join("?" for _ in identifiers)+")" if identifiers else "0"
                values = identifiers
            else:
                where, values = filter_sql(selector.get("where"))
            # Keep unchanged token rows while streaming the current source scope.
            connection.execute("CREATE TEMP TABLE seen_ids (id TEXT PRIMARY KEY)")
            for batch in batches:
                self._upsert(connection, batch)
                connection.executemany("INSERT OR IGNORE INTO seen_ids VALUES (?)", [(row[0],) for row in batch])
            self._remove(connection, "("+where+") AND d.id NOT IN (SELECT id FROM seen_ids)", values)
            connection.execute("DROP TABLE seen_ids")
            connection.execute("UPDATE lexical_operation SET state='reconciled' WHERE id=? AND collection=?", (operation_id, self.collection))
            connection.execute("UPDATE lexical_collection SET state='ready',source_count=? WHERE name=?", (source_count, self.collection))

    def search(self, query, limit=20, filters=None, *, concept_groups=None):
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("lexical_result_limit_out_of_range")
        words = list(dict.fromkeys(tokenize(query)))[:64]
        if not words:
            return []
        match = " OR ".join('"'+word.replace('"', '""')+'"' for word in words)
        if concept_groups:
            if len(concept_groups) > 16 or any(not group or len(group) > 64 for group in concept_groups):
                raise ValueError("lexical_concept_groups_out_of_range")
            clauses = []
            for group in concept_groups:
                phrases = []
                for alias in group:
                    terms = tokenize(alias)
                    if not terms or len(terms) > 16:
                        raise ValueError("invalid_lexical_concept_alias")
                    phrases.append('"'+' '.join(terms).replace('"', '""')+'"')
                clauses.append('('+' OR '.join(phrases)+')')
            match = ' AND '.join(clauses)
        where, values = filter_sql(filters)
        with self.connect() as connection:
            state = connection.execute("SELECT state FROM lexical_collection WHERE name=?", (self.collection,)).fetchone()[0]
            pending = connection.execute("SELECT 1 FROM lexical_operation WHERE collection=? AND state='pending' LIMIT 1", (self.collection,)).fetchone()
            if state != "ready" or pending:
                return []
            rows = connection.execute("SELECT d.id,d.content,d.metadata,bm25(lexical_fts) FROM lexical_fts JOIN lexical_document d ON d.rowid=lexical_fts.rowid WHERE lexical_fts MATCH ? AND d.collection=? AND ("+where+") ORDER BY bm25(lexical_fts),d.id LIMIT ?", [match, self.collection, *values, limit]).fetchall()
        self.metrics["searches"] += 1; self.metrics["returned_rows"] += len(rows)
        return [{"id": identifier, "content": text, "metadata": json.loads(meta), "score": -float(score)} for identifier,text,meta,score in rows]

    def delete(self, filters):
        where, values = filter_sql(filters)
        with self.connect() as connection:
            return self._remove(connection, where, values)

    def clear(self):
        return self.delete(None)
