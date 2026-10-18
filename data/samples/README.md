# data/samples/ — 审计产物样例（M5）

> 由 `chartaudit build` 于 M5 收尾时一次性生成并冻结（同输入重跑逐字节一致，K26）。
> 用途：不开 CLI 也能直接查看"通过图"与"阻断调试件"的形态。样例不是基准——
> 真值基准在 `tools/bench.py`（29 张冻结图实跑）。

| 文件 | 说明 |
| --- | --- |
| `clean_bar.html` | 通过图（exit 0 时的可发布产物）：`spec_clean_bar`，hover 任一柱可见"此值来自第 X 行第 Y 列 + raw_cell + 变换链" |
| `clean_bar.provenance.json` / `clean_bar.audit.json` / `clean_bar.gates.json` | 通过图的三份审计 JSON |
| `g2_skewed.audit.html` | 阻断图（`--emit-audit-html` 审计调试件，不可发布）：`spec_g2_skewed` 命中 G2 小样本偏斜，页面顶部为阻断横幅 |
| `g2_skewed.provenance.json` / `g2_skewed.audit.json` / `g2_skewed.gates.json` | 阻断图的三份审计 JSON |

再生成方式（字节一致）：

```bash
chartaudit build data/synthetic/synthetic_groups.csv data/synthetic/spec_clean_bar.json --out out/pass
chartaudit build data/synthetic/synthetic_groups.csv data/synthetic/spec_g2_skewed.json --out out/blocked --emit-audit-html
```
