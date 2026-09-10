"""导出测试：JSON / CSV 落盘、字段完整、默认跳过被过滤岗位。"""

from __future__ import annotations

import csv
import io
import json

import pytest

from jobpilot import db, export


def _job(url: str, **over) -> dict:
    job = {
        "url": url,
        "platform": "boss",
        "job_title": "算子开发工程师",
        "company": "某芯片公司",
        "city": "上海",
        "salary_raw": "30-50K",
        "salary_min": 30,
        "salary_max": 50,
        "salary_months": 12,
        "full_description": "负责 NPU 算子开发与性能优化。" * 5,
        "discovered_at": "2026-09-01T10:00:00",
        "detail_scraped_at": "2026-09-01T10:01:00",
    }
    job.update(over)
    return job


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBPILOT_HOME", str(tmp_path))
    c = db.connect()
    db.init_db(c)
    db.upsert_job(c, _job("https://www.zhipin.com/job_detail/1.html"))
    db.upsert_job(c, _job("https://www.zhipin.com/job_detail/2.html",
                          job_title="外包算子开发",
                          reject_reason="title_blacklist:外包",
                          rejected_at="2026-09-01T10:00:00"))
    yield c
    c.close()


def test_export_json_and_csv(conn, tmp_path):
    paths = export.export_jobs(conn, fmt="all", out_dir=tmp_path / "out")
    assert [p.suffix for p in paths] == [".json", ".csv"]

    data = json.loads(paths[0].read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["job_title"] == "算子开发工程师"
    assert len(data[0]["full_description"]) >= 50

    rows = list(csv.DictReader(io.StringIO(paths[1].read_text(encoding="utf-8-sig"))))
    assert len(rows) == 1
    assert rows[0]["company"] == "某芯片公司"


def test_export_skips_rejected_by_default(conn, tmp_path):
    json_path = export.export_jobs(conn, fmt="json",
                                   out_dir=tmp_path / "out")[0]
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(data) == 1

    json_path = export.export_jobs(conn, fmt="json", include_rejected=True,
                                   out_dir=tmp_path / "out2")[0]
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(data) == 2


def test_export_bad_format(conn, tmp_path):
    with pytest.raises(ValueError):
        export.export_jobs(conn, fmt="xlsx", out_dir=tmp_path / "out")
