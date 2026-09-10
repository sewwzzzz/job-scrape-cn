# 变更记录

> 供后续接手的 Agent / 开发者快速对齐上下文。
>
> 标记约定：`[新增]` 新功能 · `[修复]` 修缺陷 · `[变更]` 改行为/重构 · `[删除]` 移除
> 状态约定：`[已完成]` · `[进行中]` · `[待办]`

## 当前仓库定位（2026-09-10 起）

jobpilot-cn = **只做数据采集**：抓 Boss 直聘 / 猎聘岗位列表 → 抓 JD 全文 → 导出 JSON/CSV。
不含任何 AI 分析、打分、打招呼语、简历定制逻辑，不依赖 LLM API Key。

## 本次会话的改造（全部 [已完成]）

### [删除] 剔除 AI 分析与一次性脚本

- `src/jobpilot/llm.py`、`src/jobpilot/scoring/`（score / greet / tailor / validator）
- `src/jobpilot/prompts/`（3 个 prompt 文本）、`src/jobpilot/report.py`
- `scripts/`（build_profile + 4 个猎聘探针/校准脚本）、`examples/`、`tests/test_score_parser.py`、`tests/test_validator.py`
- `.env.example`、根 `searches.example.yaml`（内容移入包内）
- 依赖：`openai`、`anthropic`、`pydantic`（未使用）

### [变更] 核心链路改造

- `db.py`：表结构精简为 discover / enrich / 过滤三块列，删掉 score、greet、tailor、人工回路列；`counts()` 改为「总岗位 / 已有 JD / 待抓 JD / 抓 JD 失败 / 已过滤」
- `models.py`：只保留 `PENDING_ENRICH`、`ENRICH_FAILED`、`now_iso()`
- `config.py`：去掉 `.env` 与 `llm_settings()`、`load_resume()`；新增 `init_profile()` / `init_searches()`；模板随包分发（`src/jobpilot/searches.example.yaml`，用 `PKG_DIR` 定位，安装后仍可用）
- `pipeline.py`：只编排 discover → enrich；`RunOptions(platforms, max_per_search, do_discover, do_enrich)`
- `cli.py`：命令收敛为 `init / status / login / discover / enrich / run / export`
- `__init__.py`、`discovery/base.py`、`ATTRIBUTION.md` 去掉 LLM/防虚构相关表述

### [新增]

- `src/jobpilot/export.py` + `jp export`：导出 JSON / CSV（含 JD 全文，CSV 带 UTF-8 BOM，默认输出 `~/.jobpilot-cn/exports/`，支持 `--fmt` / `--include-rejected` / `--out-dir`）
- `tests/test_export.py`、`tests/test_filters.py`
- README 增加「数据」节的 DBeaver 直连查看说明与常用 SQL

### [修复]

- Windows GBK 控制台崩溃：`cli.py`、`discovery/browser.py` 里打印的 `✓` / `⚠️` 换成 ASCII 标记（`OK`、`[!]`）。原代码在中文 Windows 上执行 `jp init` 会直接 `UnicodeEncodeError`

### 验证结果

- `pytest`：14 项通过（薪资解析 / 过滤规则 / 导出）
- CLI 冒烟：`jp init`、`jp status`、`jp export` 正常；`jp discover` 在无浏览器/无登录态时把错误收进结果表，不崩
- 已装 Chromium 并验证 `BrowserSession` 可启动、可保存登录态
- `uv.lock` 已用 uv 0.12.12 重新生成

## 关键设计约束（改动时别破坏）

1. **列级状态机 = 阶段契约**：阶段完成 = 该阶段负责的列非 NULL；`jp run` 靠这个幂等续传，不要引入断点文件
2. **discovery 只写 discover 列，enrichment 只写 enrich 列**，跨模块写列会破坏续传语义
3. **入库是 INSERT + 主键冲突跳过**（url 为主键），天然去重、不覆盖已有行
4. **被过滤岗位不会自动翻案**：`PENDING_ENRICH` 要求 `reject_reason IS NULL`，放宽规则后需先 `UPDATE jobs SET reject_reason=NULL` 才会重新抓 JD
5. **enrich 最多重试 3 次**（`enrich_attempts < 3`），修好选择器后要重跑需先清失败行或清 `enrich_attempts`
6. Playwright 只在 `discovery/browser.py` 单点封装，选择器集中在各平台模块的 `LOCATORS`
7. 运行时目录 = `$JOBPILOT_HOME` 或 `~/.jobpilot-cn`（Windows 上即 `C:\Users\<用户>\.jobpilot-cn`，这是设计而非 bug）

## 后续迭代

### [修复] [已完成] 猎聘城市串号：结果里混入大量非配置城市

- 现象：猎聘抓到的岗位城市大量不在 `searches.yaml` 的 `cities` 中；Boss 正常
- 根因（2026-09 实测）：猎聘搜索真正生效的过滤参数是 **`dq`（地区）**，不是 `city`。
  只传 `city=020` 时 XHR 请求体是 `city:"020", dq:"410"`，结果覆盖全国（实测 42 张卡散落在
  深圳/杭州/南京/西安/北京/成都…）；传 `dq=020` 或 `city=020&dq=020` 时结果 40/42 为上海
- 改动：`discovery/liepin.py`
  - `build_url` 同时带 `city` 与 `dq`
  - 新增客户端兜底：按配置城市集过滤，`dq` 为空才保留（不误杀），丢弃数打印为
    `[liepin] 跳过 N 条城市不在配置内的岗位`
  - 新增 `_norm_city()`（「上海-浦东新区」→「上海」、「北京市」→「北京」）
- 验证：实跑 `cities=["上海"]` 得 15 条全为上海，0 条外地；单测 `tests/test_liepin_city.py`

### [新增] [已完成] 年限作为过滤 / 查找条件

- **本地过滤（两平台通用）**：`profile.json` 的 `preferences.experience`
  `{min_years, max_years, allow_unlimited}`，岗位要求年限区间与可接受区间**无交集**则淘汰，
  `reject_reason` 记 `experience:...`
- **年限字段**：新增 `jobs.experience_raw`（岗位年限原文），Boss 从卡片标签解析、
  猎聘取 `requireWorkYears`；已加入导出 CSV/JSON；`init_db` 带 `ALTER TABLE` 补列，旧库自动升级
- **服务端查找（仅 Boss）**：`searches.yaml` 的 `boss.experience`（`1年以下`/`1-3年`/`3-5年`/
  `5-10年`/`10年以上` → 103/104/105/106/107，2026-09 逐档实测 15/15 全中）；写非法值直接报错
- 猎聘 `workYearCode=` URL 参数实测**不生效**（结果仍混杂各年限），故猎聘只走本地过滤，
  配了 `experience` 会打印提示
- 解析规则：`discovery/base.py` 的 `parse_experience()`，覆盖 `3-5年`/`5年以上`/`1年以下`/
  `1年以内`（Boss 写法）/`在校/应届`/`经验不限`；`4天/周`、`6个月` 等实习标签返回 None 不误杀
- 验证：31 项单测通过；实跑 Boss `experience=105` 得 15/15 `3-5年`，猎聘年限字段全部有值

### [新增] [已完成] 学历作为过滤 / 查找条件

- **本地过滤（两平台通用）**：`profile.json` 的 `preferences.education`
  `{allowed: [...], allow_unlimited}`，白名单语义，岗位要求档位不在名单内则淘汰，
  `reject_reason` 记 `education:...`；解析不出学历时不淘汰
- **学历字段**：新增 `jobs.education_raw`（学历要求原文），Boss 从卡片标签解析、
  猎聘取 `requireEduLevel`；已进导出；`init_db` 补列，旧库自动升级
- **档位归一**：`parse_education()` 把 `统招本科`（猎聘写法）→ `本科`、
  `本科及以上`（Boss 写法）→ `本科`；`学历不限`→`不限`；`经验不限`/`3-5年` 不会被误判为学历
- **服务端查找（两平台都支持，与年限不同）**：`searches.yaml` 的 `education`
  - Boss `&degree=`：高中 206 / 大专 202 / 本科 203 / 硕士 204 / 博士 205（逐档实测 15/15 全中；
    201 是「本科及以上」混合档，不采用）
  - 猎聘 `&eduLevel=`：本科 040 / 硕士 030 / 大专 050（实测本科 40/42、硕士 26/42；
    020 与 030 结果相同，博士档无法确认，未内置）
  - 写非法值直接报错
- 验证：42 项单测通过；实跑 Boss `degree=203` 得 15/15 本科，猎聘 `eduLevel=040` 得
  统招本科 21 + 本科 9（0 例外）

### [变更] [已完成] 年限区间改为左开右闭

- 原因：可接受区间 `[a,b]` 时，要求 `[b,c]`（`3-5年`）的岗位因边界 b 相交被误留；语义上
  「年限在 b 以上」的岗位不会考虑 `[a,b]` 年限的应聘者
- 改动：`discovery/base.py` 新增 `experience_overlaps()`，岗位要求区间按**左开右闭 `(jmin, jmax]`**
  与可接受闭区间 `[lo, hi]` 求交 → 有交集条件为 `jmax > lo 且 jmin < hi`
- 退化区间（`jmin == jmax`，如「在校/应届」0-0）按闭点 `lo <= j <= hi` 处理，避免空区间误杀应届生
- 行为变化（可接受 0-3 年为例）：`3-5年`、`3年以上` 由「保留」变为「淘汰」；
  `1-3年`、`2-10年`、`1年以内` 仍保留
- 验证：44 项单测通过，新增 `test_filter_left_open_right_closed` / `test_filter_degenerate_range`

## 待办（用户提出但尚未实施）

| 状态 | 标记 | 事项 |
| --- | --- | --- |
| [待办] | [新增] | `jp login` 检测到登录态后自动退出（可加 `--wait` 保留现阻塞行为）；当前必须手动关掉浏览器窗口或 Ctrl+C |
| [待办] | [新增] | `jp prune` 清理命令（`--failed` / `--rejected` / `--platform`），替代手写 DELETE SQL |
| [待办] | [新增] | 关键词归一化：加载 `searches.yaml` 时去首尾空格、折叠连续空格 |
| [待办] | [变更] | `jp init --dir` 参数，或把默认运行时目录改为仓库内（用户此前疑惑「为什么 init 到 C 盘」，尚未定方案） |
| [待办] | [修复] | 猎聘服务端年限筛选：目前只知道 `workYearCode=` 无效，尚未找到真正生效的参数（本地过滤已可用） |
| [待办] | [新增] | 猎聘学历参数缺「博士」档：020 与 030 返回结果相同，无法确认，暂未内置 |
| [待办] | [新增] | Boss 年限参数只验证了 103-107；`101`（经验不限）/ `102`（在校应届）未实测，暂未内置 |

## 环境备注

- 本机 PATH 里**没有 uv**；本次是用临时 `.venv` 里的 uv 生成的 lock。用户如果用 uv，需自行安装
- 验证用的 `.venv/` 仍在工作区（已 gitignore），删除操作未获授权，可安全删除
- Chromium 已下载到用户级 `%LOCALAPPDATA%\ms-playwright`，不在仓库内，换机器需重跑 `playwright install chromium`
- 系统 Python 3.13.13
