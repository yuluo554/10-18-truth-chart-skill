# HANDOFF-M4（M3 → M4 交接快照）

> 写于 2026-10-18，M3 收尾提交之后。续接提示词：
> `/goal 读取 "plan/HANDOFF-M4.md" 继续完成任务`

## 1. 当前进度 + 证据

- **M3 完成**（2026-10-18，本地等价校验——未接远端，CI 待首推验证）：
  - `references/rules.json` 首次落地：九条规则的 `rule_id` / `severity` / `evidence_path` / `thresholds` / `title` / `message` 唯一出处，另含 `alignment`（对齐已有工作标注，验收硬条件 K14）、`severity_order`（ERROR/WARN/INFO 唯一枚举）、`block_on`。
  - `chartaudit/rules.py`：九条规则纯函数（`CHECKERS` 字典 + 每 checker 独立函数）；只读 M1 产物 + M2 provenance，不重算渲染值、不改 `match`、无网络/时钟/随机。
  - R003 双子检查：扇区数 > `max_sectors`（配置值 **4**）或 舍入百分比合计 ≠ 100（Fraction + ROUND_HALF_UP 复用 M2 函数）；`rule_pie`（5 扇区）由扇区数命中；`rule_radius` 连带命中 R003+R005 属既定事实（truth 是最小植入集，基准按 ⊆ 断言）。
  - 零字面量扫描门（K16）：`scripts/chartaudit/*.py` 全包禁 `R\d{3}_`；`rules.py` 禁引号包裹的级别字符串字面量。规则包缺件/级别非法/rule_id 或 check 重复/引用未知检查器/**未覆盖全部检查器** → `RulesConfigError` → CLI exit 3 零写入。
  - `audit.json`：按 `(severity, rule_id, evidence_path)` 排序（K17）；`verdict=blocked ⟺` 存在 `block_on` 级命中；携带 `alignment`；双跑逐字节一致（测试锁）。
  - CLI：规则包先行加载（缺件 → exit 3 零写入）；规则命中阻断 → exit 1 不渲染；通过 → 写 `audit.json` exit 0。`selftest` 增规则包不变量。
  - K13 按 **A 方案**落地（D28）：truth `expected_exit` 重定义为"解析层退出码"，最终退出码由 `expected_verdict` + 已接线层推导；`gen_synthetic --check` 复跑通过（冻结数据未动）。
  - `tools/bench.py` M3 扩展：29 图全跑 **29/29**；规则覆盖 **8/8 审计层 + 1 类解析层 exit 2**；G2/G3 期望为过渡态断言（exit 0 + 规则层零 ERROR）。
  - 变异探活四项全红后恢复：去排序（1 failed）/ 级别映射 ERROR→WARN（5 failed）/ 阈值 4→100（5 failed）/ 删规则（2 errors）。
  - **双解释器全量 pytest：3.8 与 3.12 各 202 项全绿。**
- 提交链：`1ffab92` → `c16c019` → `1b85985` → `f5692b8` → `a343cb8` → `b561f76` → M3 收尾提交（见 git log）。

## 2. 下一棒待办（M4 窄缝门禁——差异化主线，全项目押注所在）

按 plan/05 M4 DoD 与 plan/03 M4 详设逐项执行：
1. `references/aliases.json`：误差棒列名别名表（大小写规则一处定义）；`references/` 补 G2/G3 阈值（`N_MIN` 等运行时配置——目前只在 truth.json 与生成器常量里）。
2. `chartaudit/gates.py`：G1（复用 `provenance.validate` 的 gate_id/verdict，**不写第二份判定**）/ G2（口径 §7/§8 确定性公式：`g1 = m3/m2^(3/2)`、|g1|>1 偏斜、bins=6 等宽直方图局部极大判多峰；n<N_MIN 且偏斜或双峰 → ERROR；undetermined → WARN；合规替代散点叠加/箱线 → INFO）/ G3（sd/sem/ci/n 四声明按口径 §11；标题自由文本声明无来源 → ERROR；未声明但可疑列 → INFO）。
3. `gates.json` 写盘 + CLI 接线：`verdict=blocked ⟺ 有 ERROR` 锁进测试；阈值/公式/别名零代码字面量（沿用 K16 扫描门模式）。
4. **收紧 M3 过渡态**（K13-A 最终语义）：`tools/bench.py` 中 `deferred_layer` 分支与 `tests/test_rules_regression.py` 中过渡态断言改为阻断断言（g2_*/g3_* 共 9 张图 → exit 1）；truth 的 `expected_infos`（g2_scatter_alt / g2_box_alt 的 INFO）在 gates.json 断言中兑现。
5. truth 的 G2 `expected_stats`（n/g1/bin_counts/skewed/multimodal/n_below_min）逐值对上（生成期已算好，作独立复算对照）。
6. 收尾：DoD 验证 → plan/00·03·05·06 回写 → HANDOFF-M5 → commit。

## 3. 既定口径清单（K 项，续接 HANDOFF-M1/M2/M3）

- K1–K12 沿用（HANDOFF-M1 §3 / HANDOFF-M2 §3）；K13–K18 沿用（HANDOFF-M3 §3）。M4 新增/强调：
- **K19** G1 判定不重写：`provenance.validate` 是 G1 唯一判定（D26）；`gates.py` 只调用并在 gates.json 里引用其 gate_id / verdict，不得另写第二份逻辑或改判。
- **K20** G2/G3 的阈值与公式全部来自 `references/` 配置 + 口径 §7/§8/§11（`data/README.md` 是语义唯一出处）；代码零阈值字面量；`N_MIN=5` 运行时不得从 truth.json 读（truth 是期望不是配置）。
- **K21** 偏斜/多峰实现必须与生成器 `tools/gen_synthetic.py` 的 `skew_g1` / `bin_counts` / `is_multimodal` **语义一致**（同口径独立实现）；truth 的 `expected_stats` 是对照基准，不是被测实现的输出回填。
- **K22** M3 过渡态收紧是 M4 的验收项之一：收紧后 bench 仍须 29/29（g2/g3 图 exit 0→1），回归测试同步翻转；禁止"过渡态永久化"。
- **K23** gates 与 rules 的关系：两层各自出 JSON（audit.json / gates.json），最终 CLI 退出码取两层 ERROR 的并集（任一 blocked → exit 1）；层级间不得互相改判。
- **K24** 别名表 `references/aliases.json` 是 G3 列名匹配唯一出处；大小写规则一处定义；M3 的 R008 对比度是 spec 声明位检查，与 G3 无耦合，别混。

## 4. 本机环境坑（新增 + 沿用）

- 沿用 HANDOFF-M1 §4 / M2 §4 / M3 §4 全部条目（`py -X utf8` + `PYTHONDONTWRITEBYTECODE=1` + `PYTHONPATH=scripts`；3.8/3.12 双通道；serialize 只收 bytes/str；Git Bash `/tmp` 与 Python `TEMP` 不一致——**变异探活脚本里跨进程恢复备份要用 `os.environ["TEMP"]`，不要用 Git Bash 的 /tmp 路径**）。
- M3 实测：`provenance.validate` 会给记录临时加 `_index`（结束 pop）；`rules.audit` 不改输入（有测试锁），但 G2 若复用 `compile_records` 输出仍建议 `copy.deepcopy`。
- `references/rules.json` 被测试模块级加载（`RULES_CFG = rules.load_rules()`）：改规则包后跑 pytest 需新进程；变异探活务必 finally 恢复 + 恢复后全量复跑。
- 扫描门 `test_zero_rule_literal_scan_gate` 检查的是**引号包裹**的级别字面量；G2/G3 若在 gates.py 写级别，同样不得出现 `'ERROR'` / `"ERROR"` 字面量（级别一律来自配置）。
- 冻结目录 `data/synthetic/` 只读；G2/G3 阈值放 `references/`（新增文件），不要动 truth.json。

## 5. M4 DoD checklist（打勾前先跑）

- [ ] `references/aliases.json` + G2/G3 阈值配置落地；代码零阈值/别名/级别字面量（扫描门扩展）
- [ ] G1 复用 `provenance.validate`（无第二份判定）；G2 确定性公式与 truth `expected_stats` 逐值对上；G3 四声明正反例全绿
- [ ] `gates.json` 写盘；`verdict=blocked ⟺ 有 ERROR` 锁进测试；undetermined→WARN、合规替代→INFO
- [ ] M3 过渡态收紧：g2/g3 共 9 张图 exit 0→1，bench 仍 29/29
- [ ] CLI 最终退出码 = 两层 ERROR 并集（audit + gates 任一 blocked → exit 1）
- [ ] 变异探活（G2 阈值篡改 / G3 别名表篡改 / verdict 逻辑破坏均必红）
- [ ] 双解释器全量 pytest + bench + `gen_synthetic --check` 复跑
- [ ] plan/00·03·05·06 回写 + HANDOFF-M5 + commit

## 6. 关键命令速查（写时实跑过）

```bash
cd 仓库相对路径
export PYTHONDONTWRITEBYTECODE=1
PYTHONPATH=scripts py -X utf8 -m pytest -q                    # 全量（3.8 换 py -3.8）
PYTHONPATH=scripts py -X utf8 tools/bench.py                  # M2+M3 基准 29/29 + 覆盖 8/8+1
PYTHONPATH=scripts py -X utf8 -m chartaudit.cli check data/synthetic/synthetic_groups.csv data/synthetic/spec_rule_pie.json --out out/m3   # 规则命中 → exit 1
PYTHONPATH=scripts py -X utf8 -m chartaudit.cli check data/synthetic/synthetic_errorbars.tsv data/synthetic/spec_errorbar_sd.json --out out/m3ok  # exit 0 + audit.json
PYTHONPATH=scripts py -X utf8 tools/gen_synthetic.py --check  # 冻结守门
PYTHONPATH=scripts py -X utf8 tools/check_whitelist.py
```
