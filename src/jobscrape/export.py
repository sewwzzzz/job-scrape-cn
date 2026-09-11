"""导出抓取结果：JSON / CSV（供人工查看或下游分析）。

默认输出到 ~/.job-scrape-cn/exports/，文件名带日期。
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from datetime import date
from pathlib import Path

from . import config

FIELDS = [
    "platform", "job_title", "company", "city", "district",
    "salary_raw", "salary_min", "salary_max", "salary_months",
    "experience_raw", "education_raw", "job_tags", "hr_name", "hr_title",
    "hr_active", "search_source",
    "url", "apply_url", "full_description",
    "discovered_at", "detail_scraped_at", "reject_reason",
]


def select_rows(conn: sqlite3.Connection, include_rejected: bool = False) -> list[dict]:
    where = "1=1" if include_rejected else "reject_reason IS NULL"
    rows = conn.execute(
        f"SELECT {', '.join(FIELDS)} FROM jobs WHERE {where}"
        " ORDER BY platform, discovered_at"
    ).fetchall()
    return [dict(r) for r in rows]


def to_json(rows: list[dict]) -> str:
    return json.dumps(rows, ensure_ascii=False, indent=2)


def to_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=FIELDS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def export_jobs(conn: sqlite3.Connection, fmt: str = "all",
                include_rejected: bool = False,
                out_dir: str | Path | None = None) -> list[Path]:
    """导出岗位数据；返回写出的文件路径列表。"""
    fmt = fmt.lower()
    if fmt not in ("json", "csv", "all"):
        raise ValueError("fmt 只能是 json / csv / all")
    rows = select_rows(conn, include_rejected)
    d = Path(out_dir) if out_dir else config.exports_dir()
    d.mkdir(parents=True, exist_ok=True)
    stamp = date.today().isoformat()

    written: list[Path] = []
    if fmt in ("json", "all"):
        p = d / f"jobs-{stamp}.json"
        p.write_text(to_json(rows), encoding="utf-8")
        written.append(p)
    if fmt in ("csv", "all"):
        p = d / f"jobs-{stamp}.csv"
        p.write_text(to_csv(rows), encoding="utf-8-sig")  # 带 BOM，Excel 直开不乱码
        written.append(p)
    return written
