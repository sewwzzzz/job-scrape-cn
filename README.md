# JobPilot-CN

国内招聘平台**岗位与 JD 全文抓取器**：抓岗位列表 → 抓 JD 全文 → 导出 JSON / CSV。

只做数据采集，**不含任何 AI 分析、打分、简历定制逻辑，也不需要任何 LLM API Key**。
**复用代码**，原作者仓库[job-pilot-cn](https://github.com/GriffithLin/job-pilot-cn)，在此基础上改成自用版本。

## 能做什么

| 平台 | 列表页采集方式 | JD 全文方式 |
| --- | --- | --- |
| Boss 直聘 | 搜索页滚动加载 + DOM 卡片解析，薪资走字体反爬解码 | 优先拦截 `job/detail.json` 接口 JSON，失败降级 DOM 选择器 |
| 猎聘 | 拦截搜索页 `pc-search-job` XHR JSON + AntD 翻页 | 详情页 DOM 轮询（React SPA 水合较慢，等待最多 15s） |

- **SQLite 单表数据总线**：一列即一个阶段的状态，`jp run` 幂等可续传，中断后重跑只补未完成的。
- **纯代码过滤**：标题黑名单 / 日结岗 / HR 不活跃 / 公司黑名单 / 薪资下限，规则写在 `profile.json`，不依赖任何模型。
- **浏览器单点封装**：Playwright 只用 `discovery/browser.py` 一个出口，含登录态持久化与验证页人工暂停。

## 安装

```powershell
# 方式一：uv（推荐）
uv sync
uv run playwright install chromium

# 方式二：pip
python -m venv .venv
.venv\Scripts\activate
pip install -e .
playwright install chromium
```

要求 Python 3.11+。浏览器底座（Chromium）必须装，否则 `jp discover / enrich / run` 会报
`Executable doesn't exist`。

## 快速开始

```powershell
# 1. 初始化运行时目录 ~/.jobpilot-cn/（数据库 + 配置模板）
jp init
#    生成两个文件，按需编辑：
#    ~/.jobpilot-cn/searches.yaml  关键词 × 城市
#    ~/.jobpilot-cn/profile.json   过滤规则

# 2. 扫码登录（登录态保存在 ~/.jobpilot-cn/cookies/，约一周有效）
jp login boss
jp login liepin

# 3. 抓岗 + 抓 JD（每日一次即可）
jp run --max 20              # 两个平台；--platform boss 只抓 Boss

# 4. 导出
jp export                    # JSON + CSV 写到 ~/.jobpilot-cn/exports/
jp export --fmt csv --out-dir D:\data
```

运行时目录可用环境变量 `JOBPILOT_HOME` 改到别处。

## 命令一览

| 命令 | 作用 |
| --- | --- |
| `jp init [--force]` | 建库并生成 `profile.json` / `searches.yaml` 模板（`--force` 覆盖） |
| `jp login boss\|liepin` | 开浏览器扫码登录，关掉窗口即保存登录态 |
| `jp discover [--platform all] [--max 20]` | 只抓岗位列表入库 |
| `jp enrich [--platform all] [--max 20]` | 只给已入库岗位补抓 JD 全文（本轮最多 `--max` 条，可重复跑续抓） |
| `jp run [--platform all] [--max 20]` | discover + enrich，一条命令跑完（幂等，可重复跑） |
| `jp export [--fmt json\|csv\|all] [--include-rejected] [--out-dir PATH]` | 导出数据 |
| `jp status` | 计数板：总岗位 / 已有 JD / 待抓 JD / 抓 JD 失败 / 已过滤 |

`--max` 既是「每个关键词 × 每个城市」的列表抓取上限，也是**本轮抓 JD 的条数上限**。

**JD 是可续抓的**：`jp enrich` 每次只从「还没抓过 JD」的行里取最多 `--max` 条，抓满即停。
所以岗位总数多于 `--max` 时，会有部分行的 `full_description` 仍为空——这是正常的，再跑几次
就补齐（已完成的行不会被重复抓取，靠 `detail_scraped_at` 判断）：

```powershell
jp enrich --max 50      # 跑完看 jp status 的「待抓 JD」，不为 0 就再跑一次
```

每条之间随机间隔 2-4 秒（防风控），50 条约 3 分钟；中途 Ctrl+C 无害，重跑会接着补。

## 配置

### `~/.jobpilot-cn/searches.yaml`

```yaml
boss:
  keywords: ["算子开发", "GPU 优化", "CUDA"]
  cities: ["北京", "上海", "深圳"]
  # 可选：city_codes: {苏州: "101190400"}   # 覆盖内置城市代码
  # 可选：boss_salary: "402"                # Boss 的薪资筛选参数
  # 可选：experience: "3-5年"               # 服务端年限筛选，见下

liepin:
  keywords: ["算子开发", "异构计算"]
  cities: ["北京", "上海"]
  max_pages: 3                              # 翻页上限
```

**年限（查找条件，仅 Boss）**：`experience` 会拼成 `&experience=<code>` 让服务端先筛一轮，
实测有效的档位只有这些（2026-09 验证，每档 15 张卡全中）：

| 取值 | 含义 |
| --- | --- |
| `1年以下` / `1年以内` | 103 |
| `1-3年` | 104 |
| `3-5年` | 105 |
| `5-10年` | 106 |
| `10年以上` | 107 |

**学历（查找条件，两平台都支持）**：`education` 拼成 Boss 的 `&degree=` / 猎聘的 `&eduLevel=`，
2026-09 实测档位：

| 取值 | Boss | 猎聘 |
| --- | --- | --- |
| `高中` | 206 | — |
| `大专` | 202 | 050 |
| `本科` | 203 | 040 |
| `硕士` | 204 | 030 |
| `博士` | 205 | 未内置（020/030 返回结果相同，无法确认） |

写其它值会直接报错（不静默失效）。猎聘的 URL **年限**参数实测不改变结果，配了只会打印提示，
年限筛选请用下面的本地过滤；学历则两平台都可用服务端参数。

内置城市代码见 `src/jobpilot/discovery/boss.py` 与 `.../liepin.py` 的 `CITY_CODES`。

### `~/.jobpilot-cn/profile.json`

```json
{
  "preferences": {
    "title_blacklist": ["外包", "驻场", "实习"],
    "company_blacklist": [],
    "salary_min_k": 25,
    "experience": {"min_years": 0, "max_years": 3, "allow_unlimited": true},
    "education": {"allowed": ["本科", "硕士"], "allow_unlimited": true}
  }
}
```

- `title_blacklist`：标题正则（`re.search`），命中即过滤
- `company_blacklist`：公司名子串，命中即过滤
- `salary_min_k`：薪资下限（K/月，按 12 个月折算中位数）；`null` 表示不过滤
- `experience`：可接受年限区间 `[min_years, max_years]`（闭区间），与岗位要求年限**无交集**则淘汰
  - **岗位要求按左开右闭 `(jmin, jmax]` 理解**：「3-5年」= 要 3 年以上的人，刚满 3 年不算
  - 例：可接受 `0-3` 年时，`1-3年` 通过、`2-10年` 通过、`3-5年` 淘汰、`3年以上` 淘汰
  - 「在校/应届」（0-0 退化区间）按闭点处理：只招应届的岗位不会误杀应届生，但也不会留住 3 年经验的人
  - `allow_unlimited: false` 会把「经验不限」的岗位也淘汰（默认 `true` 保留）
  - 岗位年限解析不出来（如实习卡只有「4天/周」标签）时不淘汰，避免误杀
  - `null` 表示不做年限过滤
  - 该过滤两平台通用，猎聘只能走这一条（它没有可用的服务端年限参数）
- `education`：学历白名单，岗位要求档位不在名单内则淘汰
  - 档位归一：`统招本科` → `本科`（猎聘写法），`本科及以上` → `本科`（Boss 写法）
  - `allow_unlimited: false` 会把「学历不限」的岗位也淘汰（默认 `true` 保留）
  - 解析不出学历时不淘汰；`null` 表示不做学历过滤

被过滤的岗位仍会入库并记录 `reject_reason`，默认不导出，加 `--include-rejected` 可导出查看。

## 数据

SQLite 单表 `jobs`（`~/.jobpilot-cn/db.sqlite3`，WAL 模式），主键为岗位 URL。导出字段：

`platform, job_title, company, city, district, salary_raw, salary_min, salary_max,
salary_months, experience_raw, education_raw, job_tags, hr_name, hr_title, hr_active,
search_source, url, apply_url, full_description, discovered_at, detail_scraped_at,
reject_reason`

其中 `experience_raw` 是岗位要求年限原文（`3-5年` / `经验不限` / `10年以上`…），
`education_raw` 是学历要求原文（`本科` / `统招本科` / `硕士` / `学历不限`…），
Boss 取自卡片标签，猎聘取自 `requireWorkYears` / `requireEduLevel`；实习/兼职卡可能为空。
**升级前抓的旧行这两列为空**，年限/学历过滤对它们不生效，需要重抓或手动补。

CSV 为 UTF-8 BOM，Excel 双击直接打开不乱码。

不导出数据也一直在库里（`jp export` 只是快照）。想直接查库，用任意 SQLite 客户端打开
`~/.jobpilot-cn/db.sqlite3` 即可，例如 DBeaver CE：

1. 数据库 → 新建连接 → 选 **SQLite** → Path 选 `~/.jobpilot-cn/db.sqlite3` → 完成
2. 首次会提示下载 SQLite JDBC 驱动，允许联网下载（离线环境会卡在这一步）
3. 展开库 → `jobs` 表 → 「数据」页查看

注意两点：

- 别只把 `db.sqlite3` 拷到别处打开：WAL 模式下最近的写入可能还在 `db.sqlite3-wal` 里，
  单独拷走会看不到最新数据。要拷贝就连同 `-wal` / `-shm` 一起拷，或直接在原路径打开。
- 建议只读（DBeaver 编辑连接里勾选 Read-only connection）。改坏状态列会让 `jp run` 的
  续传判断出错，例如清空 `detail_scraped_at` 会导致 JD 被重复抓取。

常用查询：

```sql
SELECT platform, COUNT(*) 岗位数,
       SUM(full_description IS NOT NULL) 有JD,
       SUM(reject_reason IS NOT NULL) 已过滤
FROM jobs GROUP BY platform;

SELECT job_title, company, salary_raw, city, url
FROM jobs WHERE full_description IS NOT NULL
ORDER BY discovered_at DESC LIMIT 50;
```

## 项目结构

```
src/jobpilot/
├── cli.py            # Typer 命令行入口
├── config.py         # 运行时目录、profile / searches 加载
├── db.py             # SQLite 单表 + upsert/查询
├── models.py         # 列级状态谓词（阶段衔接契约）
├── pipeline.py       # discover → enrich 编排
├── export.py         # JSON / CSV 导出
├── discovery/        # browser.py（Playwright 唯一出口）+ base.py + boss.py + liepin.py
├── enrichment/       # detail.py：JD 全文抓取
└── searches.example.yaml  # 搜索配置模板（jp init 复制到运行时目录）
tests/                # pytest：薪资解析 / 过滤规则 / 导出
```

## 维护与排错

- **抓不到列表 / 字段为空**：平台改版，改 `discovery/boss.py`、`discovery/liepin.py` 顶部的
  `LOCATORS`（选择器）与 `XHR_MARKER`（接口特征），其余代码不用动。
- **抓 JD 失败**：`jp status` 看「抓 JD 失败」数，`enrich_error` 列有原因（多为选择器过期或
  未登录）；重试 3 次后不再自动重试，修好后重跑 `jp enrich` 即可。
- **登录态失效**：重新 `jp login <平台>`。
- **遇到滑块 / 验证页**：程序会暂停并提示人工处理，不会自动过验证（交互终端等回车，
  非交互环境最多等 10 分钟）。
- 跑测试：`uv run pytest`（或激活虚拟环境后 `pytest`）。

## 使用须知

- 本项目仅供**学习研究**与**个人求职**使用；请遵守目标平台用户协议，使用产生的一切风险与
  责任由使用者自行承担。
- 不用于任何商业用途；请保持低频使用（建议每日不超过一次、每平台 ≤ 20-40 岗），
  切勿循环轮询，勿对平台造成负担。

## License

[MIT](LICENSE)
