"""猎聘城市过滤测试：dq 参数 + 客户端城市兜底。"""

from __future__ import annotations

from jobpilot.discovery.liepin import (
    CITY_CODES,
    LiepinDiscoverer,
    _norm_city,
    _parse_liepin_salary,
)


def _card(dq: str, job_id: str = "1") -> dict:
    return {
        "job": {"jobId": job_id, "title": "算子开发", "link": f"/job/{job_id}",
                "salary": "30-50K", "dq": dq},
        "comp": {"compName": "某芯片公司"},
        "recruiter": {},
    }


def test_norm_city():
    assert _norm_city("上海-浦东新区") == "上海"
    assert _norm_city("北京市") == "北京"
    assert _norm_city("上海") == "上海"
    assert _norm_city("") == ""


def test_build_url_uses_dq():
    url = LiepinDiscoverer().build_url("算子开发", "上海", {})
    assert "key=%E7%AE%97%E5%AD%90%E5%BC%80%E5%8F%91" in url  # quote("算子开发")
    assert f"city={CITY_CODES['上海']}" in url
    assert f"dq={CITY_CODES['上海']}" in url  # 只给 city 不会过滤，必须带 dq


def test_build_url_honors_city_codes_override():
    url = LiepinDiscoverer().build_url("算子开发", "火星",
                                       {"city_codes": {"火星": "999"}})
    assert "city=999" in url and "dq=999" in url


def test_map_card_keeps_allowed_city():
    d = LiepinDiscoverer()
    row = d._map_card(_card("上海-浦东新区"), "算子开发", {"上海", "北京"})
    assert row is not None
    assert row["city"] == "上海" and row["district"] == "浦东新区"


def test_map_card_drops_other_city():
    d = LiepinDiscoverer()
    # 猎聘 dq 过滤后仍会混入外地推荐卡，兜底必须挡掉
    assert d._map_card(_card("深圳-南山区"), "算子开发", {"上海"}) is None
    assert d._map_card(_card("深圳"), "算子开发", {"上海", "北京"}) is None


def test_map_card_keeps_unknown_city():
    # dq 为空无法判定，保留不误杀
    d = LiepinDiscoverer()
    assert d._map_card(_card(""), "算子开发", {"上海"}) is not None


def test_parse_liepin_salary():
    assert _parse_liepin_salary("25-45K") == (25, 45, 12)
    assert _parse_liepin_salary("3-5万") == (30, 50, 12)
    assert _parse_liepin_salary("面议") is None
