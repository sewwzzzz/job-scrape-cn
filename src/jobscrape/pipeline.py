"""pipeline 编排：discover（岗位列表）→ enrich（JD 全文）。

幂等性来自列级状态机：任何阶段崩溃，重跑 `jp run` 即续传，无需断点文件。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import config, db


@dataclass
class RunOptions:
    platforms: list[str] = field(default_factory=lambda: ["boss", "liepin"])
    max_per_search: int = 20
    do_discover: bool = True
    do_enrich: bool = True


@dataclass
class RunResult:
    errors: dict[str, str] = field(default_factory=dict)
    stats: dict[str, int] = field(default_factory=dict)


def run_pipeline(opts: RunOptions) -> RunResult:
    conn = db.connect()
    db.init_db(conn)
    result = RunResult()
    try:
        searches = config.load_searches()
        for platform in opts.platforms:
            if platform not in ("boss", "liepin"):
                result.errors[f"platform:{platform}"] = "只支持 boss / liepin"
                continue
            try:
                _run_platform(conn, platform, searches.get(platform, {}), opts, result)
            except Exception as e:  # 单平台崩溃不影响另一平台
                result.errors[f"browser:{platform}"] = str(e)
    finally:
        conn.close()
    return result


def _run_platform(conn, platform: str, conf: dict, opts: RunOptions,
                  result: RunResult) -> None:
    from .discovery.browser import BrowserSession
    from .discovery.boss import BossDiscoverer
    from .discovery.liepin import LiepinDiscoverer
    from .enrichment.detail import enrich_jobs

    if not (opts.do_discover or opts.do_enrich):
        return

    # discover 与 enrich 共用同一浏览器会话，登录态只验一次
    with BrowserSession(platform) as session:
        if opts.do_discover:
            discoverer = BossDiscoverer() if platform == "boss" else LiepinDiscoverer()
            keywords = conf.get("keywords", [])
            if not keywords:
                result.errors[f"discover:{platform}"] = "searches.yaml 无关键词"
            for kw in keywords:
                try:
                    jobs = discoverer.run(session.context, kw, conf,
                                          limit=opts.max_per_search)
                    new = sum(1 for j in jobs if db.upsert_job(conn, j))
                    result.stats[f"discover:{platform}:{kw}"] = new
                except Exception as e:
                    result.errors[f"discover:{platform}:{kw}"] = str(e)

        if opts.do_enrich:
            try:
                result.stats[f"enrich:{platform}"] = enrich_jobs(
                    conn, session, platform, limit=opts.max_per_search
                )
            except Exception as e:
                result.errors[f"enrich:{platform}"] = str(e)
