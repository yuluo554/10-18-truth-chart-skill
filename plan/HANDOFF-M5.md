# HANDOFF-M5（M4 → M5 交接快照）

> 写于 2026-10-18，M4 收尾提交之后。续接提示词：
> `/goal 读取 "plan/HANDOFF-M5.md" 继续完成任务`

## 1. 当前进度 + 证据

- **M4 完成**（2026-10-18，本地等价校验——未接远端，CI 待首推验证）：
  - `references/gates.json` 首次落地：12 条门禁的 `gate_id` / `severity`（G2 为 violation/undetermined/alternative 三态映射）/ `evidence_path` / `thresholds` / `title` / `message` 唯一出处；**severity 枚举复用规则包** `references/rules.json` 的 `severity_order` / `block_on`（K20，不另立第二份枚举）。阈值：`n_min=5`、`skew_abs_threshold=1.0`、`skew_min_n=3`、`multimodal_bins=6`、`multimodal_min_n=4`、`multimodal_min_count_floor=2`、`multimodal_min_count_divisor=6`、`sem_tolerance_abs=1e-12`（字符串十进制）。
  - `references/aliases.json` 首次落地：误差棒列名别名表（sd/sem/ci/n 四类型 + title 别名），`case_sensitive=false` + `match_mode=suffix`（K24 大小写规则一处定义）。
  - `chartaudit/gates.py`：
    - G1 只调用 `provenance.validate`（K19/D26）：`gates.json` 的 `g1` 小节引用其 verdict / gate_ids / error_count 并计入 ERROR 计数；findings 不重复登记 G1 判定；
    - G2 独立实现口径 §7/§8 公式（`skew_g1` / `bin_counts` / `is_multimodal`，Fraction 精确算术；与生成器语义一致但实现独立，K21）；`n<N_MIN` 且偏斜或多峰 → ERROR；undetermined → WARN；合规替代（overlay_scatter / box / scatter）→ INFO；分组统计逐值写入 `g2.groups[]`，与 truth `expected_stats` 在 bench 逐键对照；
    - G3 四声明按口径 §11：sd（配对 SD 列）/ sem（SEM 列或 SD 列按 `sd/√n` 重算，超容差 → `G3_SEM_MISMATCH`）/ ci（上下限两列同时命中，单列声明 → `G3_CI_INCOMPLETE`）/ n（声明值 = 实际分组计数）；标题自由文本声明无来源 → ERROR；未声明但有可疑 SD/SEM 列 → INFO。
  - 门禁包校验（缺件 / 级别非法 / gate_id 或 check 重复 / 未知检查器 / 未覆盖全部检查器 / thresholds 缺键）→ `GatesConfigError` → CLI exit 3 零写入；别名表校验同语义。
  - `gates.json`：findings 按（级别序, gate_id, evidence_path, category）排序；`verdict=blocked ⟺` 有 ERROR（含 G1 计入）；双跑逐字节一致（测试锁）；`gates.audit` 不改输入（有测试锁）。
  - CLI：配置（规则包 + 门禁包 + 别名表）先行加载 → 缺件 exit 3 零写入；`check`/`build` 写出 `audit.json` + `gates.json`；**最终退出码 = 溯源 / 规则 / 门禁三层 ERROR 并集（K23：任一 blocked → exit 1）**；`selftest` 增门禁包 / 别名表不变量。
  - K22 过渡态收紧兑现：`tools/bench.py` 删除 `deferred_layer` 分支，g2_*/g3_* 共 9 图阻断断言（exit 0→1）；g2_scatter_alt / g2_box_alt 的 INFO 在 gates.json 兑现；G2 `expected_stats` 逐值对照；M4 门禁覆盖 6/6 类输出；`tests/test_rules_regression.py` 同步翻转（门禁期望图断言规则层零越权）。
  - 扫描门扩展（K16）：gates.py / cli.py / rules.py 禁 `G[123]_[A-Z]` 与引号包裹级别字面量（provenance.py 的 G1 gate_id 是 M2 判定语义产出位，不在扫描范围，已留档说明）。
  - 变异探活三项实跑全红后恢复：G2 阈值篡改（`multimodal_min_count_floor→100`）6 红 / G3 别名篡改（SD 别名改无关名）6 红 / verdict 逻辑破坏（blocked 只看 g1）13 红。
  - **双解释器全量 pytest：3.8 与 3.12 各 243 项全绿；bench 29/29；`gen_synthetic --check` 冻结守门复跑通过；`check_whitelist` 通过；`selftest` 通过。**
- 提交链：`1ffab92` → … → `26eed2a`（M3 收尾）→ M4 收尾提交（见 git log）。

## 2. 下一棒待办（M5 渲染与 Skill——全链交付面）

按 plan/05 M5 DoD 与 plan/03 M5 详设逐项执行：
1. `references/geometry.json`：画布宽高 / 边距 / 柱宽 / 字号 / 刻度数等几何常量唯一出处（口径 §16）；M5 渲染层零几何字面量（扫描门模式沿用 K16）。
2. `chartaudit/render.py`：单文件 HTML（内联 SVG + 少量内联 JS，零 CDN）；bar/line/scatter/box/pie 五图型；固定布局，禁自适应 / 随机抖动；两次渲染字节一致（测试锁）。
3. hover 溯源提示："此值来自第 csv_line 行第 Y 列" + `raw_cell` + 变换链摘要（口径 §1）；审计区块（ERROR/WARN/INFO 列表与计数）；有 ERROR → 阻断横幅。
4. 发布门：`build` 无 ERROR → 写 `dist/<name>.html` exit 0；有 ERROR → 默认不写，仅 `--emit-audit-html` 时写 `dist/<name>.audit.html`，exit 仍 1（D10）。
5. `SKILL.md`：触发条件 / 工作流 / 调用示例 + 机器可解析契约块（输出字段集合、顺序、退出码语义），与代码常量做三方断言（声明 ↔ 常量 ↔ 实际输出）。
6. `tools/bench.py` M5 扩展为全链：`build` 入口实跑 29 图，HTML 产物哈希断言 + 静态零 CDN 扫描门；注入式证伪（改渲染值 → HTML 与 provenance 不符必须报红）。
7. 样例产物：一份通过图 + 一份阻断图（审计调试件）HTML + 三份审计 JSON 入 `data/samples/`（或仓库约定位置）。
8. README 补渲染 / 发布门 / 契约块；收尾：DoD 验证 → plan/00·02·03·05·06 回写 → HANDOFF-M6 → commit。

## 3. 既定口径清单（K 项，续接 HANDOFF-M1/M2/M3/M4）

- K1–K18 沿用（HANDOFF-M1/M2/M3 §3）；K19–K24 沿用（HANDOFF-M4 §3）。M5 新增/强调：
- **K25** 几何常量唯一出处 `references/geometry.json`；渲染层（及测试）只引用，零几何字面量；禁从浏览器尺寸 / 分辨率 / 随机数推导（口径 §16）。
- **K26** 确定性渲染：输出不得含时间戳 / 随机数 / 进程 ID / 绝对路径 / locale 格式；同一输入两次渲染字节级一致（口径 §17，测试锁）。
- **K27** 发布门硬语义：`render_allowed=false`（任一层 blocked）→ 默认零可发布 HTML，exit 1；`--emit-audit-html` 只是审计调试件（命名带 `.audit`），不得冒充可发布产物。
- **K28** 契约块三方断言：`SKILL.md` 机器可解析块 ∩ 代码常量 ∩ 实际输出字段 = 集合相等 + 顺序相等；任何一处漂移测试必红。
- **K29** hover 溯源提示的数据源只能是 `provenance.json` 记录（`csv_line = row_index + 2` 口径 §1）；不得在渲染时重算。

## 4. 本机环境坑（新增 + 沿用）

- 沿用 HANDOFF-M1 §4 / M2 §4 / M3 §4 / M4 §4 全部条目（`py -X utf8` + `PYTHONDONTWRITEBYTECODE=1` + `PYTHONPATH=scripts`；3.8/3.12 双通道；serialize 只收 bytes/str；Git Bash `/tmp` 与 Python `TEMP` 不一致——跨进程恢复备份用 `os.environ["TEMP"]`）。
- M4 实测：`references/rules.json` 与 `references/gates.json` 都被测试模块级加载；改任一配置后跑 pytest 需新进程；变异探活务必备份→篡改→finally 恢复→恢复后全量复跑（M4 用 `cp` 到 `%TEMP%` 再 copy 回，逐字节恢复已实测）。
- `tools/bench.py` 的 `check_chart` 现返回五元组 `(ok, message, hit_rule_ids, hit_gate_ids, seen_info_gate_ids)`；M5 扩展时沿用，勿改回三元组。
- 冻结目录 `data/synthetic/` 仍只读；M5 新增几何常量放 `references/geometry.json`（新文件），不要动 truth.json / rules.json / gates.json / aliases.json。
- HTML 断言用字节级比较（`serialize.dumps_json` 不适用于 HTML；M5 需为渲染输出确定单点写盘路径）。

## 5. M5 DoD checklist（打勾前先跑）

- [ ] `references/geometry.json` 落地；渲染层零几何字面量（扫描门）
- [ ] 单文件 HTML：内联 SVG/CSS/JS，零 CDN 静态扫描门（`<script src>` / `<link href>` / `url()` / `@import` / `http(s)://` 资源全禁）+ 注入式证伪
- [ ] 固定几何；两次渲染字节一致；hover 溯源提示；审计区块与阻断横幅
- [ ] 发布门：有 ERROR 默认无可发布 HTML exit 1；`--emit-audit-html` 调试件 exit 仍 1
- [ ] `SKILL.md` 契约块三方断言（声明 ↔ 代码常量 ↔ 实际输出字段序）
- [ ] 全链 `chartaudit build` 端到端基准全绿（bench M5 扩展，真值全量实跑 + 检出率 + 逐类覆盖）
- [ ] 样例产物：通过图 + 阻断图（审计调试件）HTML + 三份审计 JSON
- [ ] README（安装/命令/退出码表/对齐标注/诚实边界）；双解释器全量 pytest + bench + `gen_synthetic --check`
- [ ] plan/00·02·03·05·06 回写 + HANDOFF-M6 + commit

## 6. 关键命令速查（写时实跑过）

```bash
cd 仓库相对路径
export PYTHONDONTWRITEBYTECODE=1
PYTHONPATH=scripts py -X utf8 -m pytest -q                    # 全量 243 项（3.8 换 py -3.8）
PYTHONPATH=scripts py -X utf8 tools/bench.py                  # M2+M3+M4 基准 29/29 + 覆盖 8/8+1 与 6/6
PYTHONPATH=scripts py -X utf8 -m chartaudit.cli check data/synthetic/synthetic_groups.csv data/synthetic/spec_g2_skewed.json --out out/m4   # 门禁命中 → exit 1 + gates.json
PYTHONPATH=scripts py -X utf8 -m chartaudit.cli check data/synthetic/synthetic_groups.csv data/synthetic/spec_clean_bar.json --out out/m4ok  # exit 0 + audit.json + gates.json
PYTHONPATH=scripts py -X utf8 -m chartaudit.cli selftest
PYTHONPATH=scripts py -X utf8 tools/gen_synthetic.py --check  # 冻结守门
PYTHONPATH=scripts py -X utf8 tools/check_whitelist.py
```
