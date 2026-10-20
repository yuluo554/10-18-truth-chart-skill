# plan/RELEASE-v0.1.1.md — 发布留档（v0.1.1，2026-10-20）

> 版本：**v0.1.1**。本文件按 `plan/00` §四 M6 行同款纪律**在 git tag 之前入库**（进 tag 树），
> 分栏记录"tag 时点事实 / tag 后追加事实"；tag 之后只允许追加类提交（回写实测值 / run id 对账 / 补记）。
> 本文件只写**实测到**的事实；未执行项标 ⬜ 并说明原因，不预填、不留空。
>
> 上一版留档：`plan/RELEASE-M6.md`（v0.1.0，内容原样保留，本文件不改写它）。

---

## 一、发布基线（tag 时点事实）

| 项 | 值 |
| --- | --- |
| 版本 / tag | **`0.1.1` / `v0.1.1`**（annotated tag，待打） |
| 版本号出处 | `pyproject.toml:7` 与 `scripts/chartaudit/__init__.py:7` **两处同值** `0.1.1`；发布门 `VERSION` 项守门（相等 + 不含 dev 段，两条判据可分别变红） |
| 上一版遗留缺陷 | v0.1.0 的包版本是 `0.1.0.dev0`（PEP 440 排在 `0.1.0` **之前**），而 tag / Release / README 都写 v0.1.0；本版把版本口径转正 |
| 目标仓库 | `yuluo554/10-18-truth-chart-skill`（GitHub 公开） |
| 支持解释器 | **Python >= 3.12**（`requires-python` / classifiers / CI 矩阵三处同一口径） |
| 运行时依赖 | 零（`dependencies = []`，纯标准库） |
| 测试基线 | 干净 venv（3.12，`py -3.12 -m venv` + `pip install -e ".[dev]"`）**285 passed** |
| 基准基线 | `tools/bench.py` **29/29 达标**；`gen_synthetic --check` 通过；`check_whitelist` 通过；`selftest` 通过 |
| sdist 形态 | 新增 `MANIFEST.in`：sdist 收 `data/` `references/` `tools/` `plan/` `tests/` `scripts/`，**在解包树里真跑 pytest 285 passed** |

### 1.1 本版改动面（相对 v0.1.0 / HEAD `e80bfc6`）

| 面 | 改动 |
| --- | --- |
| 版本 | `pyproject.toml` + `scripts/chartaudit/__init__.py` 两处 → `0.1.1`（同提交） |
| 版本可见性 | `chartaudit --version` 新增（`argparse action="version"`，输出 `chartaudit 0.1.1`）；README 快速开始 + `SKILL.md` 调用示例各加一行 |
| 门 | `scripts/check_release.py` 新增 `VERSION` 项（两处相等 + 无 dev 段）；tag / 附件名改为**由 `__init__.py` 版本派生**（不再写第三份版本字面量）；CI 矩阵期望改为**现读 `ci.yml`**（不再硬编码 3.8/3.12） |
| 元数据 | SPDX `license = "MIT"` + `license-files = ["LICENSE"]`；`setuptools>=61` → `>=77`；补 4 条 `classifiers`（此前一个都没有） |
| floor | `requires-python` `>=3.8` → `>=3.12`；CI 矩阵 `{3.8, 3.12}` → `{3.12}`（ubuntu / windows 两腿） |
| actions | `actions/checkout@v4` → `@v7`、`actions/setup-python@v5` → `@v7` |
| 交接物 | `.gitignore` 增 `update/`（否则发布门 `CLEAN_TREE` 必红） |
| 打包 | 新增 `MANIFEST.in`（sdist 自足） |
| 测试 | 283 → **285**（新增 `--version` 与版本口径两条） |

### 1.2 附件清单（D15：Release 附产物，源码 zipball 不算产物）

| 附件 | 内容 | 大小 | sha256 |
| --- | --- | --- | --- |
| `chartaudit-v0.1.1-samples.zip` | 8 个样例文件：通过图 `clean_bar.html` + 阻断调试件 `g2_skewed.audit.html` + 各自 `provenance.json` / `audit.json` / `gates.json` | 10,066 字节 | `ddd3542b10b0643d2f1ecb2f1aaad3a875ac5ada95026bc4953abf66e4a4a71e` |

> 本地副本：`release/chartaudit-v0.1.1-samples.zip`（`release/` 已在 `.gitignore`，不入库；
> 同目录 `SHA256SUMS` 留档）。附件由 `data/samples/` 冻结产物按**固定文件序 + deflate** 打包，
> 与 v0.1.0 附件**逐字节相同**——因为本版没有改渲染与数据面（`gates.py` / `provenance.py` /
> `rules.py` / `render.py` 一行未动），样例产物本就应当一致；这是可复算的事实，不是复制粘贴。

### 1.3 发布执行计划（tag 时点写定）

1. 提交本文件 + 代码改动（**留档在 tag 之前入库**），push main。
2. CI 全绿后打 annotated tag `v0.1.1`（tag 指向含本留档的提交），push tag。
3. GitHub Release `v0.1.1`：**手工上传** `chartaudit-v0.1.1-samples.zip`（≥1 个附件，K31），
   说明里写附件 sha256。
4. `scripts/check_release.py --online` 终检：远端 tag 同源 / Release 资产 digest 与本地 sha256
   一致 / 附件回下载逐位一致 / CI 矩阵（现已收敛为 3.12 两腿）全绿。
5. run id 据实补记本文件 §二与 `plan/00` §五（tag 后追加类提交）。

---

## 二、tag 后追加事实（发布执行实测，tag 后回写）

> 本栏所有行均为 tag 推送之后追加；sha / run id / 时间以 `gh` 实测为准。

| 项 | 状态 | 实测值 |
| --- | --- | --- |
| 提交 + push main | ✅ | 提交 **`0c45f35`**（v0.1.1 发布改动，16 文件 +395/−40）→ `git push origin main`，2026-10-20T12:14:45Z |
| CI 新 run（3.12 两腿） | ✅ | run **`39420791262`**（push main / `0c45f359`）：`test (ubuntu-latest, 3.12)` 与 `test (windows-latest, 3.12)` 均 **success**；日志实测两腿各 **285 passed**；`selftest` 两通路均通过 |
| CI 注解 | ✅ 部分 | **Node.js 20 弃用 warning：0 条**（改前 4 条）；ubuntu 腿仍有 **1 条 notice**「`ubuntu-latest` 将于 2026-10-19 迁 Ubuntu 26」，但该腿日志实测 `Image: ubuntu-24.04 / Version 20261018.339.1` → **本次没有真正跑在 Ubuntu 26 上**，迁移首验仍未兑现（如实记录，不当作已验） |
| tag `v0.1.1` | ✅ | annotated tag，指向 `0c45f359b5befb097b89080ad542f870b48a32ce`（= main 提交）；`git cat-file -t` = `tag`；tagger 邮箱为 GitHub noreply；`git rev-list --count v0.1.1..HEAD` = 0 |
| push tag 的 CI | ✅ | run **`39421032588`**（`v0.1.1` / `0c45f359`）：两腿全 success；注解 0 条 Node20 弃用 + 1 条 ubuntu 迁移 notice（同上） |
| GitHub Release + 附件 | ✅ | `releases/tag/v0.1.1`（`draft=false`、`prerelease=false`，created 2026-10-20T12:16:24Z）；附件 `chartaudit-v0.1.1-samples.zip` 10,066 B；GitHub 资产 digest `sha256:ddd3542b…4a71e` |
| 附件四方同值 | ✅ | GitHub digest == `release/SHA256SUMS` 台账 == 本地 `release/` 副本 == `gh release download` 回下载重算，四方逐字符相同 |
| `check_release.py --online` | ✅ | **PASS 44 / WARN 1 / FAIL 0 / SKIP 0**，exit 0（唯一 WARN = `PUSH_RECON`：push 事件数 6 ≠ run 数 10，Events API 事件面缺口的既有形态，按 run 明细对账为准） |
| `check_release.py`（离线） | ✅ | 见 §2.2（tag 后实测汇总） |

### 2.1 CI run 明细（v0.1.1 窗口）

| run id | branch | head_sha | 事件 | 结论 |
| --- | --- | --- | --- | --- |
| `39420791262` | main | `0c45f359` | push（v0.1.1 发布改动） | ✅ 2/2 success（ubuntu-latest 3.12 / windows-latest 3.12） |
| `39421032588` | v0.1.1 | `0c45f359` | push tag | ✅ 2/2 success |

> 对账：本窗口共 2 次 `git push`（main ×1 / tag ×1），`ci.yml` push run 恰 2 个，
> branch + head_sha 逐条配对，**无失败 run**（`CI_HISTORY` PASS）。
> Events API 只返回 6 个 PushEvent（含 v0.1.0 窗口的残留），少于 10 个 push run，
> `PUSH_RECON` 因此给 WARN 而非 FAIL——与本仓既有处置口径一致（以 run 明细为准）。
>
> **镜像事实（重要，别当成已验）**：ubuntu 腿日志头实测
> `Operating System: Ubuntu 24.04.5 LTS` / `Image: ubuntu-24.04` / `Version 20261018.339.1`。
> 也就是说 2026-10-19 的 `ubuntu-latest → Ubuntu 26` 迁移在本次运行上**尚未生效**，
> 迁移后首验仍待下一次 run。windows 腿实测 `Microsoft Windows Server 2025 / 10.0.26100`。

---

## 三、工作树侧判定（tag 后离线门）

```
python scripts/check_release.py      # tag 已打、Release 已建、回写已提交
→ 见 §2.2 表格：离线与在线两模均 FAIL 0
```

> 与 v0.1.0 收官态（`PASS 27 / WARN 0 / FAIL 0`，在线 44/1/0/0）**条目数仍是同一套口径**；
> 检查项名字集合实测 **39 → 40**（只新增 `VERSION`，一个没删，`comm` 对比见
> `update/03-执行记录.md` §三）。判绿口径不变：**汇总行的 FAIL 数 = 0**。

---

## 四、口径与红线对照（K30–K33 自检）

| K 项 | 约定 | 本留档兑现 |
| --- | --- | --- |
| K30 | 留档在 tag 之前入库；tag 后只允许追加类提交；分栏 tag 时点 / tag 后 | 本文件随发布提交入库（计划进 tag 树）；§一为 tag 时点事实，§二为 tag 后追加栏 |
| K31 | Release 附件手工上传 ≥1 个 + 本地副本 sha256；源码 zipball 不算产物 | §1.2 附件清单 + sha256；本地副本 `release/`（gitignore，不入库） |
| K32 | 已发布版本的留档措辞不改写，只追加实测 | `plan/RELEASE-M6.md` 原样保留，本文件另起一版 |
| K33 | 全仓无本机绝对路径 / 用户名 / 邮箱 / 系列品牌词 | `check_release.py` 的 `TRACKED_LEAKS` / `HISTORY_LEAKS` 两条在守（实测 0 命中 + 阳性对照） |
