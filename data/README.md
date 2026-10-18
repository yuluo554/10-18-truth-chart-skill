# data/ — 数据台账与纪律

> **查证基准日：2026-10-17**。本文档所有检索式、计数与星数均为该日快照；会随时间漂移的数据一律与基准日成对出现。
> 三态标记：`✅ 已核对`（可直接访问 / 已实测）/ `⬜ 待核对`（路径已登记但未取得或不可用）/ 软论据（检索计数，不可硬化为能力结论）。
> 不可获取的源**不得作规则来源**。

## 一、依据查证记录（竞品与检索）

### 1.1 `gh api` 检索式与计数（基准日 2026-10-17）

| 检索式 | 结果数 | 主要命中 |
| --- | --- | --- |
| `misleading chart visualization` | 7 | `UKPLab/awesome-misleading-visualizations` 13★；`UKPLab/acl2026-misviz` 5★；`cfdbyfed-jpg/chart-auditor` 1★ |
| `data visualization agent skill` | 64 | `larashero3-dotcom/lieflat-charts` **6169★**；`markdown-viewer/skills` 3366★；`gnurio/tufte-vdqi-plugin` **310★**；`caylent/tufte-data-viz` **226★** |
| `claude skill chart` | 285 | `claude-trading-skills` 3033★；`slides_maker` 567★；`marp-slides` 324★；`aref-vc/tufte-claude-skill` **311★**；`gongnangi-chart-skill` 70★ |
| `chart lie factor` | 3 | `rodriguescarson/lie-factor` 1★；`Unspin` 0★；`artgas1/tufte-skill` 0★ |
| `chart audit skill` | 28 | `thu-digitizer` 86★；`mingli-skill` 5★ |
| `data visualization linter` | 12 | `emeeks/viz-linting` 18★（2021 停更） |
| `honest charts agent skill` | 3 | `tufte-data-viz` 226★；`dataviz-design` 2★；`efaimo-ai/honest-chart` 0★ |
| `y axis truncation detector` | **0** | — |
| `chart truncation y axis` | **0** | — |
| `chart data provenance traceability` | **0** | — |
| `data viz quality checker` | **0** | — |

### 1.2 已占能力清单（✅ 实测，本题必须逐条对齐）

| 仓库 | 星数 | 创建日 | 已实现能力 |
| --- | --- | --- | --- |
| `larashero3-dotcom/lieflat-charts` | 6169★ | — | 占据"反误导图表"心智位 |
| `gnurio/tufte-vdqi-plugin` | 310★ | — | 拆为 `tufte-chart` 渲染 + `tufte-critique` 审计（lie factor、chartjunk 分类） |
| `caylent/tufte-data-viz` | 226★ | — | Tufte 风格数据可视化 |
| `aref-vc/tufte-claude-skill` | 311★ | — | Claude Skill 形态的 Tufte 审查 |
| `artgas1/tufte-skill` | 0★ | 2026-10-05 | 约 1500 行检查器：柱状非零基线、双 Y 轴、饼图扇区数与百分比求和、3D、面积编码、平滑插值、时间轴等距、对比度、Vega-Lite / Plotly spec 检查；ERROR 时退出码 1 |
| `efaimo-ai/honest-chart` | 0★ | 2026-09-04 | 从渲染后 SVG 读回数值的 read-back 校验（bar / pie / line / stacked / area） |

### 1.3 其他参照（✅ 实测）

| 仓库 | 星数 | 能力 | 与本题的差异 |
| --- | --- | --- | --- |
| `csv-data-summarizer-claude-skill` | 471★ | pandas / matplotlib 数据摘要 | 无门禁、无溯源 |
| `gongnangi-chart-skill` | 70★ | 咨询风 HTML 图表 | 无审计 |
| `SJAD-67/ChartForge-skill`（chart-forge） | 3★ | PyQt 桌面图表工具 | 非 Skill 形态 |

### 1.4 三态结论

| 结论 | 状态 | 说明 |
| --- | --- | --- |
| 通用"反误导 / Tufte 修正"心智已被占据 | ✅ 事实区分 | 6169★ / 310★ / 226★ / 311★ 四个高星仓库在场 |
| 大部分检查器已实现 | ✅ 事实区分 | `artgas1/tufte-skill` 与 `honest-chart` 的能力清单可逐条对照 |
| 三处窄缝未被覆盖 | ⬜ 软论据 | 检索 0 命中 + 能力对照，基准日 2026-10-17；不得写成"整体空白"或"首创" |

> **软论据纪律**：检索计数只作辅助论据，不得与"竞品已实现某能力"这类可直接查看仓库代码的事实并列作硬锚点。检索式、计数与基准日必须成对出现，便于回溯复跑。

## 二、数据源可获取性记录

| 数据源 | 三态 | 获取方式 | 阻断原因 / 降级处置 |
| --- | --- | --- | --- |
| 外部权威数据源 | — | **不需要** | 本题无外部数据依赖：输入是用户本地 CSV / TSV，规则与阈值自持 |
| 网络请求（运行时） | — | **禁止** | 纯本地；零 CDN；无埋点；断网必须可完整渲染 |
| 合成 CSV / TSV | ✅ 自建 | 生成脚本产出 | 见第三节 |

> 本题**没有**需要联网核对的规则素材（不涉及法规文号、官方统计口径或第三方数据 API）。因此数据台账只登记竞品事实与合成数据纪律，不设"权威数据源待核对"条目——**不得为了凑格式编造数据源**。

## 三、合成数据纪律

### 3.1 假业务主题白名单

- 合成 CSV 的业务主题必须来自白名单，**禁止**使用任何真实公司、真实产品、真实人名或可识别的真实业务数据。
- 白名单（前缀 + 主题词）：
  - 主题前缀：`示例` / `合成` / `教学用`
  - 维度名：`组别`、`批次`、`站点`、`渠道`
  - 指标名：`产量`、`耗时`、`得分`、`单价`、`转化数`
  - 误差棒派生列：上述指标名 + `SD` / `SEM` / `CI下限` / `CI上限`（如 `耗时SD`、`耗时CI下限`）
  - 计数列：`样本数`
  - 标识名：`记录编号`、`样本编号`
- 示例文件名：`synthetic_groups.csv`、`synthetic_errorbars.tsv`。白名单校验脚本在 M1 建立，CI 与本地均可跑。

### 3.2 植入真值（`truth.json`）

- 真值由**生成脚本程序化输出**，与合成 CSV 同源生成；**严禁手抄或由引擎输出回填**。
- 每条真值至少包含：
  - `chart_id`：图标识；
  - `expected_verdict`：`pass` / `blocked`；
  - `expected_errors[]`：`rule_id` 或 `gate_id`（如 `G2_SMALL_N_MEAN_BAR`、`G3_SEM_WITHOUT_SOURCE`）；
  - `expected_provenance[]`：`rendered_value_id → (row_index, column, raw_cell)` 的期望映射。
- 覆盖矩阵（最低要求）：
  1. 干净图：应 `pass`；
  2. M3 九类规则：每类至少一个 `ERROR` 或 `WARN` 用例；
  3. G1：缺溯源记录、`match=false`、行 / 列不存在、源文件哈希不符；
  4. G2：`n < N_MIN` 且偏斜、`n < N_MIN` 且多峰、`n < N_MIN` 但分布均匀（应通过）、合规替代（散点叠加 / 箱线）；
  5. G3：`sd` / `sem` / `ci` / `n` 四种声明各一组正例与反例；包含"只在标题写 SEM、数据无来源"的反例；
  6. 溯源正例：指定某个渲染值必须命中指定 `(row_index, column)`，`raw_cell` 逐字符相等。
- 真值文件与合成 CSV 一并冻结；变更需另立版本号并重跑全部断言。

### 3.3 冻结纪律

- `data/synthetic/` 下的 CSV / TSV、规格 JSON、`truth.json` 在 M1 冻结，此后只读。
- 冻结物必须可复现：生成脚本 + 固定种子 → 产物哈希与 manifest 一致。
- 合成数据**不得**含真实业务数值；数值本身可以任意，但必须与 `truth.json` 一致。

## 四、数值口径纪律（唯一一处定义）

> 以下口径只在本节定义一次。题面、代码常量、审计报告、`SKILL.md` 只**引用**，不得手写第二份表述；如需修改，改本节并同步全部断言。

1. **行号口径**：`row_index` 为 0-based **数据行**序号（不含表头）。界面提示使用 `csv_line = row_index + 2`（表头为第 1 行）。审计 JSON 只写 `row_index`，另附 `csv_line` 冗余字段；两者不得混用。
2. **变换白名单**（唯一枚举）：`identity`、`filter`、`group_sum`、`group_mean`、`group_median`、`group_count`、`ratio`、`sort`、`top_n`、`stack_offset`。白名单外变换一律拒绝，**不允许任意表达式 / 回调**。
3. **精确算术**：审计比对使用 `fractions.Fraction`；解析十进制字符串时按字符串构造精确有理数（`Fraction("0.1")` 语义），**禁止**先转 `float` 再转 `Fraction`。
4. **舍入规则**：`ROUND_HALF_UP`（远离零方向），只在输出标签 / 展示时应用；比较对象为"渲染标签舍入值"与"按同一规则重算的舍入值"。
5. **数值一致阈值**：经舍入后要求**精确相等**；未舍入的中间值比较使用绝对差 `<= 1e-12`（仅作浮点防护，不作为容差结论）。阈值只在代码常量 `TOL_ABS` 定义一次。
6. **样本量阈值**：`N_MIN = 5`（组内观测数）。`n < N_MIN` 触发 G2 检查。
7. **偏斜判据**（确定性公式）：
   - 使用样本偏度 `g1 = m3 / m2^(3/2)`，其中 `m_k = (1/n) * Σ(x_i - x̄)^k`；
   - `|g1| > 1.0` 判为"偏斜"；
   - `n < 3` 或 `m2 = 0`（全等值）时，偏斜判据返回 `undetermined`，不得判为通过或偏斜。
8. **多峰判据**（确定性公式）：
   - 对组内数值排序后做**固定 bins = 6** 的等宽直方图（范围为 `[min, max]`）；
   - 若存在至少 2 个"局部极大 bin"且二者之间至少隔一个 bin，且每个局部极大 bin 的计数 `>= max(2, ceil(n / 6))`，判为"多峰"；
   - `n < 4` 或 `max = min` 时返回 `undetermined`。
9. **G2 判定**：`n < N_MIN` 且（偏斜 = 是 或 多峰 = 是）→ `ERROR`；`undetermined` → `WARN`（报告中注明"未判定"）；否则 `pass`。**合规替代**：该组同时渲染全量散点叠加，或改用箱线图 —— 二者任一成立则降级为 `INFO`。
10. **误差棒类型枚举**（唯一枚举）：`sd`、`sem`、`ci`、`n`。任何其他写法必须映射到这四个之一，映射表在 `references/` 配置中唯一维护；无法映射 → `ERROR`。
11. **误差棒来源判定**：
    - `sd`：存在配对的 SD 列（列名别名表命中），或存在可重算的原始重复测量（重复行数 = n）；
    - `sem`：存在 SEM 列，或存在 SD 列且 `|sem - sd / sqrt(n)| <= TOL_ABS`；
    - `ci`：存在 CI 上下限两列，或同时声明置信水平 + 计算方法 + n 且可重算；
    - `n`：声明值必须等于实际分组计数（存在原始重复测量时以原始行数为准）；
    - 声明类型在数据中无来源 → `ERROR`（来源真实性不成立）；
    - 声明类型与列数值矛盾 → `ERROR`；
    - 未声明误差棒但存在可疑 SD / SEM 列 → `INFO`。
12. **G1 判定**：任一渲染值缺溯源记录、`match=false`、指向不存在的行 / 列、`raw_cell` 与源文件不符、源文件 SHA-256 不符 → 均 `ERROR`。
13. **严重级别**（唯一枚举）：`ERROR` / `WARN` / `INFO`。级别映射只在 `references/rules.json` 定义一次，代码与文档必须一致。
14. **最终判定**：`verdict = blocked` 当且仅当存在至少一个 `ERROR`；否则 `pass`。不允许 `WARN` 阻断发布。
15. **退出码**（唯一语义）：
    - `0`：审计通过（无 ERROR）且产物写出；
    - `1`：审计完成但存在 ERROR（阻断发布；默认不写可发布 HTML）；
    - `2`：用法 / 输入 / 规格错误；
    - `3`：规则包或配置缺失 / 校验失败。
    **禁止**把 ERROR 退化为 0，或在配置缺失时静默按"零规则"通过。
16. **几何常量**：画布宽高、绘图区边距、柱宽、柱间距、标签偏移、字号、刻度数量全部在 `references/geometry.json` 定义一次；HTML 与测试只引用。禁止从浏览器尺寸、屏幕分辨率或随机数推导。
17. **确定性**：输出中不得包含时间戳、随机数、进程 ID、绝对路径、主机名、locale 相关格式；同一输入两次渲染字节级一致。

## 五、隐私与品牌

- 数据纯本地处理，用户 CSV 不上传；HTML 无外链、无埋点、无远程字体。
- 本题方向为**数据→图表的诚信审计**；文档、仓库名、Skill 名不引用本系列其他项目的名称、素材或文档模板。
- 不编造文号、数值、日期；检索计数与星数一律与基准日 2026-10-17 成对出现。
