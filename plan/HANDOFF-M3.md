# HANDOFF-M3（M2 → M3 交接快照）

> 写于 2026-10-18，M2 收尾提交之后。续接提示词：
> `/goal 读取 "plan/HANDOFF-M3.md" 继续完成任务`

## 1. 当前进度 + 证据

- **M2 完成**（2026-10-18，本地等价校验——未接远端，CI 待首推验证）：
  - `scripts/chartaudit/provenance.py`：Consume M1 `chart_spec.normalized.json`；每个渲染值恰一条记录。
  - `rendered_value_id`：固定字段序 `spec_id, mark_id, series, category, row_index, column, transform_chain`，规范串接 = `json.dumps(..., separators=(",",":"), sort_keys=True)`，SHA-256 前 16 hex；字段序与规范串已锁测试。
  - 变换白名单封闭（identity/filter/group_sum/group_mean/group_median/group_count/ratio/sort/top_n/stack_offset）；白名单外 → `ProvenanceError` / exit 2；`sort/top_n/stack_offset` 仅后处理（需参数），不能直接充当 `y.aggregate`。
  - 精确算术：`Fraction` 从 `raw_cell` 字符串构造；ROUND_HALF_UP 仅输出层；`1.005→1.01`、`-1.25→-1.3` 反 float 测试；聚合记录含 `sources[]`（全量源单元格）+ 代表行（最小 row_index）。
  - 不变式/G1：重复 id、缺失记录、多余记录、`match=false`、行列不存在、`raw_cell` 不符、源 SHA-256 不符 → ERROR；`verdict=blocked` / `exit_code=1` / `render_allowed=false`。
  - CLI：`build`/`check` 写出 `dataset.json` / `diagnostics.json` / `chart_spec.normalized.json` / `provenance.json`；溯源阻断返回 1 且不渲染（M5 接渲染器后由 `render_allowed` 强制）。
  - `tools/bench.py`：交付态入口对 29 张真值图全量实跑，**29/29 达标**；期望值由 benchmark 内独立复算（不调用引擎聚合/舍入）。
  - 双跑逐字节一致：全部 JSON 产物（含 provenance）。
  - 变异探活：舍入改截断、ID 字段换序、group_mean 改 sum，测试均必红。
  - **双解释器全量 pytest：3.8 与 3.12 各 133 项全绿。**
- 提交链：`1ffab92` → `c16c019` → M1 收尾提交 → M2 收尾提交（见 git log）。

## 2. 下一棒待办（M3 规则门禁，对齐已有工作）

按 plan/05 M3 DoD 与 plan/03 M3 逐项执行：
1. 建 `references/rules.json`：九条规则的 `rule_id` / 严重级别 / 证据字段唯一映射；`references/` 目录首次落地。
2. `chartaudit/rules.py`：九条规则纯函数实现；**代码零规则字面量**（rule_id/severity/阈值全部来自 `references/rules.json`；加扫描门测试）。
3. `audit.json`：按 `(severity, rule_id, evidence_path)` 稳定排序；字段序固定；走 `serialize.py` 单点写盘。
4. 九条规则全覆盖（题面 M3）：基线非零 / 双 Y 轴 / 饼图扇区与求和 / 3D / 面积半径编码 / 平滑过冲 / 时间轴等距 / 对比度 / 规格合法性。`rule_invalid_mark` 已由解析层 exit 2 拦截，规则层不得越权改判。
5. truth 九类各 ≥1 植入真值命中；`rule_*` 的 `expected_errors` 逐条对上；`audit.json` 排序稳定。
6. 级别语义：`ERROR/WARN/INFO` 唯一枚举；`verdict=blocked ⟺ 有 ERROR`；M3 阶段先让 `audit` 输出参与 CLI 退出码（见 K13）。
7. README/审计报告保留 **"对齐已有工作"** 标注（验收硬条件）。
8. 收尾：DoD 验证 → plan/00·03·05·06 回写 → HANDOFF-M4 → commit。

## 3. 既定口径清单（K 项，续接 HANDOFF-M1/M2）

- K1–K10 沿用（`plan/HANDOFF-M1.md` §3）；K11–K12 沿用（`plan/HANDOFF-M2.md` §3）。M3 新增/强调：
- **K13（M3 开工前必须清零）** truth.json 的 `expected_exit` 对 M3/M4 的 blocked 图当前仍是 `0`（M1 生成时只有解析层，按无审计层设定）；而最终语义是 `blocked → exit 1`（data/README §15 / D10）。M3 必须二选一并留档：
  - **A（建议）**：把 `expected_exit` 重定义为"输入/解析层退出码"，基准用 `expected_verdict` 推导最终退出码；不改冻结数据。
  - **B**：改生成器 → `contract_version` 升档 → 整目录重生成 + manifest 更新 + 全量断言重跑。
  - 禁止"truth 一套、基准一套"各写各的。
- **K14** M3 的九条规则属**对齐已有工作，非创新**；README、审计报告、提交说明一律保留标注。`artgas1/tufte-skill` 与 `honest-chart` 的能力清单是硬对照。
- **K15** `rule_invalid_mark` 的期望是解析层 `exit 2`（K11）；R009 只能作为"规格合法性"的解析层证据被引用，不得在规则层二次报错或把 exit 2 改成 1。
- **K16** `references/rules.json` 是严重级别与 rule_id 的唯一出处；代码、测试、文档只引用。加"零字面量"扫描门（源码中不得出现 `R00x_...` 与 `ERROR/WARN/INFO` 规则映射）。
- **K17** `audit.json` 的顺序是契约：`(severity, rule_id, evidence_path)`；同级同 id 时按 evidence_path 字符串序，禁止依赖 dict/set 迭代序。
- **K18** 规则层只读 M1 产物 + M2 provenance；不得重算渲染值、不得改 `match`、不得读网络/时钟/随机。

## 4. 本机环境坑（新增 + 沿用）

- 沿用 HANDOFF-M1 §4 / HANDOFF-M2 §4 全部条目（`py -X utf8` + `PYTHONDONTWRITEBYTECODE=1` + `PYTHONPATH=scripts`；3.8/3.12 双通道；serialize 只收 bytes/str；Git Bash `/tmp` 与 Python `TEMP` 不一致）。
- **M2 实测**：`provenance.validate` 会在记录上临时加 `_index`（结束后 pop）；M3 若复制记录做审计，先 `copy.deepcopy`，不要共享引用。
- `tools/bench.py` 用 `contextlib.redirect_stdout/stderr` 包住 `cli.main`，临时目录用 `tempfile.mkdtemp` + `shutil.rmtree`；M3 扩展全链时沿用。
- 记录 JSON 的键序被 `serialize.dumps_json(sort_keys=True)` 统一为字母序；`rendered_value_id` 的规范串也 `sort_keys=True`，两处不要混为"字段序"。
- 冻结目录 `data/synthetic/` 仍只读；M3 若按 K13-B 改 truth，必须走生成器 `--write` 重生成整目录，禁止手改。
- `out/`、`dist/` 已在 `.gitignore`；基准/冒烟临时产物不要入库。

## 5. M3 DoD checklist（打勾前先跑）

- [ ] `references/rules.json` 唯一映射；代码零规则字面量（扫描门）
- [ ] 九条规则实现；每类 ≥1 植入真值命中
- [ ] `audit.json` 排序稳定 `(severity, rule_id, evidence_path)`；双跑逐字节一致
- [ ] `rule_invalid_mark` 仍 exit 2（解析层），规则层不二次改判
- [ ] `verdict=blocked ⟺ 有 ERROR` 锁进测试；CLI 退出码按 K13 方案落地
- [ ] `tools/bench.py` 覆盖 M3：29 图全跑，规则类期望命中（检出率/逐类覆盖）
- [ ] README/审计报告保留"对齐已有工作"标注
- [ ] 双解释器全量 pytest；变异探活（删一条规则/改级别映射/打乱排序均必红）
- [ ] plan/00·03·05·06 回写 + HANDOFF-M4 + commit

## 6. 关键命令速查（写时实跑过）

```bash
cd "$(git rev-parse --show-toplevel)"
export PYTHONDONTWRITEBYTECODE=1
PYTHONPATH=scripts py -X utf8 -m pytest -q                  # 全量（3.12 换 py -3.8）
PYTHONPATH=scripts py -X utf8 -m chartaudit.cli check data/synthetic/synthetic_groups.csv data/synthetic/spec_clean_bar.json --out out/m2
PYTHONPATH=scripts py -X utf8 tools/bench.py                # M2 基准 29/29
PYTHONPATH=scripts py -X utf8 tools/gen_synthetic.py --check  # 冻结守门（M2/M3 只读）
PYTHONPATH=scripts py -X utf8 tools/check_whitelist.py
```
