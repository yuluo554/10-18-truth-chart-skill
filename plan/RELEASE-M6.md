# plan/RELEASE-M6.md — 发布留档（M6 三件套之三）

> 版本：v0.1.0。本文件按 plan/00 §四 M6 行约定**在 git tag 之前入库**（进 tag 树），
> 并分栏记录"tag 时点事实 / tag 后追加事实"；tag 之后只允许追加类提交
> （回写实测值 / run id 对账 / 补记）。
> 本文件只写**实测到**的事实；未执行项标 ⬜ 并说明原因，不预填、不留空。

---

## 一、发布基线（tag 时点事实）

| 项 | 值 |
| --- | --- |
| 版本 / tag | `v0.1.0`（annotated tag） |
| 发布基线提交 | M6 收尾提交（本文件 + 干净环境验证留档 + 脱敏留档 + 发布门禁脚本入库的提交；sha 见 git log，tag 后追加事实栏记录 tag 指向） |
| 目标仓库 | `yuluo554/10-18-truth-chart-skill`（GitHub 公开） |
| 双解释器 | Python 3.8.8-64 / 3.12.10（本机 `py -0p` 实测；CI 同两版本四矩阵） |
| 运行时依赖 | 零（`dependencies = []`，纯标准库；pytest 仅为 dev extra） |
| 测试基线 | 双解释器全量 pytest **283 项全绿**（开发机与干净 venv 四处收集数一致均为 283） |
| 基准基线 | `tools/bench.py` **29/29 达标**（M2 独立重算 + M3 规则 8/8+1 + M4 门禁 6/6 + M5 发布门 29/29 + 13 张双跑 sha256） |
| 冻结守门 | `gen_synthetic --check` 通过；`check_whitelist` 通过；`selftest` 通过 |

### 1.1 附件清单（D15：Release 附产物，源码 zipball 不算产物）

| 附件 | 内容 | 大小 | sha256 |
| --- | --- | --- | --- |
| `chartaudit-v0.1.0-samples.zip` | 8 个样例文件：通过图 `clean_bar.html` + 阻断调试件 `g2_skewed.audit.html` + 各自 `provenance.json` / `audit.json` / `gates.json` | 10,066 字节 | `ddd3542b10b0643d2f1ecb2f1aaad3a875ac5ada95026bc4953abf66e4a4a71e` |

> 本地副本：`release/chartaudit-v0.1.0-samples.zip`（已加 .gitignore 不入库；
> `release/SHA256SUMS` 同目录留档）。附件由 `data/samples/` 冻结产物打包
> （zip deflate，固定文件序），样例本身在仓库内可由同一命令重生成并逐字节复现
> （干净 clone 已实测 `cmp` 逐字节一致，见 `plan/verify/README.md` §二）。

### 1.2 发布前验证证据（tag 时点已实测）

- **干净环境验证**（`plan/verify/README.md`）：新目录 `git clone --no-local` + 全新
  venv 3.8 / 3.12 各一；README「当前可用命令」12 条逐条实跑，退出码全部符合
  「退出码契约」表；双解释器收集数 **283 = 283**（与开发机一致，防包漂移）；
  模块形态与裸 console script 两通路冒烟（含非仓库根 CWD）。
- **脱敏扫描**（`plan/M6-desensitize-scan.md`）：工作树 89 个入库文本文件 0 命中；
  全历史（重写后 10 rev）0 命中（阳性对照 chartaudit 命中 220 文件·rev，通道有效）；
  提交邮箱全部 GitHub noreply；垃圾文件 0。
- **历史重写（如实留档）**：发布前脱敏扫描发现 `plan/HANDOFF-M1~M6.md` 含本机
  盘符路径 / 工作区路径标记（24 处文件·rev），已用 `git filter-repo --replace-text`
  重写全历史清零（重写前仓外备份 bundle 221,853 字节）。重写后旧短 sha 失效，
  活文档引用已核对（`git log` 10 提交无悬挂）。
- **发布终态自检**：`scripts/check_release.py --pre-tag` 通过（工作树干净 /
  脱敏 0 命中 / 邮箱 noreply / 垃圾 0；tag 相关项 SKIP）。
- 3.8 干净 venv 首次安装曾因**本机代理环境变量**失败（pip build isolation
  `ProxyError`），绕过代理后通过——属本机网络环境问题非包缺陷，已在
  `plan/verify/README.md` §一留档。

### 1.3 发布执行计划（tag 时点写定）

1. 建公开仓库 `yuluo554/10-18-truth-chart-skill`，push main → CI 首推（四矩阵）。
2. CI 全绿后打 annotated tag `v0.1.0`（tag 指向含本留档的收尾提交），push tag。
3. GitHub Release `v0.1.0`：**手工上传** `chartaudit-v0.1.0-samples.zip`（≥1 个附件，
   K31），标题与说明据实写（不编造）。
4. `scripts/check_release.py --online` 终检：远端 tag 同源 / Release 资产 digest 与
   本地 sha256 一致 / 附件回下载逐位一致 / CI 矩阵全绿 / push 事件数 = run 数。
5. run id 据实补记 plan/00 §五与本文 §二（tag 后追加类提交）。

---

## 二、tag 后追加事实（发布执行实测，tag 后回写）

> 本栏所有行均为 tag 推送之后追加；sha / run id / 时间以 `gh` 实测为准。
> 追加提交按 K30 只做回写/补记/对账。

| 项 | 状态 | 实测值 |
| --- | --- | --- |
| 仓库建立 + 首推 | ✅ | `https://github.com/yuluo554/10-18-truth-chart-skill`（公开）；首推 push main，head `1d3cee0`（12 提交全量），2026-10-18T10:37Z |
| CI 首推四矩阵 | ✅ | run `39119973977`（push main / `1d3cee0`）：ubuntu×3.8 / ubuntu×3.12 / windows×3.8 / windows×3.12 四 job 全部 success，1m15s |
| push ↔ run 对账 | ✅（Events API 缺口如实留档） | 发布窗口共执行 2 次 `git push`（main 首推、tag v0.1.0），`ci.yml` push run 恰 2 个（`39119973977` main / `39120145040` v0.1.0），head_sha 均为 `1d3cee03…` 逐条配对，无多余 run。GitHub Events API 该窗口仅返回 ReleaseEvent、0 个 PushEvent（事件面延迟/丢弃，实测两次重试仍 0）——故对账以 push 操作流水 ↔ run 明细（branch + head_sha + event）为准，2 = 2 |
| tag `v0.1.0` | ✅ | annotated tag，指向 `1d3cee03f0350c912a8d4c0587c80ecd0a69343c`（= main 收尾提交，含本留档）；tagger 邮箱 noreply；push 后 run `39120145040` 四矩阵全绿 |
| GitHub Release + 附件 | ✅ | `releases/tag/v0.1.0`（draft=false，prerelease=false）；手工上传附件 `chartaudit-v0.1.0-samples.zip`：GitHub 资产 digest `sha256:ddd3542b…` 与 §1.1 台账一致、大小 10,066 字节一致；附件回下载 sha256 与本地副本逐位一致 |
| `check_release.py --online` | ✅ | 终检 **PASS 43 / WARN 0 / FAIL 0 / SKIP 1**（唯一 SKIP = PUSH_RECON：Events API 0 个 PushEvent，已按上表口径以 run 明细完成对账）；离线模同样全绿 |
| run id 补记 plan/00 §五 | ✅ | 已补记（见 plan/00 §五"CI 首推实测记录"表） |
| 收尾追加提交 | ✅ | tag 后共 4 个追加类提交（§二/§2.1/§2.2 回写与发布门禁自身修正），各自 main run `39121268053` / `39121434804` / `39121632358` / `39121855807` 四矩阵全绿；tag 后改动面仅 plan/ 文档 + README + 发布门禁脚本（无产品/构建面改动） |

### 2.1 CI run 明细（发布窗口，ci.yml 全部 push run）

| run id | branch | head_sha | 事件 | 四矩阵结论 |
| --- | --- | --- | --- | --- |
| `39119973977` | main | `1d3cee03` | push（首推，12 提交全量） | ✅ 4/4 success（1m15s） |
| `39120145040` | v0.1.0 | `1d3cee03` | push tag | ✅ 4/4 success |
| `39121268053` | main | `4ca566ca` | push（§二回写追加） | ✅ 4/4 success |
| `39121434804` | main | `b7af5e5e` | push（门禁脚本中文文件名修正） | ✅ 4/4 success |
| `39121632358` | main | `5afd7e1e` | push（§2.1/§2.2 终记追加） | ✅ 4/4 success |
| `39121855807` | main | `493430e0` | push（通道备注措辞去邮箱形态） | ✅ 4/4 success |

> 对账：发布窗口共 6 次 `git push`（main ×5 / tag ×1），`ci.yml` push run 恰 6 个，
> branch + head_sha 逐条配对，**无失败 run**（`CI_HISTORY` PASS）；无 pull_request /
> workflow_dispatch run。首推零诊断轮（四个矩阵一次全绿，未出现兄弟项目实录过的
> "首跑 ubuntu 红"类缺陷）。tag 后 4 个提交均为追加类（§二回写 / 发布门禁自身修正 /
> 终记），`POST_TAG_FILES` 判定：改动面仅 plan/ 文档 + README + 发布门禁脚本，无产品/构建面改动。
>
> **传输通道备注（如实留档）**：追加提交 push 期间本机对 github.com 443 直连间歇不可达
> （api.github.com 正常），改走 GitHub SSH-over-443 通道完成推送；不影响远端
> 内容与 CI 结论。

### 2.2 终检快照（收官态）

- `scripts/check_release.py`（离线）：**PASS 27 / WARN 0 / FAIL 0 / SKIP 0**
- `scripts/check_release.py --online`：**PASS 44 / WARN 0 / FAIL 0 / SKIP 0**（终版）
  —— 中间轮次唯一 SKIP/WARN = PUSH_RECON：GitHub Events API 该窗口仅返回
  ReleaseEvent（后段延迟出现 1 个 PushEvent，远少于实际 6 次 push，事件面
  延迟/丢弃多次实测），对账已按 §2.1 push 流水 ↔ run 明细口径完成 **6 = 6**；
  终版 Events API 返回的 PushEvent 计数与 run 数一致，WARN 消除。
- 收官态再验：全新 clone（`--no-local`）→ pytest **283 passed**；`build` exit 0 且
  `clean_bar.html` 与 `data/samples/` **逐字节一致**（`cmp`）。

---

## 三、口径与红线对照（K30–K33 自检）

| K 项 | 约定 | 本留档兑现 |
| --- | --- | --- |
| K30 | 留档在 tag 之前入库；tag 后只允许追加类提交；分栏 tag 时点 / tag 后 | 本文件随 M6 收尾提交入库（在 tag 树内）；§一为 tag 时点事实，§二为 tag 后追加栏 |
| K31 | Release 附件手工上传 ≥1 个 + 本地副本 sha256；源码 zipball 不算产物 | §1.1 附件清单 + sha256；本地副本 `release/`（gitignore，不入库） |
| K32 | CI 首推后"本地等价校验"历史措辞不改写，只追加 run id 实测 | plan/00 §五新增"CI 首推实测记录"小节，M1–M5 历史行未动 |
| K33 | 全仓无本机绝对路径 / 用户名 / 邮箱 / 系列品牌词 | `plan/M6-desensitize-scan.md` 三面终扫 0 命中 + 阳性对照 |
