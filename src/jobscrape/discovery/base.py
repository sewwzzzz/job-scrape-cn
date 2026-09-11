"""Discoverer 公共基类 + 纯代码过滤链（不调用任何模型，规则可审计）。"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from .. import config


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


# 年限解析：「3-5年」「5年以上」「1年以下」「在校/应届」「经验不限」
_EXP_RANGE_RE = re.compile(r"(\d+)\s*-\s*(\d+)\s*年")
_EXP_ABOVE_RE = re.compile(r"(\d+)\s*年以上")
_EXP_BELOW_RE = re.compile(r"(\d+)\s*年(?:以下|以内)")  # Boss 写「1年以内」，猎聘用「以下」

# 「经验不限」的上界，视为极大值以参与区间求交
UNLIMITED_YEARS = 99


def parse_experience(text: str) -> tuple[int, int] | None:
    """年限文本 → (下限, 上限)；无法识别返回 None。

    '3-5年'→(3,5)｜'5年以上'→(5,99)｜'1年以下'/'1年以内'→(0,1)｜'在校/应届'→(0,0)
    '经验不限'→(0,99)｜'4天/周'、'6个月'等实习/兼职标签 → None
    """
    s = str(text or "").strip()
    if not s:
        return None
    if "不限" in s:
        return (0, UNLIMITED_YEARS)
    if "在校" in s or "应届" in s:
        return (0, 0)
    if m := _EXP_RANGE_RE.search(s):
        lo, hi = int(m.group(1)), int(m.group(2))
        return (min(lo, hi), max(lo, hi))
    if m := _EXP_ABOVE_RE.search(s):
        return (int(m.group(1)), UNLIMITED_YEARS)
    if m := _EXP_BELOW_RE.search(s):
        return (0, int(m.group(1)))
    return None


def is_unlimited_experience(text: str) -> bool:
    return bool(text) and "不限" in str(text)


# 学历：按「要求档位」归一，'统招本科' 视同 '本科'，'本科及以上' 取基准档 '本科'
EDU_UNLIMITED = "不限"
_EDU_RE = re.compile(
    r"(学历不限|不限学历|初中及以下|初中|高中|中专|中技|大专|统招本科|本科|硕士|博士)"
    r"(?:及以上|以上)?"
)
_EDU_ALIAS = {"统招本科": "本科"}


def parse_education(text: str) -> str | None:
    """学历文本 → 归一档位；无法识别返回 None。

    '本科'/'统招本科'/'本科及以上'→'本科'｜'学历不限'→'不限'｜'5天/周' → None
    """
    s = str(text or "").strip()
    if not s:
        return None
    if "学历不限" in s or "不限学历" in s:
        return EDU_UNLIMITED
    if m := _EDU_RE.search(s):
        return _EDU_ALIAS.get(m.group(1), m.group(1))
    return None


def experience_overlaps(job_range: tuple[int, int], lo: int, hi: int) -> bool:
    """岗位要求年限区间与可接受区间 [lo, hi] 是否有交集。

    岗位要求按**左开右闭** (jmin, jmax] 理解：「3-5年」= 要 3 年以上的人，
    刚满 3 年的应聘者不算，因此可接受 0-3 年时 [3,5] 必须判为无交集。
    退化区间（jmin == jmax，如「在校/应届」0-0）按闭点处理，避免空区间误杀。
    """
    jmin, jmax = job_range
    if jmin == jmax:
        return lo <= jmin <= hi
    return jmax > lo and jmin < hi


def apply_filters(job: dict[str, Any], profile: dict) -> str | None:
    """返回 reject_reason；None = 通过。

    顺序：标题黑名单 → 日结岗 → HR 不活跃 → 公司黑名单 → 薪资 → 年限 → 学历。
    """
    prefs = profile.get("preferences", {})
    title = job.get("job_title") or ""

    for pattern in prefs.get("title_blacklist", []):
        if re.search(pattern, title):
            return f"title_blacklist:{pattern}"

    if "元/天" in (job.get("salary_raw") or ""):
        return "daily_wage:日结岗"

    active = job.get("hr_active") or ""
    if active and ("月前活跃" in active or "年前活跃" in active):
        return f"hr_inactive:{active}"

    company = (job.get("company") or "").lower()
    for name in prefs.get("company_blacklist", []):
        if name.lower() in company:
            return f"company_blacklist:{name}"

    if job.get("salary_min") and job.get("salary_max"):
        salary_min_k = prefs.get("salary_min_k")
        if salary_min_k:
            months = job.get("salary_months") or 12
            median = (job["salary_min"] + job["salary_max"]) / 2 * months / 12
            if median < salary_min_k:
                return f"salary_below:{median:.0f}K < {salary_min_k}K"

    # 年限：岗位要求区间与可接受区间求交集，无交集则淘汰
    cfg = prefs.get("experience")
    if cfg:
        raw = job.get("experience_raw") or ""
        rng = parse_experience(raw)
        # 解析不出年限（如实习卡只有「4天/周」）→ 不误杀
        if rng is not None:
            if is_unlimited_experience(raw):
                # (0, 99) 与任何区间都有交集，只能单独判断
                if not cfg.get("allow_unlimited", True):
                    return f"experience:{raw}（已配置淘汰不限年限岗位）"
            else:
                lo = int(cfg.get("min_years", 0))
                hi = int(cfg.get("max_years", UNLIMITED_YEARS))
                if not experience_overlaps(rng, lo, hi):
                    return (f"experience:{raw}（按左开右闭 ({rng[0]},{rng[1]}] 年）"
                            f"不在可接受 {lo}-{hi} 年内")

    # 学历：岗位要求档位需在可接受名单内（白名单语义）
    edu_cfg = prefs.get("education")
    if edu_cfg:
        raw = job.get("education_raw") or ""
        level = parse_education(raw)
        if level is None:
            pass  # 解析不出学历 → 不误杀
        elif level == EDU_UNLIMITED:
            if not edu_cfg.get("allow_unlimited", True):
                return f"education:{raw}（已配置淘汰不限学历岗位）"
        else:
            allowed = {parse_education(x) or str(x).strip()
                       for x in edu_cfg.get("allowed", []) if str(x).strip()}
            if allowed and level not in allowed:
                return f"education:{raw} 不在可接受 {sorted(allowed)}"

    return None


class BaseDiscoverer:
    platform: str = ""

    def run(self, context, keyword: str, conf: dict,
            limit: int = 20) -> list[dict[str, Any]]:
        raise NotImplementedError

    def _finalize(self, raw_jobs: list[dict[str, Any]], keyword: str,
                  limit: int) -> list[dict[str, Any]]:
        """过滤链 + 公共字段补齐。"""
        profile = config.load_profile()
        jobs: list[dict[str, Any]] = []
        for j in raw_jobs[:limit * 3]:  # 过滤会淘汰一部分，多取一些
            job = {**j, "platform": self.platform, "search_source": keyword}
            reason = apply_filters(job, profile)
            if reason:
                job["reject_reason"] = reason
                job["rejected_at"] = now_iso()
            job.setdefault("discovered_at", now_iso())
            jobs.append(job)
            # 通过过滤的够数即停；被拒的继续收集（报告尾供翻案）
            if len([x for x in jobs if not x.get("reject_reason")]) >= limit:
                pass  # 通过过滤的够数即停，被拒岗继续收集（报告尾供翻案）
        return jobs
