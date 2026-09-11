"""SQLite 数据总线：单表 jobs + WAL + upsert/查询辅助。

阶段间只通过本表交互（列级状态机，谓词见 models.py），
模块边界铁律：discovery 只写 discover 列，enrichment 只写 enrich 列。
"""

from __future__ import annotations

import sqlite3
from typing import Any, Iterable

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  url            TEXT PRIMARY KEY,
  platform       TEXT NOT NULL CHECK(platform IN ('boss','liepin')),

  -- discover（列表页）
  job_title      TEXT,
  company        TEXT,
  city           TEXT,
  district       TEXT,
  salary_raw     TEXT,
  salary_min     INTEGER,
  salary_max     INTEGER,
  salary_months  INTEGER,
  experience_raw TEXT,
  education_raw  TEXT,
  job_tags       TEXT,
  hr_name        TEXT,
  hr_title       TEXT,
  hr_active      TEXT,
  search_source  TEXT,
  discovered_at  TEXT,

  -- enrich（JD 全文）
  full_description TEXT,
  apply_url      TEXT,
  detail_scraped_at TEXT,
  enrich_error   TEXT,
  enrich_attempts INTEGER DEFAULT 0,

  -- 过滤（纯代码规则淘汰）
  reject_reason  TEXT,
  rejected_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_pending_enrich
  ON jobs(discovered_at) WHERE detail_scraped_at IS NULL;
"""

_DISCOVER_COLUMNS = {
    "url", "platform", "job_title", "company", "city", "district",
    "salary_raw", "salary_min", "salary_max", "salary_months", "experience_raw",
    "education_raw", "job_tags",
    "hr_name", "hr_title", "hr_active", "search_source", "discovered_at",
}
ALLOWED_COLUMNS = _DISCOVER_COLUMNS | {
    "full_description", "apply_url", "detail_scraped_at", "enrich_error",
    "enrich_attempts", "reject_reason", "rejected_at",
}


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


# 旧库补列用：CREATE TABLE IF NOT EXISTS 不会给已存在的表加新列
_MIGRATIONS = (("experience_raw", "TEXT"), ("education_raw", "TEXT"))


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    have = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
    for col, decl in _MIGRATIONS:
        if col not in have:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {decl}")
    conn.commit()


def upsert_job(conn: sqlite3.Connection, job: dict[str, Any]) -> bool:
    """插入岗位行；url 冲突则忽略。返回 True 表示新增。"""
    cols = {k: v for k, v in job.items() if k in ALLOWED_COLUMNS and v is not None}
    bad = set(job) - ALLOWED_COLUMNS
    if bad:
        raise ValueError(f"未知列: {bad}")
    names = ", ".join(cols)
    marks = ", ".join("?" for _ in cols)
    try:
        conn.execute(f"INSERT INTO jobs ({names}) VALUES ({marks})", tuple(cols.values()))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def fetch(conn: sqlite3.Connection, where: str = "1=1", params: Iterable = (),
          order: str = "ORDER BY discovered_at DESC") -> list[sqlite3.Row]:
    cur = conn.execute(f"SELECT * FROM jobs WHERE {where} {order}", tuple(params))
    return cur.fetchall()


def update_columns(conn: sqlite3.Connection, url: str, **cols: Any) -> None:
    bad = set(cols) - ALLOWED_COLUMNS
    if bad:
        raise ValueError(f"未知列: {bad}")
    if not cols:
        return
    sets = ", ".join(f"{k} = ?" for k in cols)
    conn.execute(f"UPDATE jobs SET {sets} WHERE url = ?", (*cols.values(), url))
    conn.commit()


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    """jp status 的计数板数据源。"""
    q = lambda sql, p=(): (conn.execute(sql, tuple(p)).fetchone() or [0])[0]  # noqa: E731
    return {
        "总岗位": q("SELECT COUNT(*) FROM jobs"),
        "已有 JD 全文": q("SELECT COUNT(*) FROM jobs WHERE full_description IS NOT NULL"),
        "待抓 JD": q(
            "SELECT COUNT(*) FROM jobs WHERE discovered_at IS NOT NULL"
            " AND detail_scraped_at IS NULL AND reject_reason IS NULL"
        ),
        "抓 JD 失败": q(
            "SELECT COUNT(*) FROM jobs WHERE detail_scraped_at IS NULL"
            " AND enrich_error IS NOT NULL AND reject_reason IS NULL"
        ),
        "已过滤": q("SELECT COUNT(*) FROM jobs WHERE reject_reason IS NOT NULL"),
    }
