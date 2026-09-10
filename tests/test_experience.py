"""年限解析与过滤测试。"""

from __future__ import annotations

import pytest

from jobpilot.discovery.base import (
    UNLIMITED_YEARS,
    apply_filters,
    is_unlimited_experience,
    parse_experience,
)

# 可接受 0-3 年
PROFILE = {"preferences": {"experience": {"min_years": 0, "max_years": 3}}}


def test_parse_range():
    assert parse_experience("3-5年") == (3, 5)
    assert parse_experience("1-3年") == (1, 3)
    assert parse_experience("5-10年") == (5, 10)
    assert parse_experience("2-10年") == (2, 10)


def test_parse_open_ended():
    assert parse_experience("5年以上") == (5, UNLIMITED_YEARS)
    assert parse_experience("10年以上") == (10, UNLIMITED_YEARS)
    assert parse_experience("1年以下") == (0, 1)
    assert parse_experience("1年以内") == (0, 1)  # Boss 的写法


def test_parse_special():
    assert parse_experience("经验不限") == (0, UNLIMITED_YEARS)
    assert parse_experience("在校/应届") == (0, 0)


def test_parse_unrecognized():
    # 实习/兼职卡只有「4天/周」「6个月」这类标签，不该被当成年限
    assert parse_experience("4天/周") is None
    assert parse_experience("6个月") is None
    assert parse_experience("本科") is None
    assert parse_experience("") is None
    assert is_unlimited_experience("经验不限") is True
    assert is_unlimited_experience("3-5年") is False


def _filter(exp_raw):
    return apply_filters({"job_title": "算子开发", "experience_raw": exp_raw}, PROFILE)


def test_filter_keeps_overlapping():
    assert _filter("1-3年") is None
    assert _filter("经验不限") is None


def test_filter_rejects_high_requirement():
    assert _filter("5-10年").startswith("experience:")
    assert _filter("5年以上").startswith("experience:")


def test_filter_left_open_right_closed():
    """岗位要求按左开右闭 (jmin, jmax]：可接受 0-3 年时，[3,5] 不该被算作有交集。"""
    assert _filter("3-5年").startswith("experience:")   # (3,5] 与 [0,3] 无交集
    assert _filter("3年以上").startswith("experience:")  # (3,99] 同理
    assert _filter("2-10年") is None                     # (2,10] 与 [0,3] 有交集
    assert _filter("1年以内") is None                     # (0,1] 与 [0,3] 有交集


def test_filter_degenerate_range():
    # 「在校/应届」退化区间 (0,0] 为空，按闭点处理，避免误杀应届生
    assert _filter("在校/应届") is None
    fresh = {"preferences": {"experience": {"min_years": 0, "max_years": 0}}}
    assert apply_filters({"job_title": "x", "experience_raw": "在校/应届"},
                         fresh) is None
    # 但 3 年经验的人不会被应届岗留下
    assert apply_filters({"job_title": "x", "experience_raw": "在校/应届"},
                         {"preferences": {"experience": {"min_years": 3,
                                                         "max_years": 5}}},
                         ).startswith("experience:")


def test_filter_keeps_unknown():
    # 解析不出年限的不误杀
    assert _filter("") is None


def test_filter_disallow_unlimited():
    profile = {"preferences": {"experience": {"min_years": 0, "max_years": 3,
                                              "allow_unlimited": False}}}
    assert apply_filters({"job_title": "算子开发", "experience_raw": "经验不限"},
                         profile).startswith("experience:")


def test_filter_disabled_by_default():
    # 不配 experience 就不做年限过滤
    assert apply_filters({"job_title": "算子开发", "experience_raw": "10年以上"},
                         {"preferences": {}}) is None


def test_boss_search_experience_param():
    from jobpilot.discovery.boss import BossDiscoverer

    d = BossDiscoverer()
    assert "experience=105" in d.build_url("算子开发", "北京", {"experience": "3-5年"})
    assert "experience=103" in d.build_url("算子开发", "北京", {"experience": "1年以内"})
    # 服务端参数实测只支持这几档，写错要显式报错而不是静默失效
    with pytest.raises(ValueError):
        d.build_url("算子开发", "北京", {"experience": "3年"})
    # 不配就不带参数
    assert "experience" not in d.build_url("算子开发", "北京", {})


def test_boss_search_education_param():
    from jobpilot.discovery.boss import BossDiscoverer

    d = BossDiscoverer()
    assert "degree=203" in d.build_url("算子开发", "北京", {"education": "本科"})
    assert "degree=205" in d.build_url("算子开发", "北京", {"education": "博士"})
    with pytest.raises(ValueError):
        d.build_url("算子开发", "北京", {"education": "博士后"})
    assert "degree" not in d.build_url("算子开发", "北京", {})
