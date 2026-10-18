# chartaudit — 图表诚信审计 Skill（开发中）

> **状态：开发中（M0 计划先行 ✅、M1 数据先行 + 解析层 ✅、M2 逐值溯源 ✅、M3 规则门禁 ✅；M4–M5 未开工）。本 README 只声称下述已实现能力。**

CSV → 单文件 HTML 图表 + 机器可读诚信审计报告：逐值溯源到源 CSV 单元格、聚合可独立重算、样本量不足时禁止画均值柱、误差棒类型必须与数据列一致；存在 ERROR 时阻断发布。

三条窄缝（本题唯一押注；通用反误导检查为对齐已有工作，非创新）：
1. **逐值溯源**：每个渲染数值可回溯源单元格 `(row_index, column, raw_cell, transform_chain)`；
2. **样本量门禁**：n 过小且分布偏斜/多峰时禁止画均值柱；
3. **误差棒来源真实性**：`sd`/`sem`/`ci`/`n` 声明必须能在数据列或重复测量中找到来源。

## M3 规则门禁：对齐已有工作，非创新

九条反误导规则（柱状非零基线 / 双 Y 轴 / 饼图扇区数与求和 / 3D / 面积·半径编码 / 平滑过冲 / 时间轴等距 / 对比度 / 规格合法性）与 `artgas1/tufte-skill`（0★，2026-10-05 实测）等已有实现高度重叠，属**对齐已有工作**，不作为本题创新点（能力对照见 `plan/01` §一/§七，检索基准日 2026-10-17）。该标注同时固化在规则包 `references/rules.json` 的 `alignment` 字段，并随 `audit.json` 原样输出。

规则包 `references/rules.json` 是 rule_id / 严重级别 / 证据路径 / 阈值的**唯一出处**：引擎源码零规则字面量（扫描门测试锁定）；规则包缺失 / 级别映射非法 → 退出码 3，绝不静默按"零规则"通过。规格合法性（R009）由解析层以退出码 2 拦截，规则层不二次改判。

## 计划

详见 `plan/00-README总览.md`（索引 / 决策记录 / 承诺台账）与 `plan/05-里程碑.md`（M1–M6 DoD）。

## 当前可用命令（M1 解析 + M2 溯源 + M3 规则门禁已接线）

```bash
pip install -e ".[dev]"
pytest -q                                              # 全量测试（含解析 / 溯源 / 规则回归、G1 注入、独立重算、零字面量扫描门）
chartaudit check <csv> <spec.json> --out <dir>         # 解析 → 溯源 → 规则审计；写出 dataset/diagnostics/normalized/provenance/audit（exit 0/1/2/3）
chartaudit build <csv> <spec.json> --out <dir>         # 当前等价 check（渲染 M5 接线；溯源或规则 ERROR 时 exit 1 且不渲染）
chartaudit selftest                                    # 内部不变量自检（exit 0）
py -X utf8 tools/bench.py                              # M2+M3 独立基准：29 张真值图全量实跑 + 规则逐类覆盖（exit 0/1/2）
py -X utf8 tools/gen_synthetic.py --check              # 冻结数据两层守门
py -X utf8 tools/check_whitelist.py                    # 假业务主题白名单校验
```

溯源产物 `provenance.json`：每个渲染值恰一条记录，含 `rendered_value_id`（SHA-256 前 16 hex）、
`row_index` / `csv_line`、逐源单元格 `sources[]`、`transform_chain`、`rendered_label` /
`recomputed_value` / `match`。G1 四形态（缺记录 / `match=false` / 行列不存在 / 源哈希不符）为 ERROR。

规则审计产物 `audit.json`：命中按 `(severity, rule_id, evidence_path)` 排序，含逐条证据与
`alignment` 对齐标注；`verdict=blocked` 当且仅当存在 ERROR 级命中（当前九条均为 ERROR）。

## 退出码契约（定稿，随模块接线逐条激活）

| 码 | 语义 |
| --- | --- |
| 0 | 审计通过（无 ERROR）且产物写出 |
| 1 | 审计完成但存在 ERROR（阻断发布；默认不写可发布 HTML） |
| 2 | 用法 / 输入 / 规格错误 |
| 3 | 规则包或配置缺失 / 校验失败 |

数值口径唯一出处：`data/README.md` 第四节。
