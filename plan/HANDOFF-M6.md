# HANDOFF-M6（M5 → M6 交接快照）

> 写于 2026-10-18，M5 收尾提交之后。续接提示词：
> `/goal 读取 "plan/HANDOFF-M6.md" 继续完成任务`

## 1. 当前进度 + 证据

- **M5 完成**（2026-10-18，本地等价校验——未接远端，CI 待首推验证）：
  - `references/geometry.json` 首次落地：45 键几何常量唯一出处（画布 / 边距 / 五图型图元尺寸 / 字号 / 刻度数 / 调色板 / `coord_decimals` 坐标精度 / CSS 间距 / `hover_opacity` / `z_index_tip` / `line_height_tip` / `font_weight_bold`）；缺件 / 未知键 / 颜色非法 / 边距越界 / `pie_full_angle ≠ 2×pie_half_turn` → `GeometryConfigError` → CLI exit 3 零写入（配置先行加载，与规则包 / 门禁包 / 别名表同批，见 D31）。
  - `chartaudit/render.py`：五图型单文件 HTML（bar 多系列并排柱 / line / scatter 同类目堆叠 / box 五数概括+逐观测散点 / pie 扇区 path）；内联 SVG+CSS+JS 零 CDN；hover 溯源提示（"此值 X 来自第 N 行「Y」列" + `raw_cell` + 变换链摘要 + 逐源单元格展开 + `rendered_value_id`；box 摘要单独载荷）；审计区块三层并集（溯源/规则/门禁，按级别序+id+路径+消息排序）+ 阻断横幅；坐标 Fraction 精确算术，饼图三角函数固定 3 位小数、`-0` 归一。
  - K25 扫描门：`render.py` tokenize 后 NUMBER 白名单 {0,1,2,3,4,5,10}（控制流小整数；浮点字面量一律禁）；变异实测：`("r", 7)` 与 `str(7)` 形式均红。
  - K26 确定性：pytest 参数化五图型双跑字节一致 + 非确定性模式扫描（时间戳/Date/random/绝对路径）；bench 13 张 pass 图双跑 sha256 断言；无时间戳 / 随机 / 进程 ID / locale。
  - K27 发布门（`cli._publish_gate`）：pass → `dist/<name>.html` exit 0；blocked → 默认零可发布 HTML exit 1；`--emit-audit-html` → `dist/<name>.audit.html`（横幅 + "审计调试件，不可作为发布产物"声明）exit 恒 1；`check` 永不写 HTML；`<name>` = spec_id 归一 `[^A-Za-z0-9._-]`→`_`。变异实测：`if True` 破坏 → pytest 2 红 + bench 11 图红。
  - K28 契约块：`SKILL.md` `<!-- chartaudit-contract -->` 三键（exit_codes / html_sections / html_provenance_fields）↔ `render.HTML_PROVENANCE_FIELDS`（13 字段定序）/ `HTML_SECTIONS` 常量 ↔ 实际渲染输出，集合相等 + 顺序相等，`test_skill_contract_block_triple_agreement` 锁定。
  - K29：hover 载荷只消费 provenance 记录（`csv_line` 取记录字段 = row_index+2 不重算）；bench 对每张 pass 图做 hover 载荷 ↔ provenance.json 逐键对照。
  - bench M5 扩展：29 图 build 全链——pass 13 张（产物 + 零 CDN + 载荷对照 + 双跑 sha256 + **注入式证伪逐张执行**：篡改 rendered_label → validate 必 blocked）；blocked 11 张（默认零 HTML + 调试件横幅 + exit 1）；`rule_invalid_mark` exit 2 零写入；G1 注入 4 图按"正常 build 出图 + 注入复算阻断"断言（D31⑥：注入桩与交付态发布门互不干扰）。
  - 样例产物 `data/samples/`：`clean_bar.html`（通过图）+ `g2_skewed.audit.html`（阻断调试件）+ 各自 provenance/audit/gates 三份 JSON + 台账 README；重跑 cmp 逐字节一致实测。
  - README（状态行 / M5 章节 / 命令表 / 退出码表全激活措辞）、`selftest`（+几何包键集合不变量）、`tests/test_cli_skeleton.py`（双跑断言扩展 dist/ HTML 递归对照）同步回写。
  - **双解释器全量 pytest：3.8 与 3.12 各 283 项全绿；bench 29/29（M2 独立重算 + M3 规则 8/8+1 + M4 门禁 6/6 + M5 发布门 29/29 + 13 张哈希）；`gen_synthetic --check` 冻结守门复跑通过；`check_whitelist` 通过；`selftest` 通过。**
- 提交链：`1ffab92` → … → `58d4969`（M4 收尾）→ M5 收尾提交（见 git log）。

## 2. 下一棒待办（M6 发布——三件套 + 终态自检）

按 plan/05 M6 DoD 与 plan/00 §四 M6 行逐项执行：
1. 干净环境验证：新 clone + 新 venv，README 命令逐条一次跑通；`pip install -e ".[dev]"` 在 3.8 与 3.12 各收集一次，**同一 extras 集合收集数一致**（防包漂移）；`python -m chartaudit.cli` 与裸 `chartaudit` 两通路冒烟。
2. 脱敏检查：全仓扫描本机路径（盘符绝对路径 / 用户目录）/ 用户名 / 邮箱 / 系列品牌词（见 data/README §五 品牌隔离）；`out/` 已在 .gitignore 则确认未入库；扫描留档。
3. 发布三件套：① `plan/RELEASE-M6.md` 发布留档**在 tag 之前入库**（分栏"tag 时点事实 / tag 后追加事实"）② git tag ③ GitHub Release **手工上传附件**（≥1 个：建议 `data/samples/clean_bar.html` + `g2_skewed.audit.html` 打 zip）+ 本地副本 sha256 留档。
4. CI 首推：`.github/workflows/ci.yml` 四矩阵（ubuntu/windows × 3.8/3.12）首推全绿；push 事件数 = run 数对账；**据实补记 run id 到 plan/00 §五**（历史"本地等价校验"措辞不改写，只追加）。
5. `scripts/check_release.py` 发布终态自检（离线 + `--online` 两模；离线模式查 tag/留档/附件本地副本哈希/README 状态行，online 模查 Release 资产与 run）。
6. README 状态行转正（去"开发中"或按题面措辞收尾）；仓库 topics / 缓议项（plan/06 §四 Q1/Q2 用户未表态项）清零或留档说明。
7. 收尾：DoD 验证 → plan/00·05·06 回写 → commit（tag 后只允许追加类提交）。

## 3. 既定口径清单（K 项，续接 HANDOFF-M1/M2/M3/M4/M5）

- K1–K24 沿用（HANDOFF-M1–M4 §3）；K25–K29 见 HANDOFF-M5 §3。M6 新增/强调：
- **K30** 发布留档 `plan/RELEASE-M6.md` 必须在 **tag 之前**入库；tag 之后只允许追加类提交（回写实测值 / run id 对账 / 补记），并在留档里分栏写"tag 时点事实 / tag 后追加事实"（plan/00 §四 M6 行既有约定）。
- **K31** Release 附件必须**手工上传**（≥1 个）且本地留副本 + sha256；源码 zipball 不算产物（D15）。
- **K32** CI 首推后"本地等价校验"措辞**不改写历史**，只在 plan/00 §五追加 run id 实测记录（plan/05 硬约束）。
- **K33** 脱敏红线：全仓不得出现本机绝对路径 / 用户名 / 邮箱 / 本系列其他项目名（品牌隔离 D13）；发现即清零后重新扫描留档。

## 4. 本机环境坑（新增 + 沿用）

- 沿用 HANDOFF-M1 §4 / M2 §4 / M3 §4 / M4 §4 / M5 §4 全部条目（`py -X utf8` + `PYTHONDONTWRITEBYTECODE=1` + `PYTHONPATH=scripts`；3.8/3.12 双通道；serialize 只收 bytes/str；Git Bash 与 Python TEMP 不一致）。
- M5 实测新增：**仓库根残留 Windows 保留名文件（如 `nul`）会让 pytest 收集直接报错**（`AssertionError: ... is not a file`）——Git Bash `ls` 可见、`os.remove` 报 WinError 5，**`rm -f nul`（Git Bash 内建）可删**；若再现按此处理并检查是否误入库。
- M5 实测新增：`pytest tmp_path` 下 `os.listdir` 会把 `dist/` 子目录与 JSON 文件并列返回——双跑断言遍历产物时必须分支处理目录（`test_build_is_byte_identical_across_runs` 已按此实现，M6 勿改回纯文件遍历）。
- `tools/bench.py` 的 `check_chart` 五元组与 `check_m5_build` 三元组 `(ok, message, html_sha256)` 并存；M6 若扩展保持两函数签名不变。
- HTML 断言用字节级比较；渲染输出单点在 `render.render_html`（文本）+ `serialize.write_atomic`（写盘），M6 不得另开写盘路径。
- 变异探活纪律照旧：备份 → 篡改 → 实跑必红 → 恢复 → 恢复后全量复跑（M5 三项：几何字面量 int/str 两形式 + 发布门破坏，均已实测全红后恢复全绿）。

## 5. M6 DoD checklist（打勾前先跑）

- [ ] 干净环境验证：新 clone + 新 venv，README 逐条一次跑通；双解释器 extras 收集数一致
- [ ] 脱敏检查（本机路径 / 用户名 / 邮箱 / 系列品牌词全仓扫描）+ 留档
- [ ] `scripts/check_release.py`（离线 + --online 两模）通过
- [ ] `plan/RELEASE-M6.md` 在 tag 前入库（分栏结构）
- [ ] git tag + GitHub Release 附产物（手工上传附件 + 本地副本 sha256）
- [ ] CI 首推四矩阵全绿 + push 事件数 = run 数对账 + run id 据实补记 plan/00
- [ ] README 状态行转正；topics / 缓议项清零或留档
- [ ] plan/00·05·06 回写 + commit（tag 后仅追加类提交）

## 6. 关键命令速查（M5 收尾时实跑全绿）

```bash
cd "$(git rev-parse --show-toplevel)"
export PYTHONDONTWRITEBYTECODE=1
PYTHONPATH=scripts py -X utf8 -m pytest -q                    # 全量 283 项（3.8 换 py -3.8，同样 283 全绿）
PYTHONPATH=scripts py -X utf8 tools/bench.py                  # 29/29（含 M5 发布门 + 13 张双跑 sha256）
PYTHONPATH=scripts py -X utf8 -m chartaudit.cli build data/synthetic/synthetic_groups.csv data/synthetic/spec_clean_bar.json --out out/m6      # exit 0 + dist/clean_bar.html
PYTHONPATH=scripts py -X utf8 -m chartaudit.cli build data/synthetic/synthetic_groups.csv data/synthetic/spec_g2_skewed.json --out out/m6 --emit-audit-html   # exit 1 + dist/g2_skewed.audit.html
PYTHONPATH=scripts py -X utf8 -m chartaudit.cli selftest      # 含几何包不变量
PYTHONPATH=scripts py -X utf8 tools/gen_synthetic.py --check  # 冻结守门
PYTHONPATH=scripts py -X utf8 tools/check_whitelist.py        # 白名单校验
cmp data/samples/clean_bar.html <重跑产物>                    # 样例字节一致抽检
```
