# chartaudit — 图表诚信审计 Skill

> CSV → 单文件 HTML 图表 + 机器可读诚信审计报告。每个渲染数值都能回溯源 CSV 单元格、每个聚合都能被独立重算、样本量不足时禁止画均值柱、误差棒类型必须与数据列一致；存在 ERROR 时阻断发布（退出码 1，默认不产出可发布 HTML）。
>
> 三条窄缝（差异化主线）：① 逐值溯源 ② 样本量门禁 ③ 误差棒来源真实性。通用反误导规则（柱状非零基线 / 双 Y 轴 / 饼图 / 3D / 面积半径编码 / 平滑 / 时间轴等距 / 对比度 / 规格合法性）属**对齐已有工作，非创新**，见 `references/rules.json` 的 `alignment` 标注。

## 触发条件

当用户需要以下任一工作时使用本 Skill：

- 把 CSV / TSV 数据画成图表，并要求图表数值**可追溯、可审计**；
- 检查既有图表规格是否存在误导性声明（截断轴、双 Y 轴、伪 3D、平滑过冲等）；
- 验证均值柱的**样本量是否充分**（n 过小且偏斜 / 多峰时必须换散点叠加或箱线图）;
- 验证误差棒声明（`sd` / `sem` / `ci` / `n`）**是否在数据列中有真实来源**；
- 要求渲染产物**确定性**（同输入两次渲染字节级一致）且**零外部依赖**（单文件 HTML、零 CDN、断网可用）。

不适用：在线取数渲染、Vega-Lite / Plotly / ECharts spec 兼容检查、力导向 / 自适应布局、发布被 ERROR 阻断后"先出图再说"的场景。

## 工作流

1. **确认输入**：用户提供 CSV / TSV（UTF-8，含 BOM 可接受）+ 规格 JSON（`mark` ∈ bar / line / scatter / box / pie；`encoding` 白名单 x / y / series / error_bar；未知字段直接 exit 2，不静默忽略）。
2. **跑全链**：`chartaudit build <csv> <spec.json> --out <dir>`。一次命令产出 `dataset.json` / `diagnostics.json` / `chart_spec.normalized.json` / `provenance.json` / `audit.json` / `gates.json` 与（通过时）`dist/<name>.html`。
3. **读退出码**：0 = 通过并产出可发布 HTML；1 = 存在 ERROR，被阻断，默认无可发布 HTML；2 = 用法 / 输入 / 规格错误（零写入）；3 = 规则包 / 门禁包 / 别名表 / 几何包缺失或非法（零写入）。
4. **按报告修复**：`audit.json`（九条规则，对齐已有工作）与 `gates.json`（三条窄缝：G1 溯源完备性 / G2 样本量门禁 / G3 误差棒来源真实性）逐条给出 rule_id / gate_id、证据路径与修复建议。数据问题改数据，规格问题改规格；**不得**手工"修数据"绕过审计——任何数据修正必须落为显式 filter / transform 并进入溯源链。
5. **重跑直到通过**：只有 exit 0 时 `dist/<name>.html` 才是可发布产物；hover 任一图元可看到"此值来自第 X 行第 Y 列 + 原始单元格 + 变换链"。

## 调用示例

```bash
# 安装（纯标准库，零运行时依赖；pytest 仅为 dev extra；需 Python >= 3.12）
pip install -e ".[dev]"

# 打印版本（与 pyproject 同一处口径；exit 0）
chartaudit --version

# 全链构建：审计 + 渲染（通过 → dist/clean_bar.html，exit 0）
chartaudit build data/synthetic/synthetic_groups.csv data/synthetic/spec_clean_bar.json --out out/demo

# 只审计不渲染
chartaudit check data/synthetic/synthetic_groups.csv data/synthetic/spec_clean_bar.json --out out/demo

# 存在 ERROR：exit 1，默认零可发布 HTML；显式要求调试件（带阻断横幅，不可发布）
chartaudit build data/synthetic/synthetic_groups.csv data/synthetic/spec_g2_skewed.json --out out/blocked --emit-audit-html
# → out/blocked/dist/g2_skewed.audit.html（exit 仍 1）

# 内部不变量自检（退出码 / 序列化 / 类型推断 / 规则包 / 门禁包 / 几何包）
chartaudit selftest

# 独立真值基准（29 张冻结图全量实跑；期望值独立复算，不引用引擎实现）
py -X utf8 tools/bench.py
```

`python -m chartaudit.cli ...` 与裸命令 `chartaudit ...` 两种入口等价。

## 输出产物

| 文件 | 内容 |
| --- | --- |
| `dataset.json` | 解析结果：列类型、源文件 SHA-256、行数 |
| `diagnostics.json` | 缺失 / 类型冲突 / 重复行 / 重复键诊断 |
| `chart_spec.normalized.json` | 规格编译结果（字段序固定，默认值显式化） |
| `provenance.json` | 每个渲染值恰一条溯源记录（`rendered_value_id`、`row_index` / `csv_line`、逐源单元格 `sources[]`、`transform_chain`、`match`） |
| `audit.json` | 九条规则命中（按 severity, rule_id, evidence_path 排序；携带 `alignment` 对齐标注） |
| `gates.json` | 三条窄缝门禁：G1 引用溯源验证 verdict；G2 逐组 n / g1 / bin_counts；G3 逐组误差棒来源判定 |
| `dist/<name>.html` | 可发布单文件 HTML（仅 exit 0 时写出） |
| `dist/<name>.audit.html` | 阻断调试件（仅 `--emit-audit-html` 时写出；带阻断横幅，不可发布） |

## 机器可解析契约块

以下块与 `scripts/chartaudit/render.py` 的代码常量、实际渲染输出做**三方断言**（集合相等 + 顺序相等；`tests/test_render.py::test_skill_contract_block_triple_agreement` 锁定，任何一处漂移测试必红）：

<!-- chartaudit-contract
{
  "exit_codes": {
    "0": "审计通过且产物写出（含 dist/<name>.html）",
    "1": "审计完成但存在 ERROR（阻断发布；默认不写可发布 HTML）",
    "2": "用法 / 输入 / 规格错误",
    "3": "规则包或配置缺失 / 校验失败"
  },
  "html_sections": ["chart", "audit", "provenance-data"],
  "html_provenance_fields": [
    "rendered_value_id",
    "csv_line",
    "column",
    "raw_cell",
    "parsed_value",
    "transform_chain",
    "transform_summary",
    "rendered_label",
    "exact_value",
    "series",
    "category",
    "sources",
    "sources_count"
  ]
}
-->

- `html_sections`：每个产物 HTML 必含的区块标记（`data-section` 属性）。
- `html_provenance_fields`：hover 溯源载荷的字段集合与顺序（数据源只来自 `provenance.json` 记录；`csv_line = row_index + 2`，表头为第 1 行）。

## 诚实边界

- **对齐标注**：九条规则与 `artgas1/tufte-skill`（0★，2026-10-05 实测）等已有实现高度重叠，不作为创新点；差异化只在三条窄缝。
- **确定性**：输出不含时间戳 / 随机数 / 进程 ID / 绝对路径 / locale 格式；几何常量唯一出处 `references/geometry.json`；同输入两次渲染字节级一致。
- **纯本地**：无网络请求、无埋点、无远程字体；用户数据不上传。
- **合成数据**：`data/synthetic/` 为程序化生成的冻结数据（假业务主题白名单约束），真值台账 `truth.json` 与数据同源生成，非手抄回填。

## 目录结构

```
SKILL.md                  本文件（Skill 主入口 + 契约块）
scripts/chartaudit/       parse / provenance / rules / gates / render / cli
references/               rules.json / gates.json / aliases.json / geometry.json（唯一出处）
data/synthetic/           冻结 CSV/TSV + spec + truth.json + manifest
tests/                    pytest（含契约门、字节复现门、零字面量扫描门、注入式证伪）
tools/                    gen_synthetic / bench / check_whitelist
plan/                     项目计划与交接快照
```
