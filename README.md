# chartaudit — 图表诚信审计 Skill（开发中）

> **状态：开发中（M0 计划先行 ✅、M1 数据先行 + 解析层 ✅；M2–M5 未开工）。本 README 只声称下述已实现能力。**

CSV → 单文件 HTML 图表 + 机器可读诚信审计报告：逐值溯源到源 CSV 单元格、聚合可独立重算、样本量不足时禁止画均值柱、误差棒类型必须与数据列一致；存在 ERROR 时阻断发布。

三条窄缝（本题唯一押注；通用反误导检查为对齐已有工作，非创新）：
1. **逐值溯源**：每个渲染数值可回溯源单元格 `(row_index, column, raw_cell, transform_chain)`；
2. **样本量门禁**：n 过小且分布偏斜/多峰时禁止画均值柱；
3. **误差棒来源真实性**：`sd`/`sem`/`ci`/`n` 声明必须能在数据列或重复测量中找到来源。

## 计划

详见 `plan/00-README总览.md`（索引 / 决策记录 / 承诺台账）与 `plan/05-里程碑.md`（M1–M6 DoD）。

## 当前可用命令（M1 已接线：解析层）

```bash
pip install -e ".[dev]"
pytest -q                                              # 全量测试（M1 起含解析器回归基准）
chartaudit check <csv> <spec.json> --out <dir>         # 解析 → dataset/diagnostics/chart_spec.normalized.json（exit 0/2）
chartaudit build <csv> <spec.json> --out <dir>         # 当前等价 check（溯源/门禁/渲染 M2+ 接线）
chartaudit selftest                                    # 内部不变量自检（exit 0）
py -X utf8 tools/gen_synthetic.py --check              # 冻结数据两层守门
py -X utf8 tools/check_whitelist.py                    # 假业务主题白名单校验
```

## 退出码契约（定稿，随模块接线逐条激活）

| 码 | 语义 |
| --- | --- |
| 0 | 审计通过（无 ERROR）且产物写出 |
| 1 | 审计完成但存在 ERROR（阻断发布；默认不写可发布 HTML） |
| 2 | 用法 / 输入 / 规格错误 |
| 3 | 规则包或配置缺失 / 校验失败 |

数值口径唯一出处：`data/README.md` 第四节。
