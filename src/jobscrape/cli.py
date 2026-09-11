"""jp 命令行入口：登录 → 抓岗位列表 → 抓 JD 全文 → 导出。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import config, db, export

app = typer.Typer(help="JobScrape-CN：Boss 直聘 / 猎聘 岗位与 JD 全文抓取器")
console = Console()

PLATFORMS = ("boss", "liepin")


def _platforms(platform: str, default_all: bool = True) -> list[str]:
    if platform not in (*PLATFORMS, "all"):
        raise typer.Exit("platform 只能是 boss / liepin / all")
    return list(PLATFORMS) if platform == "all" else [platform]


@app.command()
def init(
    force: bool = typer.Option(False, "--force", help="覆盖已存在的 profile.json / searches.yaml"),
) -> None:
    """初始化 ~/.job-scrape-cn/：数据库 + 配置模板。"""
    config.runtime_dir()
    conn = db.connect()
    db.init_db(conn)
    conn.close()
    console.print(f"[green]OK[/] 已初始化 {config.runtime_dir()}")
    console.print(f"- 过滤配置: {config.init_profile(force=force)}")
    console.print(f"- 搜索配置: {config.init_searches(force=force)}")
    console.print("下一步：编辑上面两个文件，然后 jp login boss / jp login liepin 扫码登录")


@app.command()
def status() -> None:
    """各阶段计数板。"""
    conn = db.connect()
    db.init_db(conn)
    table = Table(title="JobScrape 状态")
    table.add_column("阶段")
    table.add_column("数量", justify="right")
    for k, v in db.counts(conn).items():
        table.add_row(k, str(v))
    conn.close()
    console.print(table)


@app.command()
def login(platform: str = typer.Argument(..., help="boss 或 liepin")):
    """打开浏览器扫码登录，持久化登录态（约一周有效）。"""
    if platform not in PLATFORMS:
        raise typer.Exit("platform 只能是 boss 或 liepin")
    from .discovery.browser import BrowserSession, save_cookies

    home = {"boss": "https://www.zhipin.com", "liepin": "https://www.liepin.com"}[platform]
    with BrowserSession(platform) as session:
        page = session.new_page()
        page.goto(home, wait_until="domcontentloaded", timeout=60_000)
        console.print("[yellow]请在浏览器中完成扫码登录[/]（猎聘为微信扫码）…")
        console.print("[dim]窗口保持打开：登录态会自动持续保存，用完直接关掉浏览器窗口即退出[/]")
        import time

        logged_in = False
        tick = 0
        while True:
            time.sleep(5)
            tick += 1
            closed = False
            try:
                closed = not session.context.pages
            except Exception:
                closed = True  # 浏览器进程已被关掉
            if not logged_in:
                if platform == "boss":
                    names = {c["name"] for c in session.context.cookies()}
                    logged_in = bool(names & {"wt2", "wt", "bst"})
                else:
                    # 双证据防假阳性：登录/注册消失 且 出现任一登录后导航词
                    try:
                        text = page.locator("body").inner_text(timeout=2_000)
                        logged_in = bool(text) and "登录/注册" not in text and any(
                            kw in text for kw in ("消息", "我的简历", "退出")
                        )
                    except Exception:
                        pass
                if logged_in:
                    console.print("[green]OK[/] 检测到登录态，已保存；浏览器留给你继续用")
            # 登录后每次落盘；未登录也每 30s 兜底存（检测失误也不丢态）
            if logged_in or closed or tick % 6 == 0:
                try:
                    save_cookies(session.context, platform)
                except Exception:
                    pass
            if closed:
                break
    console.print(f"[green]OK[/] 登录态已保存到 {config.cookies_dir() / f'{platform}.json'}")


@app.command()
def discover(
    platform: str = typer.Option("all", help="boss / liepin / all"),
    max_jobs: int = typer.Option(20, "--max", help="每个关键词抓取上限"),
) -> None:
    """只抓岗位列表入库（含纯代码过滤）。"""
    from .pipeline import RunOptions, run_pipeline

    result = run_pipeline(RunOptions(
        platforms=_platforms(platform), max_per_search=max_jobs, do_enrich=False,
    ))
    _print_result(result)


@app.command()
def enrich(
    platform: str = typer.Option("all", help="boss / liepin / all"),
    max_jobs: int = typer.Option(20, "--max", help="本轮抓 JD 的条数上限"),
) -> None:
    """给已入库岗位补抓 JD 全文（需登录态）。"""
    from .pipeline import RunOptions, run_pipeline

    result = run_pipeline(RunOptions(
        platforms=_platforms(platform), max_per_search=max_jobs, do_discover=False,
    ))
    _print_result(result)


@app.command(name="run")
def run_cmd(
    platform: str = typer.Option("all", help="boss / liepin / all"),
    max_jobs: int = typer.Option(20, "--max", help="每个关键词抓取上限（也是本轮抓 JD 上限）"),
) -> None:
    """完整流程：抓岗位列表 → 抓 JD 全文（幂等，可重跑续传）。"""
    from .pipeline import RunOptions, run_pipeline

    result = run_pipeline(RunOptions(
        platforms=_platforms(platform), max_per_search=max_jobs,
    ))
    _print_result(result)


@app.command(name="export")
def export_cmd(
    fmt: str = typer.Option("all", help="json / csv / all"),
    include_rejected: bool = typer.Option(False, help="一并导出被过滤的岗位"),
    out_dir: Optional[Path] = typer.Option(None, help="输出目录，默认 ~/.job-scrape-cn/exports/"),
) -> None:
    """导出已抓岗位（含 JD 全文）为 JSON / CSV。"""
    conn = db.connect()
    db.init_db(conn)
    rows = export.select_rows(conn, include_rejected=include_rejected)
    try:
        paths = export.export_jobs(conn, fmt=fmt, include_rejected=include_rejected,
                                   out_dir=out_dir)
    except ValueError as e:
        conn.close()
        raise typer.Exit(str(e))
    conn.close()
    console.print(f"[green]OK[/] 导出 {len(rows)} 条：")
    for p in paths:
        console.print(f"  {p}")


def _print_result(result) -> None:
    if result.stats:
        table = Table(title="执行统计")
        table.add_column("项")
        table.add_column("值", justify="right")
        for k, v in result.stats.items():
            table.add_row(k, str(v))
        console.print(table)
    if result.errors:
        console.print("[red]错误（不影响其他阶段，重跑 jp run 可续传）:[/]")
        for k, v in result.errors.items():
            console.print(f"  [red]-[/] {k}: {v[:200]}")


def main() -> None:
    app()
