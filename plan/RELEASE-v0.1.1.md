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
| 提交 + push main | ⬜ | 待执行（需用户点头；本仓纪律：不自行 commit / push） |
| CI 新 run（3.12 两腿） | ⬜ | 待触发后补记 run id / 结论 / 注解条数（期望：0 条 Node20 弃用、0 条 ubuntu 迁移 notice） |
| tag `v0.1.1` | ⬜ | 待打（annotated，tagger 邮箱须为 GitHub noreply） |
| GitHub Release + 附件 | ⬜ | 待建（draft=false；附件 `chartaudit-v0.1.1-samples.zip`，sha256 见 §1.2） |
| `check_release.py --online` | ⬜ | 待跑；离线模已实测 **PASS 26 / WARN 3 / FAIL 0 / SKIP 0**（WARN 均为 tag 未打时的应有形态，见 §三） |

---

## 三、tag 前的离线门实测（tag 时点事实，便于复验对照）

```
python scripts/check_release.py            # tag 未打、工作树含本批改动
→ 汇总：PASS 26 / WARN 3 / FAIL 0 / SKIP 0，exit 0
  WARN = TAG_EXISTS 之前的历史口径差异：
    · README_STATUS   —— README 前 12 行还没有 v0.1.1 的"已发布"句
    · POST_TAG        —— tag v0.1.1 尚不存在，无法读 tag..HEAD
    · TAGGER_EMAIL    —— 同上
```

> 说明：这三条 WARN 是"tag 还没打"的必然形态；打了 tag 并回写 README 状态行后应全部转 PASS。
> `CLEAN_TREE` 在提交后回绿（当前工作树含待提交改动时必然 FAIL，这是判据本身）。

---

## 四、口径与红线对照（K30–K33 自检）

| K 项 | 约定 | 本留档兑现 |
| --- | --- | --- |
| K30 | 留档在 tag 之前入库；tag 后只允许追加类提交；分栏 tag 时点 / tag 后 | 本文件随发布提交入库（计划进 tag 树）；§一为 tag 时点事实，§二为 tag 后追加栏 |
| K31 | Release 附件手工上传 ≥1 个 + 本地副本 sha256；源码 zipball 不算产物 | §1.2 附件清单 + sha256；本地副本 `release/`（gitignore，不入库） |
| K32 | 已发布版本的留档措辞不改写，只追加实测 | `plan/RELEASE-M6.md` 原样保留，本文件另起一版 |
| K33 | 全仓无本机绝对路径 / 用户名 / 邮箱 / 系列品牌词 | `check_release.py` 的 `TRACKED_LEAKS` / `HISTORY_LEAKS` 两条在守（实测 0 命中 + 阳性对照） |
