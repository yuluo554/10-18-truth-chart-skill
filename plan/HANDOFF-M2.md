# HANDOFF-M2（M1 → M2 交接快照）

> 写于 2026-10-18，M1 收尾提交之后。续接提示词：
> `/goal 读取 "plan/HANDOFF-M2.md" 继续完成任务`

## 1. 当前进度 + 证据

- **M1 完成**（2026-10-18，本地等价校验——未接远端，CI 待首推验证）：
  - 生成器 `tools/gen_synthetic.py`：splitmix64 自研 RNG、seed=20261018、禁 stdlib random/时钟/set 迭代序；双跑逐字节一致有测试锁死。
  - `data/synthetic/` 冻结 29 件：`synthetic_groups.csv`（21 行）、`synthetic_errorbars.tsv`（28 行，含缺失单元格 116 个）、25 个 `spec_*.json`、`truth.json`、`manifest.json`（登记全部产物 + 生成器 + data/README.md 三处 sha256）。覆盖矩阵：干净图、M3 九类、G1 四形态（M2 启用注入）、G2 偏斜/多峰/均匀/合规替代×2、G3 四声明正反例+标题 SEM 反例、溯源正例 5 条。
  - G2 可检出性下限生成期断言已实跑：乙组 g1≈1.154701 判偏斜、丙组 bins=[2,0,0,0,0,2] 判多峰、戊组均匀通过；实算值写入 truth.json，测试内另有独立复算。
  - 守门：`tools/gen_synthetic.py --check` 两层断言绿；`tools/check_whitelist.py` 绿；两者均有测试 + 变异探活（改冻结件必红）。
  - 解析层 `scripts/chartaudit/parse.py`：分隔符实测判定（歧义 exit 2）、UTF-8-only、类型推断四序（全列缺失→string，D23）、缺失/null 标记、整行重复与主键重复分报、spec 白名单字段 + 未知字段报错 + 归一化（默认值显式化）。`build`/`check` 已接线，产出 `dataset.json` / `diagnostics.json` / `chart_spec.normalized.json`。
  - 退出码：骨架期 exit 4 已四处退役（exitcodes 常量、CLI、测试、README），`test_exit_code_contract_constants` 用 `hasattr` 反向锁死防复活。
  - **双解释器全量 pytest：3.8 与 3.12 各 72 项全绿。**
- 提交链：`1ffab92` → `c16c019` → M1 收尾提交（见 git log）。

## 2. 下一棒待办（M2 逐值溯源）

按 plan/05 M2 DoD 逐项执行：
1. `chartaudit/provenance.py`：消费 M1 的 `chart_spec.normalized.json`，为每个渲染值产出一条溯源记录。
2. `rendered_value_id` = SHA-256 前 16 hex；输入字段序固定（spec_id, mark_id, series, category, row_index, column, transform_chain 规范串接，口径/plan-02 §六.4）。
3. 变换白名单复算：`identity/filter/group_sum/group_mean/group_median/group_count/ratio/sort/top_n/stack_offset`；`Fraction` 按字符串构造（K5），舍入 ROUND_HALF_UP 仅输出层；比较精确相等。
4. `provenance.json` 落盘（走 serialize 单点 K3）；不变量：每渲染值恰一条记录；重复 id → 冲突 ERROR；无溯源不渲染。
5. 真值启用：`truth.json` 中 5 条 `expected_provenance`（scatter_identity 的 `(row_index, column, raw_cell)`）接入基准；G1 四形态注入缺陷真值（`injection` 字段）在本棒实现并断言 blocked + 对应 gate_id。
6. 独立重算基准：期望值由基准脚本独立复算（判别 = "注释掉引擎，真值还能算出来吗"）；行号口径断言 `row_index`（JSON）/ `csv_line = row_index + 2`（提示）不混用。
7. 双跑逐字节一致测试；`build` 接线溯源层；HANDOFF-M3 + plan/00·05·06 回写 + commit。

## 3. 既定口径清单（K 项，续接 HANDOFF-M1，动了会打挂测试）

- K1–K10 全部沿用（见 `plan/HANDOFF-M1.md` §3），此处只列 M2 新增强调：
- **K7a** `rendered_value_id` 输入字段序：`spec_id, mark_id, series, category, row_index, column, transform_chain`，规范串接后 SHA-256 取前 16 hex；序列化细节一旦定稿即锁测试。
- **K11** truth.json 的 `expected_stats` 只对 G2 五例存在；`expected_exit=2` 的用例（rule_invalid_mark）解析层即报错，M2 不得改成审计层报错。
- **K12** G1 四形态真值带 `injection` 字段描述注入方式；注入发生在基准运行时（对正常产物做缺陷注入再断言 ERROR），不得改冻结产物。

## 4. 本机环境坑（新增 + 沿用）

- 沿用 HANDOFF-M1 §4 全部条目（`py -X utf8` + `PYTHONDONTWRITEBYTECODE=1` + `PYTHONPATH=scripts`；3.8/3.12 双通道；serialize 只收 bytes/str）。
- **Git Bash 下 `/tmp` 与 Python 的 `TEMP` 不一致**：bash `rm -rf /tmp/x` 删不到 Python 写的系统临时目录；跨工具清理用同一侧路径。CLI `--out` 指向已存在的**文件**时 `os.makedirs` 会 FileExistsError（exit 1 而非 2）——M2 若在 CLI 层遇到再决定是否归入 exit 2 语义。
- 生成器 `--write` 是唯一写盘入口；冻结后禁止手工编辑 `data/synthetic/`（改生成器 → `--write` 重生成 → manifest 自动更新）。
- spec 归一化把 `filter` 组信息保留在 `encoding.y.filter`；G2 真值复算走该字段定位组（测试已示范）。

## 5. M2 DoD checklist（打勾前先跑）

- [ ] `provenance.json`：每渲染值恰一条记录；重复 id 冲突报错；无溯源不渲染（ERROR）
- [ ] `rendered_value_id` 稳定哈希 + 字段序锁进测试
- [ ] 变换白名单外 → exit 2；Fraction 重算 match；舍入规则正确
- [ ] truth 5 条溯源正例全中（`(row_index, column, raw_cell)` 逐字符）
- [ ] G1 四形态注入基准：各断言 blocked + 对应 gate_id + exit 1
- [ ] 独立重算基准与引擎一致；csv_line=+2 口径断言
- [ ] 双跑逐字节一致测试
- [ ] 双解释器全量 pytest；plan/00·05·06 回写 + HANDOFF-M3 + commit

## 6. 关键命令速查（写时实跑过）

```bash
cd "$(git rev-parse --show-toplevel)"
export PYTHONDONTWRITEBYTECODE=1
PYTHONPATH=scripts py -X utf8 -m pytest -q                  # 全量（3.12 换 py -3.8）
PYTHONPATH=scripts py -X utf8 -m chartaudit.cli check data/synthetic/synthetic_groups.csv data/synthetic/spec_clean_bar.json --out <out>
PYTHONPATH=scripts py -X utf8 tools/gen_synthetic.py --check  # M1 冻结守门（M2 只读）
PYTHONPATH=scripts py -X utf8 tools/check_whitelist.py
```
