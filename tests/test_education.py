"""学历解析与过滤测试。"""

from __future__ import annotations

import pytest

from jobscrape.discovery.base import EDU_UNLIMITED, apply_filters, parse_education

# 只接受要求本科 / 硕士的岗位
PROFILE = {"preferences": {"education": {"allowed": ["本科", "硕士"]}}}


def test_parse_level():
    assert parse_education("本科") == "本科"
    assert parse_education("硕士") == "硕士"
    assert parse_education("博士") == "博士"
    assert parse_education("大专") == "大专"
    assert parse_education("高中") == "高中"


def test_parse_normalization():
    assert parse_education("统招本科") == "本科"      # 猎聘写法
    assert parse_education("本科及以上") == "本科"    # Boss 写法，取基准档
    assert parse_education("学历不限") == EDU_UNLIMITED
    assert parse_education("不限学历") == EDU_UNLIMITED


def test_parse_unrecognized():
    # 年限/兼职标签不能被误判成学历
    assert parse_education("经验不限") is None
    assert parse_education("3-5年") is None
    assert parse_education("4天/周") is None
    assert parse_education("") is None


def _filter(edu_raw, profile=None):
    return apply_filters({"job_title": "算子开发", "education_raw": edu_raw},
                         profile or PROFILE)


def test_filter_keeps_allowed():
    assert _filter("本科") is None
    assert _filter("统招本科") is None
    assert _filter("本科及以上") is None
    assert _filter("硕士") is None


def test_filter_rejects_others():
    assert _filter("大专").startswith("education:")
    assert _filter("博士").startswith("education:")


def test_filter_unlimited():
    assert _filter("学历不限") is None  # 默认保留
    strict = {"preferences": {"education": {"allowed": ["本科"],
                                            "allow_unlimited": False}}}
    assert _filter("学历不限", strict).startswith("education:")


def test_filter_keeps_unknown():
    assert _filter("") is None
    assert _filter("4天/周") is None


def test_filter_disabled_by_default():
    assert _filter("博士", {"preferences": {}}) is None
    # allowed 为空视为不启用
    assert _filter("博士", {"preferences": {"education": {"allowed": []}}}) is None


def test_liepin_search_education_param():
    from jobscrape.discovery.liepin import LiepinDiscoverer

    d = LiepinDiscoverer()
    assert "eduLevel=040" in d.build_url("算子开发", "上海", {"education": "本科"})
    assert "eduLevel=030" in d.build_url("算子开发", "上海", {"education": "硕士"})
    # 猎聘没有可用的服务端年限参数，学历才行 —— 写错要显式报错
    with pytest.raises(ValueError):
        d.build_url("算子开发", "上海", {"education": "博士"})
    assert "eduLevel" not in d.build_url("算子开发", "上海", {})


def test_experience_and_education_independent():
    profile = {"preferences": {
        "experience": {"min_years": 0, "max_years": 3},
        "education": {"allowed": ["本科"]},
    }}
    assert apply_filters({"job_title": "x", "experience_raw": "1-3年",
                          "education_raw": "本科"}, profile) is None
    assert apply_filters({"job_title": "x", "experience_raw": "5-10年",
                          "education_raw": "本科"}, profile).startswith("experience:")
    assert apply_filters({"job_title": "x", "experience_raw": "1-3年",
                          "education_raw": "博士"}, profile).startswith("education:")
