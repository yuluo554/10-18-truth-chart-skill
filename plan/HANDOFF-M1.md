# HANDOFF-M1（M0 → M1 交接快照）

> 写于 2026-10-18，M0 收尾提交 `c16c019` 之后。续接提示词：
> `/goal 读取 "仓库相对路径" 继续完成任务`

## 1. 当前进度 + 证据

- **M0 完成**：plan/02–06 定稿（架构 / 模块详设 / 数据计划 / 里程碑 / 交付对标+决策记录）；可运行骨架落地并双解释器验证。
- 证据：`py -3.8` / `py -3.12` 双通道 pytest **8 项全绿**（`tests/test_cli_skeleton.py` + `tests/test_serialize.py`）；`python -m chartaudit.cli selftest` exit 4（骨架期显式拦截）；CI workflow 本地 `yaml.safe_load` 解析断言 jobs=1 / steps=6。
- 提交链：`1ffab92`（出题定稿）→ `c16c019`（M0 计划 + 骨架）。
- 待定决策 Q1–Q4 已呈报用户（plan/06 §四）；用户未表态前按建议列执行（Q1 建仓时机、Q2 可见性、Q3 命令名 `chartaudit`、Q4 pytest 已执行）。

## 2. 下一棒待办（M1 数据先行）

按 plan/05 M1 DoD 逐项执行：
1. `tools/gen_synthetic.py`：固定 seed、**禁 stdlib random / 禁系统时钟 / 禁 set 迭代序**（自研确定性 RNG，如 splitmix64）；生成合成 CSV/TSV + spec + `truth.json` + `manifest.json` 入 `data/synthetic/`。
2. 覆盖矩阵（plan/04 §三）：干净图 / M3 九类 / G1 四形态 / G2 偏斜+多峰+均匀+合规替代 / G3 四声明正反例 / 溯源正例。
3. **可检出性下限生成期断言**：生成器用口径 §7/§8 公式复算植入组，断言判为偏斜/多峰；实算值写进 truth.json。
4. CSV/TSV 解析器 `chartaudit/parse.py` + 类型推断 + 缺失/重复诊断 → `dataset.json` / `diagnostics.json`；`build`/`check` 接线（exit 4 语义按退役流程四处同步退役）。
5. `--check` 重生成位级一致守门（**两层**：冻结产物形态 + 重生成逐字节）；白名单校验脚本；解析器回归基准全绿。
6. 收尾：DoD 验证 → plan/00·05·06 回写 → 写 HANDOFF-M2 → commit。

## 3. 既定口径清单（K 项：动了会打挂测试的约定）

- **K1** 数值口径唯一出处 = `data/README.md` 第四节；代码/文档只引用不复写；改口径改那一节并同步全部断言。
- **K2** 退出码契约 0/1/2/3 唯一语义（`exitcodes.py`）；骨架期 4 = 阶段未就绪，模块接线后**整项退役**（常量/CLI/测试/文档四处同步，防幽灵语义复活）。
- **K3** 写盘单点 `serialize.py`：`sort_keys=True, ensure_ascii=False, indent=2` + LF + 尾换行 + 原子写；任何产物 JSON/HTML 不得绕过它。
- **K4** CLI 无子命令 → 返回 EXIT_USAGE（2）而非 SystemExit；未知用法码统一入口收口。
- **K5** 精确算术一律 `Fraction`（按字符串构造，禁 float 中转）；比较精确相等，舍入 ROUND_HALF_UP 仅在输出层。
- **K6** 变换白名单（口径 §2）、误差棒类型枚举（§10）、严重级别枚举（§13）均为唯一枚举，配置落 `references/`，代码零字面量。
- **K7** `rendered_value_id` = SHA-256 前 16 hex，输入字段序固定；行号口径 row_index 0-based 数据行、显示 =+2（§1）。
- **K8** M3 九条规则在 README/审计报告保留"对齐已有工作"标注（验收硬条件，写成创新 = 定位造假）。
- **K9** 真值只存输入与期望，禁 `observed_*` 字段；期望可由输入独立复算（与引擎实现相互独立）。
- **K10** 品牌隔离 + 库内相对路径：HANDOFF/文档不写本机绝对路径与系列项目领域词。

## 4. 本机环境坑（实测过才写）

- 2026-10-18 实测：`py -0p` 有 3.8 与 3.12 两通道，均可用；测试一律 `py -X utf8` + `PYTHONDONTWRITEBYTECODE=1`（防 pyc 坏损），以 `PYTHONPATH=scripts` 跑仓库内包。
- `serialize.write_atomic` 只收 bytes/str——直接喂 dict 会 TypeError（首跑抓过一次，测试已锁正确用法）。
- Git Bash 下临时文件用工作区相对路径；`pip` 需 `NO_PROXY="*"` + 清华镜像（本机代理污染，未在本项目实测 pip install，装包时先验）。
- CI 未推送：四矩阵 workflow 已预置但从未实跑，M6 首推前所有"CI 绿"表述禁用，写"本地等价校验"。

## 5. M1 DoD checklist（打勾前先跑）

- [ ] `tools/gen_synthetic.py` 固定 seed，双跑产物逐字节一致
- [ ] 合成 CSV/TSV + spec + truth.json + manifest.json 冻结入 `data/synthetic/`
- [ ] `--check` 两层守门绿（冻结产物形态 + 重生成比对）
- [ ] 白名单校验脚本 + 测试
- [ ] 解析器 + 诊断产物；`build`/`check` 接线；exit 4 退役四处同步
- [ ] 解析器回归基准全绿；退出码契约测试更新
- [ ] 双解释器全量 pytest；变异探活（生成器改坏必须红）
- [ ] plan/00·05·06 回写 + HANDOFF-M2 落盘 + commit

## 6. 关键命令速查（写时实跑过）

```bash
cd 仓库相对路径
export PYTHONDONTWRITEBYTECODE=1
PYTHONPATH=scripts py -X utf8 -m pytest -q          # 3.8 全量（3.12 换解释器）
PYTHONPATH=scripts py -X utf8 -m chartaudit.cli selftest   # 现为 exit 4，接线后改 0
py -3.12 -X utf8 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml', encoding='utf-8'))"  # 改 workflow 后必跑
```
