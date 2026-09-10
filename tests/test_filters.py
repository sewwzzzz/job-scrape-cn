"""纯代码过滤链测试：标题黑名单 / 公司黑名单 / 薪资下限 / 日结岗。"""

from jobpilot.discovery.base import apply_filters

PROFILE = {
    "preferences": {
        "title_blacklist": ["外包", "实习"],
        "company_blacklist": ["某某人力"],
        "salary_min_k": 25,
    },
}


def test_pass():
    job = {"job_title": "算子开发工程师", "company": "某芯片公司",
           "salary_raw": "30-50K", "salary_min": 30, "salary_max": 50,
           "salary_months": 12}
    assert apply_filters(job, PROFILE) is None


def test_title_blacklist():
    assert apply_filters({"job_title": "外包装配工"}, PROFILE) == "title_blacklist:外包"


def test_company_blacklist():
    assert apply_filters({"job_title": "开发", "company": "某某人力资源"},
                         PROFILE) == "company_blacklist:某某人力"


def test_salary_below():
    job = {"job_title": "开发", "salary_raw": "10-20K",
           "salary_min": 10, "salary_max": 20, "salary_months": 12}
    reason = apply_filters(job, PROFILE)
    assert reason and reason.startswith("salary_below:")


def test_daily_wage():
    assert apply_filters({"job_title": "开发", "salary_raw": "500-800元/天"},
                         PROFILE) == "daily_wage:日结岗"
