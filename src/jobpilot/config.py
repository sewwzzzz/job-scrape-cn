"""运行时目录、profile / searches 配置加载与初始化。"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import yaml

PKG_DIR = Path(__file__).resolve().parent

# 默认过滤配置模板：jp init 写入 ~/.jobpilot-cn/profile.json 后由使用者编辑。
# 只有 preferences 生效，规则见 discovery/base.py 的 apply_filters。
DEFAULT_PROFILE = {
    "preferences": {
        # 标题命中任一正则即过滤（re.search）
        "title_blacklist": ["外包", "驻场", "实习"],
        # 公司名包含任一词即过滤
        "company_blacklist": [],
        # 薪资下限（K/月，按 12 个月折算中位数）；null = 不过滤
        "salary_min_k": None,
        # 年限：可接受区间 [min_years, max_years]，与岗位要求区间无交集则淘汰；
        # allow_unlimited=false 时连「经验不限」也淘汰；null = 不过滤
        "experience": None,
        # 学历白名单：岗位要求档位不在名单内则淘汰（'本科'/'硕士'/'博士'/'大专'…）；
        # allow_unlimited=false 时连「学历不限」也淘汰；null = 不过滤
        "education": None,
    },
}


def runtime_dir() -> Path:
    d = Path(os.environ.get("JOBPILOT_HOME", str(Path.home() / ".jobpilot-cn")))
    d.mkdir(parents=True, exist_ok=True)
    (d / "cookies").mkdir(exist_ok=True)
    (d / "exports").mkdir(exist_ok=True)
    return d


def db_path() -> Path:
    return runtime_dir() / "db.sqlite3"


def cookies_dir() -> Path:
    return runtime_dir() / "cookies"


def exports_dir() -> Path:
    return runtime_dir() / "exports"


def profile_path() -> Path:
    return runtime_dir() / "profile.json"


def searches_path() -> Path:
    return runtime_dir() / "searches.yaml"


def init_profile(force: bool = False) -> Path:
    """写入默认 profile.json；已存在且非 force 时跳过。返回文件路径。"""
    p = profile_path()
    if p.exists() and not force:
        return p
    p.write_text(json.dumps(DEFAULT_PROFILE, ensure_ascii=False, indent=2),
                 encoding="utf-8")
    return p


def init_searches(force: bool = False) -> Path:
    """从包内模板生成 searches.yaml；已存在且非 force 时跳过。"""
    p = searches_path()
    if p.exists() and not force:
        return p
    shutil.copy(PKG_DIR / "searches.example.yaml", p)
    return p


def load_profile() -> dict:
    p = profile_path()
    if not p.exists():
        raise FileNotFoundError(f"未找到 {p}。先运行: jp init")
    return json.loads(p.read_text(encoding="utf-8"))


def load_searches() -> dict:
    """加载搜索配置（每平台关键词 × 城市）；首次运行自动从包内模板生成。"""
    p = searches_path()
    if not p.exists():
        init_searches()
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    return {k: v for k, v in (data or {}).items() if k in ("boss", "liepin")}
