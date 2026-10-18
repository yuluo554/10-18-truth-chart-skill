# chartaudit — 图表诚信审计 Skill（开发中）

> **状态：开发中（M0 计划先行 ✅、M1 数据先行 + 解析层 ✅、M2 逐值溯源 ✅、M3 规则门禁 ✅、M4 窄缝门禁 ✅；M5–M6 未开工）。本 README 只声称下述已实现能力。**

CSV → 单文件 HTML 图表 + 机器可读诚信审计报告：逐值溯源到源 CSV 单元格、聚合可独立重算、样本量不足时禁止画均值柱、误差棒类型必须与数据列一致；存在 ERROR 时阻断发布。

三条窄缝（本题唯一押注；通用反误导检查为对齐已有工作，非创新）：
1. **逐值溯源**：每个渲染数值可回溯源单元格 `(row_index, column, raw_cell, transform_chain)`；
2. **样本量门禁**：n 过小且分布偏斜/多峰时禁止画均值柱；
3. **误差棒来源真实性**：`sd`/`sem`/`ci`/`n` 声明必须能在数据列或重复测量中找到来源。

## M3 规则门禁：对齐已有工作，非创新

九条反误导规则（柱状非零基线 / 双 Y 轴 / 饼图扇区数与求和 / 3D / 面积·半径编码 / 平滑过冲 / 时间轴等距 / 对比度 / 规格合法性）与 `artgas1/tufte-skill`（0★，2026-10-05 实测）等已有实现高度重叠，属**对齐已有工作**，不作为本题创新点（能力对照见 `plan/01` §一/§七，检索基准日 2026-10-17）。该标注同时固化在规则包 `references/rules.json` 的 `alignment` 字段，并随 `audit.json` 原样输出。

规则包 `references/rules.json` 是 rule_id / 严重级别 / 证据路径 / 阈值的**唯一出处**：引擎源码零规则字面量（扫描门测试锁定）；规则包缺失 / 级别映射非法 → 退出码 3，绝不静默按"零规则"通过。规格合法性（R009）由解析层以退出码 2 拦截，规则层不二次改判。

## M4 窄缝门禁（差异化主线）

三条窄缝门禁（逐值溯源 / 样本量 / 误差棒真实性）在 `gates.json` 落地：

- **G1 溯源完备性**：直接复用 M2 `provenance.validate` 的判定与 gate_id（不写第二份判定、不改判）；任一渲染值缺记录 / `match=false` / 行列不存在 / `raw_cell` 不符 / 源哈希不符 → ERROR 阻断；
- **G2 样本量门禁**：组内 `n < N_MIN` 且偏斜或呈多峰（确定性公式：样本偏度 `g1 = m3/m2^(3/2)`、|g1| > 1 判偏斜；bins=6 等宽直方图局部极大判多峰——阈值与公式参数全部来自配置）→ ERROR；分布未判定（样本过小 / 全等值）→ WARN；合规替代（全量散点叠加或箱线图）→ INFO；
- **G3 误差棒来源真实性**：`sd`/`sem`/`ci`/`n` 四类声明按数据来源判定（列名匹配走 `references/aliases.json` 别名表，大小写规则一处定义）；标题自由文本声明无来源 → ERROR；未声明但存在可疑 SD/SEM 列 → INFO。

`references/gates.json` 是 gate_id / 级别 / 证据路径 / 阈值的**唯一出处**：引擎源码零门禁字面量（扫描门测试锁定）；门禁包或别名表缺失 / 非法 → 退出码 3。`verdict=blocked` 当且仅当存在 ERROR；最终 CLI 退出码取规则层与门禁层 ERROR 的**并集**（任一层 blocked → exit 1），层级间不互相改判。

## 计划

详见 `plan/00-README总览.md`（索引 / 决策记录 / 承诺台账）与 `plan/05-里程碑.md`（M1–M6 DoD）。

## 当前可用命令（M1 解析 + M2 溯源 + M3 规则门禁 + M4 窄缝门禁已接线）

```bash
pip install -e ".[dev]"
pytest -q                                              # 全量测试（含解析 / 溯源 / 规则 / 门禁回归、G1 注入、独立重算、零字面量扫描门）
chartaudit check <csv> <spec.json> --out <dir>         # 解析 → 溯源 → 规则审计 → 窄缝门禁；写出 dataset/diagnostics/normalized/provenance/audit/gates（exit 0/1/2/3）
chartaudit build <csv> <spec.json> --out <dir>         # 当前等价 check（渲染 M5 接线；任一层 ERROR 时 exit 1 且不渲染）
chartaudit selftest                                    # 内部不变量自检（exit 0）
py -X utf8 tools/bench.py                              # M2+M3+M4 独立基准：29 张真值图全量实跑 + 规则 / 门禁逐类覆盖（exit 0/1/2）
py -X utf8 tools/gen_synthetic.py --check              # 冻结数据两层守门
py -X utf8 tools/check_whitelist.py                    # 假业务主题白名单校验
```

溯源产物 `provenance.json`：每个渲染值恰一条记录，含 `rendered_value_id`（SHA-256 前 16 hex）、
`row_index` / `csv_line`、逐源单元格 `sources[]`、`transform_chain`、`rendered_label` /
`recomputed_value` / `match`。G1 四形态（缺记录 / `match=false` / 行列不存在 / 源哈希不符）为 ERROR。

规则审计产物 `audit.json`：命中按 `(severity, rule_id, evidence_path)` 排序，含逐条证据与
`alignment` 对齐标注；`verdict=blocked` 当且仅当存在 ERROR 级命中（当前九条均为 ERROR）。

窄缝门禁产物 `gates.json`：G1 小节只引用溯源验证的 verdict / gate_ids；G2 小节逐组记录
`n` / `g1` / `bin_counts` / `skewed` / `multimodal`；G3 小节记录误差棒逐组声明与来源判定。
命中按 `(severity, gate_id, evidence_path)` 排序；`verdict=blocked` 当且仅当存在 ERROR
（含 G1 溯源 ERROR，计入 ERROR 计数）。

## 退出码契约（定稿，随模块接线逐条激活）

| 码 | 语义 |
| --- | --- |
| 0 | 审计通过（无 ERROR）且产物写出 |
| 1 | 审计完成但存在 ERROR（阻断发布；默认不写可发布 HTML） |
| 2 | 用法 / 输入 / 规格错误 |
| 3 | 规则包或配置缺失 / 校验失败 |

数值口径唯一出处：`data/README.md` 第四节。
