"""只追加事件存储。

所有状态变化都是一条不可变事件，按单调递增的逻辑时钟 ``seq`` 排序，并带
``effective_at``（业务生效时间）与内容哈希 ``payload_hash``。读模型通过重放
事件构建；任何"更正"都是追加一条新版本事件，旧版本永远可查。

存储使用标准库 sqlite3。表一旦建立便不做破坏性迁移；新版本只追加新事件类型。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    seq           INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type    TEXT NOT NULL,
    aggregate     TEXT NOT NULL,
    version       INTEGER NOT NULL,
    payload       TEXT NOT NULL,
    payload_hash  TEXT NOT NULL,
    effective_at  REAL NOT NULL,
    recorded_at   REAL NOT NULL,
    run_id        TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_agg ON events(aggregate, version);
CREATE INDEX IF NOT EXISTS idx_events_eff ON events(effective_at);

CREATE TABLE IF NOT EXISTS runs (
    run_id       TEXT PRIMARY KEY,
    parent_run_id TEXT,
    rationale    TEXT NOT NULL,
    trigger_seq  INTEGER,
    formula_id   TEXT NOT NULL,
    status       TEXT NOT NULL,
    manifest     TEXT NOT NULL,
    created_at   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS result_nodes (
    node_hash     TEXT PRIMARY KEY,
    node_key      TEXT NOT NULL,
    value         REAL,
    unc_low       REAL,
    unc_high      REAL,
    basis         TEXT NOT NULL,
    method        TEXT,
    deps          TEXT NOT NULL,
    payload       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_nodes_key ON result_nodes(node_key);

CREATE TABLE IF NOT EXISTS run_nodes (
    run_id        TEXT NOT NULL,
    node_hash     TEXT NOT NULL,
    node_key      TEXT NOT NULL,
    PRIMARY KEY (run_id, node_hash),
    UNIQUE(run_id, node_key)
);

CREATE TABLE IF NOT EXISTS report_cells (
    report_id    TEXT NOT NULL,
    cell_key     TEXT NOT NULL,
    run_id       TEXT NOT NULL,
    node_hash    TEXT NOT NULL,
    sex          TEXT NOT NULL,
    age_band     TEXT,
    disease_id   TEXT NOT NULL,
    value        REAL,
    unc_low      REAL,
    unc_high     REAL,
    status       TEXT NOT NULL,
    basis        TEXT NOT NULL,
    suppressed_reason TEXT,
    payload      TEXT NOT NULL,
    PRIMARY KEY (report_id, cell_key)
);

CREATE TABLE IF NOT EXISTS reports (
    report_id    TEXT PRIMARY KEY,
    run_id       TEXT NOT NULL,
    title        TEXT NOT NULL,
    cutoff_seq   INTEGER NOT NULL,
    min_sample   INTEGER NOT NULL,
    created_at   REAL NOT NULL,
    superseded_by TEXT
);

CREATE TABLE IF NOT EXISTS flags (
    flag_id      TEXT PRIMARY KEY,
    kind         TEXT NOT NULL,
    target_type  TEXT NOT NULL,
    target_id    TEXT NOT NULL,
    reason       TEXT NOT NULL,
    report_id    TEXT,
    run_id       TEXT,
    node_key     TEXT,
    created_seq  INTEGER NOT NULL,
    resolved     INTEGER NOT NULL DEFAULT 0,
    payload      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_flags_target ON flags(target_type, target_id, resolved);
"""


def canonical_dumps(obj: Any) -> str:
    """以键排序、无空白的方式序列化，保证同内容哈希一致。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(obj: Any) -> str:
    return hashlib.sha256(canonical_dumps(obj).encode("utf-8")).hexdigest()


class Event:
    __slots__ = ("seq", "event_type", "aggregate", "version", "payload",
                 "payload_hash", "effective_at", "recorded_at", "run_id")

    def __init__(self, row: sqlite3.Row):
        self.seq = row["seq"]
        self.event_type = row["event_type"]
        self.aggregate = row["aggregate"]
        self.version = row["version"]
        self.payload = json.loads(row["payload"])
        self.payload_hash = row["payload_hash"]
        self.effective_at = row["effective_at"]
        self.recorded_at = row["recorded_at"]
        self.run_id = row["run_id"]

    def as_dict(self) -> dict:
        return {
            "seq": self.seq, "event_type": self.event_type,
            "aggregate": self.aggregate, "version": self.version,
            "payload": self.payload, "payload_hash": self.payload_hash,
            "effective_at": self.effective_at, "recorded_at": self.recorded_at,
            "run_id": self.run_id,
        }


class EventStore:
    """线程安全的只追加存储。一个实例对应一个 sqlite 数据库文件。"""

    def __init__(self, path: str = ":memory:"):
        self.path = path
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        with self._lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    # -- 写入 ---------------------------------------------------------------

    def append(self, event_type: str, aggregate: str, payload: dict,
               *, effective_at: float | None = None, run_id: str | None = None,
               expected_version: int | None = None) -> Event:
        """追加一条事件。

        aggregate 的版本号从 1 起自增；``expected_version`` 用于乐观并发控制。
        同一聚合的同一内容若已存在，返回既有事件（幂等合并的基础）。
        """
        now = time.time()
        effective = now if effective_at is None else effective_at
        phash = content_hash(payload)
        with self._lock:
            cur = self.conn.execute(
                "SELECT MAX(version) AS v FROM events WHERE aggregate = ?", (aggregate,))
            current_version = cur.fetchone()["v"] or 0
            if expected_version is not None and expected_version != current_version:
                raise ConflictError(
                    f"聚合 {aggregate} 版本冲突：期望 {expected_version}，实际 {current_version}")
            dup = self.conn.execute(
                "SELECT seq FROM events WHERE aggregate = ? AND payload_hash = ?",
                (aggregate, phash)).fetchone()
            if dup is not None:
                return self.get_event(dup["seq"])
            cur = self.conn.execute(
                "INSERT INTO events(event_type, aggregate, version, payload, "
                "payload_hash, effective_at, recorded_at, run_id) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (event_type, aggregate, current_version + 1, canonical_dumps(payload),
                 phash, effective, now, run_id))
            self.conn.commit()
            return self.get_event(cur.lastrowid)

    def save_run(self, run_id: str, parent_run_id: str | None, rationale: str,
                 trigger_seq: int | None, formula_id: str, status: str,
                 manifest: dict) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO runs(run_id, parent_run_id, rationale, "
                "trigger_seq, formula_id, status, manifest, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (run_id, parent_run_id, rationale, trigger_seq, formula_id, status,
                 canonical_dumps(manifest), time.time()))
            self.conn.commit()

    def save_node(self, node: dict, run_id: str) -> None:
        """写入内容寻址节点，并把它挂到本次运行。同内容节点全局只存一份。"""
        method = node.get("method")
        if not isinstance(method, (str, type(None))):
            method = canonical_dumps(method)
        with self._lock:
            self.conn.execute(
                "INSERT OR IGNORE INTO result_nodes(node_hash, node_key, value, "
                "unc_low, unc_high, basis, method, deps, payload) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (node["node_hash"], node["node_key"], node.get("value"),
                 node.get("unc_low"), node.get("unc_high"), node["basis"],
                 method, canonical_dumps(node["deps"]),
                 canonical_dumps(node)))
            self.conn.execute(
                "INSERT OR IGNORE INTO run_nodes(run_id, node_hash, node_key) "
                "VALUES (?,?,?)", (run_id, node["node_hash"], node["node_key"]))
            self.conn.commit()

    def save_report(self, report: dict, cells: Iterable[dict]) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO reports(report_id, run_id, title, cutoff_seq, "
                "min_sample, created_at, superseded_by) VALUES (?,?,?,?,?,?,NULL)",
                (report["report_id"], report["run_id"], report["title"],
                 report["cutoff_seq"], report["min_sample"], time.time()))
            self.conn.executemany(
                "INSERT OR REPLACE INTO report_cells(report_id, cell_key, run_id, "
                "node_hash, sex, age_band, disease_id, value, unc_low, unc_high, "
                "status, basis, suppressed_reason, payload) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [(c["report_id"], c["cell_key"], c["run_id"], c["node_hash"],
                  c["sex"], c.get("age_band"), c["disease_id"], c.get("value"),
                  c.get("unc_low"), c.get("unc_high"), c["status"], c["basis"],
                  c.get("suppressed_reason"), canonical_dumps(c)) for c in cells])
            self.conn.commit()

    def mark_superseded(self, report_id: str, by_report_id: str) -> None:
        with self._lock:
            self.conn.execute(
                "UPDATE reports SET superseded_by = ? WHERE report_id = ?",
                (by_report_id, report_id))
            self.conn.commit()

    def add_flag(self, flag: dict) -> None:
        with self._lock:
            exists = self.conn.execute(
                "SELECT resolved FROM flags WHERE flag_id = ?",
                (flag["flag_id"],)).fetchone()
            if exists is not None:
                if exists["resolved"]:
                    # 同一问题再次发生（如裁定后胜方主张又被更正）→ 重新挂起
                    self.conn.execute(
                        "UPDATE flags SET resolved = 0, created_seq = ?, "
                        "payload = ? WHERE flag_id = ?",
                        (flag["created_seq"], canonical_dumps(flag),
                         flag["flag_id"]))
                    self.conn.commit()
                return
            self.conn.execute(
                "INSERT INTO flags(flag_id, kind, target_type, target_id, reason, "
                "report_id, run_id, node_key, created_seq, resolved, payload) "
                "VALUES (?,?,?,?,?,?,?,?,?,0,?)",
                (flag["flag_id"], flag["kind"], flag["target_type"], flag["target_id"],
                 flag["reason"], flag.get("report_id"), flag.get("run_id"),
                 flag.get("node_key"), flag["created_seq"], canonical_dumps(flag)))
            self.conn.commit()

    def resolve_flags(self, target_type: str, target_id: str) -> int:
        with self._lock:
            cur = self.conn.execute(
                "UPDATE flags SET resolved = 1 WHERE target_type = ? AND target_id = ?",
                (target_type, target_id))
            self.conn.commit()
            return cur.rowcount

    # -- 读取 ---------------------------------------------------------------

    def head_seq(self) -> int:
        with self._lock:
            row = self.conn.execute("SELECT MAX(seq) AS s FROM events").fetchone()
            return row["s"] or 0

    def get_event(self, seq: int) -> Event:
        with self._lock:
            row = self.conn.execute("SELECT * FROM events WHERE seq = ?", (seq,)).fetchone()
        if row is None:
            raise KeyError(seq)
        return Event(row)

    def events(self, event_type: str | None = None,
               until_seq: int | None = None) -> list[Event]:
        sql = "SELECT * FROM events"
        clauses, params = [], []
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if until_seq is not None:
            clauses.append("seq <= ?")
            params.append(until_seq)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY seq"
        with self._lock:
            return [Event(r) for r in self.conn.execute(sql, params).fetchall()]

    def aggregate_versions(self, aggregate: str) -> list[Event]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM events WHERE aggregate = ? ORDER BY version",
                (aggregate,)).fetchall()
        return [Event(r) for r in rows]

    def find_hash(self, payload_hash: str) -> Event | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM events WHERE payload_hash = ?", (payload_hash,)).fetchone()
        return Event(row) if row else None

    def aggregate_has_hash(self, aggregate: str, payload_hash: str) -> bool:
        with self._lock:
            return self.conn.execute(
                "SELECT 1 FROM events WHERE aggregate = ? AND payload_hash = ?",
                (aggregate, payload_hash)).fetchone() is not None

    def get_run(self, run_id: str) -> dict | None:
        with self._lock:
            row = self.conn.execute("SELECT * FROM runs WHERE run_id = ?",
                                    (run_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["manifest"] = json.loads(d["manifest"])
        return d

    def all_runs(self) -> list[dict]:
        with self._lock:
            rows = self.conn.execute("SELECT * FROM runs ORDER BY created_at").fetchall()
        out = []
        for row in rows:
            d = dict(row)
            d["manifest"] = json.loads(d["manifest"])
            out.append(d)
        return out

    def nodes_of_run(self, run_id: str) -> list[dict]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT n.payload AS p FROM result_nodes n "
                "JOIN run_nodes r ON r.node_hash = n.node_hash "
                "WHERE r.run_id = ? ORDER BY n.node_key",
                (run_id,)).fetchall()
        return [json.loads(r["p"]) for r in rows]

    def node(self, run_id: str, node_key: str) -> dict | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT n.payload AS p FROM result_nodes n "
                "JOIN run_nodes r ON r.node_hash = n.node_hash "
                "WHERE r.run_id = ? AND n.node_key = ?",
                (run_id, node_key)).fetchone()
        return json.loads(row["p"]) if row else None

    def node_by_hash(self, node_hash: str) -> dict | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT payload FROM result_nodes WHERE node_hash = ?",
                (node_hash,)).fetchone()
        return json.loads(row["payload"]) if row else None

    def get_report(self, report_id: str) -> dict | None:
        with self._lock:
            row = self.conn.execute("SELECT * FROM reports WHERE report_id = ?",
                                    (report_id,)).fetchone()
        return dict(row) if row else None

    def report_cells(self, report_id: str) -> list[dict]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT payload FROM report_cells WHERE report_id = ? ORDER BY cell_key",
                (report_id,)).fetchall()
        return [json.loads(r["payload"]) for r in rows]

    def list_reports(self) -> list[dict]:
        with self._lock:
            rows = self.conn.execute("SELECT * FROM reports ORDER BY created_at").fetchall()
        return [dict(r) for r in rows]

    def flags(self, target_type: str | None = None, target_id: str | None = None,
              include_resolved: bool = True) -> list[dict]:
        sql = "SELECT payload FROM flags"
        clauses, params = [], []
        if target_type:
            clauses.append("target_type = ?")
            params.append(target_type)
        if target_id:
            clauses.append("target_id = ?")
            params.append(target_id)
        if not include_resolved:
            clauses.append("resolved = 0")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_seq"
        with self._lock:
            return [json.loads(r["payload"]) for r in self.conn.execute(sql, params)]

    def lineage(self, node_hash: str) -> list[dict]:
        """沿 deps 递归展开某结果节点的完整输入血缘（含节点本身）。"""
        seen, order = set(), []

        def visit(nh: str):
            if nh in seen:
                return
            seen.add(nh)
            with self._lock:
                row = self.conn.execute(
                    "SELECT payload FROM result_nodes WHERE node_hash = ?",
                    (nh,)).fetchone()
            if row is None:
                return
            node = json.loads(row["payload"])
            for dep in node["deps"]:
                visit(dep)
            order.append(node)

        visit(node_hash)
        return order


class ConflictError(RuntimeError):
    """乐观并发冲突。"""
