# M6 脱敏扫描留档（发布前终扫）

> 记录时间：2026-10-18（M6 发布执行中，git tag 之前）。
> 扫描对象：本仓库工作树（git ls-files 全部入库文本文件）+ 全历史（`git rev-list --all`
> 逐 rev `git grep`，blob 级）+ 干净 clone（`git clone --no-local` 副本复扫）。
> 留档纪律：命中词面不复述；扫描模式以掩码/自引用形式出现于扫描器
> `scripts/check_release.py`（属模式定义，非泄露）。

## 一、扫描口径

| 类别 | 模式（措辞描述） | 级别 |
| --- | --- | --- |
| 盘符绝对路径 | 任意盘符 + 用户目录 / 系统程序数据目录（首字母 P 开头） / Documents and Settings 前缀（正斜杠与反斜杠两形态） | FAIL |
| MSYS 绝对路径 | `/x/` + 用户目录 / 系统程序数据目录 / home 前缀形态 | FAIL |
| 本系列工作区标记 | 「系统程序数据目录 / 本系列工作区父目录」组合路径签名（首字母 P/z 开头，词面不复述） | FAIL |
| 系统用户名 | 运行时取 `USERNAME`/`USER`，长度 ≥3 且非通用占位（public/runner/example 等白名单除外） | FAIL |
| 邮箱 | 非 GitHub noreply 且非 RFC 2606 保留域（example.com 等）的邮箱 | FAIL |
| 凭据 | GitHub token / OpenAI key / 私钥头 | FAIL |
| 系列品牌词 | 本系列其他项目名（data/README §五 品牌隔离） | 人工复核 |

## 二、扫描结果（终态）

| 扫描面 | 结果 | 证据 |
| --- | --- | --- |
| 工作树（89 个入库文本文件） | **0 命中**（扫描器自身模式行除外） | `py -X utf8 scripts/check_release.py --pre-tag` → `TRACKED_LEAKS PASS`（扫描 89 个文本文件） |
| 全历史（10 个 rev） | **0 命中**（阳性对照通过） | 同上 → `HISTORY_LEAKS PASS`（阳性对照 chartaudit 命中 220 文件·rev，通道有效） |
| 干净 clone（`--no-local`） | 工作树 0 命中 / 全历史仅扫描器自引用 1 处 | clone 副本 `git grep` 复扫；唯一命中为 `scripts/check_release.py` 的模式定义行（第 399/400/442/494-496 行），属模式自引用，非本机路径泄露 |
| 提交邮箱 | 全部为 GitHub noreply（1 个唯一值） | `COMMIT_EMAILS PASS` |
| 垃圾文件 | 0（无 `__pycache__` / `.pyc` / `out/` / `dist/` / 日志入库） | `TRACKED_JUNK PASS`（89 个文件） |

**阳性对照纪律**：历史扫描先以必然存在的关键词（`chartaudit`）验证通道有效
（220 个文件·rev 命中），再做 0 命中结论——"扫了 0 命中"与"扫描没工作"已区分。

## 三、发现与处置（如实留档）

| # | 发现 | 处置 |
| --- | --- | --- |
| 1 | `plan/HANDOFF-M1.md` 续接提示词含本机盘符绝对路径（Windows 形态，1 处） | 改为仓库相对路径 `plan/HANDOFF-M1.md` |
| 2 | `plan/HANDOFF-M1~M5.md` 命令速查含本机工作区 MSYS 绝对路径（`cd` 行，24 处文件·rev） | 全部替换为 `cd "$(git rev-parse --show-toplevel)"` |
| 3 | `plan/HANDOFF-M2.md` §4 环境坑示例含盘符用户目录路径（1 处） | 措辞改为"系统临时目录"，去路径形态 |
| 4 | `plan/HANDOFF-M6.md` §2 待办含盘符路径示例（2 处） | 措辞改为"盘符绝对路径 / 用户目录" |
| 5 | 上述 1–4 均已存在于历史提交（共 7 个 rev 的旧 blob） | **`git filter-repo --replace-text` 重写全历史**（替换目标=通用词；重写前备份 bundle 于仓外），重写后全历史复扫 0 命中 || 6 | 测试夹具 `tests/test_whitelist.py` 含 `someone@example.com` | 判定为 RFC 2606 保留域占位邮箱（该测试正是验证"邮箱痕迹被白名单校验拒绝"），非真实身份泄露；扫描器对保留域放行并在本表留档 |

**历史重写记录**：`git filter-repo --replace-text`（正则替换盘符绝对路径 →
通用词）+ `--replace-refs delete-no-add`；重写前仓外备份
`10-18-truth-chart-skill-pre-scrub.bundle`（221,853 字节）。重写后旧短 sha
全部失效，活文档引用按新历史核对（`git log --oneline` 10 个提交，无悬挂引用）。

## 四、品牌隔离复核（人工项）

- 全仓检索本系列其他项目名（data/README §五 所列品牌词族）：0 命中（工作树与全历史）。
- 仓库名 / Skill 名 / 文档只使用本题自有名称 `chartaudit` / `10-18-truth-chart-skill`。

## 五、隐私声明对齐

- "纯本地处理、零上传"措辞的审计范围：引擎运行时零第三方依赖（pyproject
  `dependencies = []`）、HTML 零外链（`http(s)://` 静态扫描门在 bench 与 pytest
  双通道）、无网络调用代码路径（标准库导入面仅 `csv/json/os/re/hashlib/...`，
  无 `urllib`/`requests`/`socket`）——措辞与扫描范围对齐。
