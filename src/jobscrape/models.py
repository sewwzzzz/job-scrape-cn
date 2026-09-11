"""列级状态谓词：某阶段完成 = 该阶段负责的列非 NULL。

集中定义，所有阶段与 status 计数板复用；阶段间零直接调用，靠这些谓词衔接。
"""

from __future__ import annotations

from datetime import datetime


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


# 待抓 JD：已发现、未抓、未被过滤
PENDING_ENRICH = (
    "discovered_at IS NOT NULL AND detail_scraped_at IS NULL AND reject_reason IS NULL"
)

# 抓 JD 失败过（可排查后重跑 enrich 再试）
ENRICH_FAILED = (
    "detail_scraped_at IS NULL AND enrich_error IS NOT NULL AND reject_reason IS NULL"
)
