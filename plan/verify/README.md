# 干净环境验证留档（M6）

> 记录时间：2026-10-18（M6 发布执行中，git tag 之前）。
> 验证环境：Windows（Git Bash），新目录 `git clone --no-local` 副本 + 两个全新 venv
> （Python 3.8.8 / 3.12.10，`py -0p` 实测通道）。
> README「当前可用命令」逐条实跑，退出码对照 README「退出码契约」表判定。

## 一、前置：干净 clone 与两个 venv

| 步骤 | 命令（干净副本根目录） | 结果 |
| --- | --- | --- |
| 干净 clone | `git clone --no-local <仓库> <副本>` | ✅ 10 个提交完整 |
| venv 3.12 | `py -3.12 -m venv .venv312` → `pip install -e ".[dev]"` | ✅ exit 0（pytest 9.1.1） |
| venv 3.8 | `py -3.8 -m venv .venv38` → `pip install -e ".[dev]"` | ✅ exit 0（pytest 8.3.5） |

> 3.8 通道实测一次失败：本机代理环境变量指向不可用代理，pip build isolation
> 子进程 `ProxyError` → `setuptools>=61 (from versions: none)`。属**本机网络环境
> 问题，非包配置缺陷**：绕过代理（`NO_PROXY="*"`）后同一命令 exit 0；
> 3.12 venv 同机同代理下一次通过（走缓存）。CI（GitHub Actions）无此环境变量，
> 不受影响——首推四矩阵实跑结果见 plan/RELEASE-M6.md。

## 二、README 命令逐条实跑（3.12 venv）

| # | 命令 | 退出码 | 语义判定 |
| --- | --- | --- | --- |
| 1 | `pip install -e ".[dev]"` | 0 | ✅ 安装成功 |
| 2 | `pytest -q` | 0 | ✅ **283 passed** |
| 3 | `python -m chartaudit.cli check <groups.csv> <spec_clean_bar.json> --out out/c1` | 0 | ✅ 审计通过，六份 JSON 写出 |
| 4 | `python -m chartaudit.cli build <groups.csv> <spec_clean_bar.json> --out out/c2` | 0 | ✅ `dist/clean_bar.html` 写出 |
| 5 | `python -m chartaudit.cli build <groups.csv> <spec_g2_skewed.json> --out out/c3` | 1 | ✅ 存在 ERROR → 阻断发布，默认零可发布 HTML（非 0 ≠ 跑挂，既定语义） |
| 6 | 同上 + `--emit-audit-html` | 1 | ✅ 调试件 `dist/g2_skewed.audit.html` 写出，退出码仍 1 |
| 7 | `check <groups.csv> <spec_rule_invalid_mark.json>` | 2 | ✅ 非法 mark → 用法错误，零写入 |
| 8 | `python -m chartaudit.cli selftest` | 0 | ✅ 模块形态冒烟 |
| 9 | `chartaudit selftest`（console script） | 0 | ✅ 裸命令形态冒烟 |
| 10 | `py -X utf8 tools/bench.py` | 0 | ✅ **29/29 达标**（M2 独立重算 + M3 8/8+1 + M4 6/6 + M5 发布门 + 13 张哈希） |
| 11 | `py -X utf8 tools/gen_synthetic.py --check` | 0 | ✅ 冻结两层守门 |
| 12 | `py -X utf8 tools/check_whitelist.py` | 0 | ✅ 白名单校验 |

**样例字节一致性抽检**（干净副本内重跑 vs `data/samples/`）：
`clean_bar.html` 与 `g2_skewed.audit.html` `cmp` 逐字节一致 ✅。

## 三、双解释器收集数对账（防包漂移）

| venv | `pytest --collect-only -q` | 全量 `pytest -q` |
| --- | --- | --- |
| 3.12（干净） | **283 tests collected** | 283 passed |
| 3.8（干净） | **283 tests collected** | 283 passed |
| 开发机 3.8 / 3.12 | 283 / 283 | 283 / 283 passed |

同一 extras 集合（`.[dev]`）收集数四处一致：**283**。

## 四、非仓库根 CWD 冒烟（安装面第四面）

在仓库外目录（非 CWD 依赖场景）运行 `python -m chartaudit.cli selftest` 与裸
`chartaudit selftest`：两通路均 exit 0 ✅（editable 安装的 console script 与
模块入口都不依赖当前目录恰在仓库根）。

## 五、3.8 venv 补充实跑

- `tools/bench.py`（3.8）：29/29 达标 exit 0 ✅
- `python -m chartaudit.cli selftest` / `chartaudit selftest`（3.8）：exit 0 / 0 ✅

## 六、CI 通路（首推后补记）

CI 四矩阵（ubuntu/windows × 3.8/3.12）在 GitHub Actions 首推后实跑；run id
与结论据实补记于 `plan/RELEASE-M6.md`（tag 后追加事实栏）与 `plan/00` §五。
