#!/usr/bin/env python3
"""M1 合成数据生成器 + 冻结守门（唯一生成入口）。

纪律（plan/04 §二）：
- 固定 seed；禁 stdlib random、禁系统时钟、禁 set 迭代序（自研 splitmix64）；
- 真值与 CSV/TSV 同源生成，严禁手抄回填；真值只存输入与期望，无 observed_*；
- M1 冻结后只读；`--check` 两层断言：
    第一层 冻结产物形态（manifest 覆盖完整、哈希与实物一致、无缺件/多件）；
    第二层 重生成到临时目录后逐字节比对。

用法：
    py -X utf8 tools/gen_synthetic.py --write      # 重生成并写盘（仅 M1 冻结时使用）
    py -X utf8 tools/gen_synthetic.py --check      # 两层守门，0=一致 1=不一致 2=用法错误
    py -X utf8 tools/gen_synthetic.py --check --data-dir <dir>
"""

import argparse
import csv
import hashlib
import io
import json
import math
import os
import subprocess
import sys
import tempfile
from fractions import Fraction

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "data", "synthetic")
GENERATOR_REL = "tools/gen_synthetic.py"
CALIBER_REL = "data/README.md"

SEED = 20261018
N_MIN = 5  # 口径 §6：仅生成期断言使用，运行时实现由 references/ 配置持有

MASK64 = (1 << 64) - 1


class SplitMix64:
    """自研确定性 RNG（无 stdlib random / 无时钟参与）。"""

    def __init__(self, seed):
        self.state = seed & MASK64

    def next_u64(self):
        self.state = (self.state + 0x9E3779B97F4A7C15) & MASK64
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
        return (z ^ (z >> 31)) & MASK64

    def below(self, bound):
        """[0, bound) 上的确定性整数。"""
        return self.next_u64() % bound


# ---------------------------------------------------------------- 统计口径实现
# 生成期断言用（口径 §7/§8）；与运行时引擎实现相互独立。


def skew_g1(values):
    n = len(values)
    if n < 3:
        return None
    mean = Fraction(sum(values), n)
    m2 = sum((Fraction(v) - mean) ** 2 for v in values) / n
    if m2 == 0:
        return None
    m3 = sum((Fraction(v) - mean) ** 3 for v in values) / n
    return float(m3 / (m2 ** Fraction(3, 2)))


def bin_counts(values, bins=6):
    n = len(values)
    lo, hi = min(values), max(values)
    if n < 4 or hi == lo:
        return None
    width = Fraction(hi - lo, bins)
    counts = [0] * bins
    for v in values:
        idx = int((v - lo) / width)
        if idx == bins:
            idx = bins - 1
        counts[idx] += 1
    return counts


def is_multimodal(counts, n):
    threshold = max(2, int(math.ceil(n / 6.0)))
    maxima = []
    for i, c in enumerate(counts):
        if c < threshold:
            continue
        left = counts[i - 1] if i > 0 else None
        right = counts[i + 1] if i < len(counts) - 1 else None
        if left is not None and c <= left:
            continue
        if right is not None and c <= right:
            continue
        maxima.append(i)
    for a in range(len(maxima)):
        for b in range(a + 1, len(maxima)):
            if maxima[b] - maxima[a] >= 2:
                return True
    return False


def classify(values):
    """返回 (skewed, multimodal, g1, counts) 的确定性判定。"""
    g1 = skew_g1(values)
    counts = bin_counts(values)
    multimodal = bool(counts) and is_multimodal(counts, len(values))
    skewed = g1 is not None and abs(g1) > 1.0
    return skewed, multimodal, g1, counts


# ---------------------------------------------------------------- 数据设计
# 假业务主题白名单（data/README §3.1）。真实公司/产品/人名一律禁止。
GROUPS_HEADER = ["组别", "批次", "样本编号", "产量"]
ERRORBARS_HEADER = [
    "组别",
    "样本编号",
    "耗时",
    "耗时SD",
    "耗时SEM",
    "耗时CI下限",
    "耗时CI上限",
    "样本数",
]

JIA_DATES = ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05"]
YI_DATES = ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-06"]
BING_DATES = ["2026-01-01", "2026-01-02", "2026-01-05", "2026-01-06"]
DING_DATES = ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-06"]
WU_DATES = ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]

# 乙/丙/丁 组为植入信号，数值一旦改动必须重生成整目录并复核生成期断言。
YI_VALUES = [1, 1, 1, 10]  # 偏斜（|g1| > 1）
BING_VALUES = [1, 1, 9, 9]  # 双峰（bins=6，两个局部极大各 2）
DING_VALUES = [2, 2, 2, 9]  # 偏斜 + 合规替代用例
WU_VALUES = [10, 11, 12, 13]  # 均匀（n<N_MIN 仍应通过）

TSV_GROUPS = {
    "组S": [10, 12, 11, 13],
    "组M": [8, 10, 12, 14],
    "组C": [10, 12, 11, 13],
    "组N": [10, 12, 11, 13],
    "组N2": [10, 12, 11, 13],
    "组T": [10, 12, 11, 13],
    "组E": [10, 12, 11, 13],
}
TSV_SD = {"组S": "1.5", "组M": "9.0"}
TSV_CI = {"组C": ("7.5", "15.5")}
TSV_N = {"组N": "4", "组N2": "7"}


def build_tables():
    rng = SplitMix64(SEED)
    jia_values = [10 + rng.below(5) for _ in range(5)]
    wu_gen_values = [10 + rng.below(4) for _ in range(4)]

    group_rows = []
    seq = 1
    for name, dates, values in (
        ("甲组", JIA_DATES, jia_values),
        ("乙组", YI_DATES, YI_VALUES),
        ("丙组", BING_DATES, BING_VALUES),
        ("丁组", DING_DATES, DING_VALUES),
        ("戊组", WU_DATES, wu_gen_values),
    ):
        for date, value in zip(dates, values):
            group_rows.append([name, date, "S%03d" % seq, str(value)])
            seq += 1

    tsv_rows = []
    seq = 1
    for name, values in TSV_GROUPS.items():
        for value in values:
            sd = TSV_SD.get(name, "")
            sem = ""
            lo, hi = TSV_CI.get(name, ("", ""))
            n_value = TSV_N.get(name, "")
            tsv_rows.append(
                [name, "T%03d" % seq, str(value), sd, sem, lo, hi, n_value]
            )
            seq += 1

    return jia_values, wu_gen_values, group_rows, tsv_rows


# ---------------------------------------------------------------- 规格构造


def enc_y(field="产量", aggregate=None, group=None, decimals=1):
    y = {"field": field, "decimals": decimals}
    if aggregate:
        y["aggregate"] = aggregate
    if group:
        y["filter"] = {"field": "组别", "equals": group}
    return y


def spec(
    spec_id,
    title,
    mark,
    x_field="组别",
    y=None,
    extra=None,
    error_bar=None,
):
    obj = {
        "spec_id": spec_id,
        "title": title,
        "mark": mark,
        "encoding": {"x": {"field": x_field}, "y": y or enc_y()},
    }
    if error_bar is not None:
        obj["encoding"]["error_bar"] = error_bar
    if extra:
        obj.update(extra)
    return obj


def build_specs():
    specs = {}

    def add(s):
        specs["spec_%s.json" % s["spec_id"]] = s

    # ---- 干净图 + 溯源正例
    add(
        spec(
            "clean_bar",
            "合成示例：甲组产量均值",
            "bar",
            y=enc_y(aggregate="group_mean", group="甲组"),
            extra={"primary_key": ["组别", "样本编号"]},
        )
    )
    add(
        spec(
            "scatter_identity",
            "合成示例：甲组逐样本产量",
            "scatter",
            x_field="样本编号",
            y=enc_y(group="甲组"),
            extra={"primary_key": ["样本编号"]},
        )
    )

    # ---- M3 九条规则（对齐已有工作，非创新）
    add(
        spec(
            "rule_baseline",
            "合成示例：非零基线柱状",
            "bar",
            y=enc_y(aggregate="group_mean", group="甲组"),
            extra={"y_zero": False},
        )
    )
    add(
        spec(
            "rule_dual_y",
            "合成示例：双 Y 轴",
            "bar",
            y=enc_y(aggregate="group_mean", group="甲组"),
            extra={"dual_y": True},
        )
    )
    add(
        spec(
            "rule_pie",
            "合成示例：扇区求和",
            "pie",
            y=enc_y(aggregate="group_sum"),
        )
    )
    add(
        spec(
            "rule_3d",
            "合成示例：伪三维柱状",
            "bar",
            y=enc_y(aggregate="group_mean", group="甲组"),
            extra={"pseudo_3d": True},
        )
    )
    add(
        spec(
            "rule_radius",
            "合成示例：半径面积编码",
            "pie",
            y=enc_y(aggregate="group_sum"),
            extra={"size_channel": "radius"},
        )
    )
    add(
        spec(
            "rule_smooth",
            "合成示例：平滑折线",
            "line",
            x_field="样本编号",
            y=enc_y(group="甲组"),
            extra={"smooth": True},
        )
    )
    add(
        spec(
            "rule_time_uneven",
            "合成示例：不等距时间轴",
            "line",
            x_field="批次",
            y=enc_y(group="乙组"),
        )
    )
    add(
        spec(
            "rule_contrast",
            "合成示例：低对比度",
            "bar",
            y=enc_y(aggregate="group_mean", group="甲组"),
            extra={"low_contrast": True},
        )
    )
    add(
        spec(
            "rule_invalid_mark",
            "合成示例：非法图型",
            "bar3d",
            y=enc_y(aggregate="group_mean", group="甲组"),
        )
    )

    # ---- G2 样本量门禁
    add(
        spec(
            "g2_skewed",
            "合成示例：小样本偏斜均值柱",
            "bar",
            y=enc_y(aggregate="group_mean", group="乙组"),
        )
    )
    add(
        spec(
            "g2_bimodal",
            "合成示例：小样本双峰均值柱",
            "bar",
            y=enc_y(aggregate="group_mean", group="丙组"),
        )
    )
    add(
        spec(
            "g2_uniform_ok",
            "合成示例：小样本均匀均值柱",
            "bar",
            y=enc_y(aggregate="group_mean", group="戊组"),
        )
    )
    add(
        spec(
            "g2_scatter_alt",
            "合成示例：小样本偏斜（散点替代）",
            "bar",
            y=enc_y(aggregate="group_mean", group="丁组"),
            extra={"overlay_scatter": True},
        )
    )
    add(
        spec(
            "g2_box_alt",
            "合成示例：小样本偏斜（箱线替代）",
            "box",
            y=enc_y(group="丁组"),
        )
    )

    # ---- G3 误差棒来源真实性
    add(
        spec(
            "errorbar_sd",
            "合成示例：SD 来源",
            "bar",
            y=enc_y(field="耗时", aggregate="group_mean", group="组S"),
            error_bar={"type": "sd", "column": "耗时SD"},
        )
    )
    add(
        spec(
            "errorbar_sem",
            "合成示例：SEM 重算",
            "bar",
            y=enc_y(field="耗时", aggregate="group_mean", group="组M"),
            error_bar={"type": "sem"},
        )
    )
    add(
        spec(
            "errorbar_ci",
            "合成示例：CI 上下限",
            "bar",
            y=enc_y(field="耗时", aggregate="group_mean", group="组C"),
            error_bar={"type": "ci"},
        )
    )
    add(
        spec(
            "errorbar_n",
            "合成示例：n 声明",
            "bar",
            y=enc_y(field="耗时", aggregate="group_mean", group="组N"),
            error_bar={"type": "n", "column": "样本数"},
        )
    )
    add(
        spec(
            "g3_sd_missing",
            "合成示例：SD 来源缺失",
            "bar",
            y=enc_y(field="耗时", aggregate="group_mean", group="组T"),
            error_bar={"type": "sd"},
        )
    )
    add(
        spec(
            "g3_sem_missing",
            "合成示例：SEM 无来源",
            "bar",
            y=enc_y(field="耗时", aggregate="group_mean", group="组E"),
            error_bar={"type": "sem"},
        )
    )
    add(
        spec(
            "g3_n_mismatch",
            "合成示例：n 与行数不符",
            "bar",
            y=enc_y(field="耗时", aggregate="group_mean", group="组N2"),
            error_bar={"type": "n", "column": "样本数"},
        )
    )
    add(
        spec(
            "g3_ci_incomplete",
            "合成示例：CI 只有下限",
            "bar",
            y=enc_y(field="耗时", aggregate="group_mean", group="组C"),
            error_bar={"type": "ci", "column": "耗时CI下限"},
        )
    )
    add(
        spec(
            "g3_title_sem",
            "合成示例：耗时均值（SEM）",
            "bar",
            y=enc_y(field="耗时", aggregate="group_mean", group="组T"),
        )
    )

    return specs


# ---------------------------------------------------------------- 真值构造


def chart_entry(
    chart_id,
    data,
    spec_file,
    verdict,
    errors=(),
    infos=(),
    exit_code=0,
    stats=None,
    injection=None,
    provenance=None,
):
    entry = {
        "chart_id": chart_id,
        "data": data,
        "spec": spec_file,
        "expected_exit": exit_code,
        "expected_verdict": verdict,
        "expected_errors": list(errors),
        "expected_infos": list(infos),
    }
    if stats is not None:
        entry["expected_stats"] = stats
    if injection is not None:
        entry["injection"] = injection
    entry["expected_provenance"] = provenance or []
    return entry


def group_stats(values, n_expected):
    skewed, multimodal, g1, counts = classify(values)
    stats = {
        "n": len(values),
        "n_below_min": len(values) < N_MIN,
        "skewed": skewed,
        "multimodal": multimodal,
        "g1": None if g1 is None else round(g1, 6),
        "bin_counts": counts,
    }
    if len(values) != n_expected:
        raise AssertionError("样本量设计不符：期望 %d，实际 %d" % (n_expected, len(values)))
    return stats


def build_truth(jia_values, wu_values):
    groups_csv = "synthetic_groups.csv"
    tsv = "synthetic_errorbars.tsv"

    yi_stats = group_stats(YI_VALUES, 4)
    bing_stats = group_stats(BING_VALUES, 4)
    ding_stats = group_stats(DING_VALUES, 4)
    wu_stats = group_stats(wu_values, 4)

    # 生成期可检出性下限断言：植入信号必须对准口径判定线
    assert yi_stats["n_below_min"] and yi_stats["skewed"], "乙组必须判为偏斜"
    assert bing_stats["n_below_min"] and bing_stats["multimodal"], "丙组必须判为多峰"
    assert not bing_stats["skewed"], "丙组不应判为偏斜（检验判据独立）"
    assert ding_stats["skewed"] and ding_stats["n_below_min"], "丁组必须判为偏斜"
    assert wu_stats["n_below_min"], "戊组样本量必须低于阈值"
    assert not wu_stats["skewed"] and not wu_stats["multimodal"], "戊组必须判为均匀"

    charts = [
        chart_entry("clean_bar", groups_csv, "spec_clean_bar.json", "pass"),
        chart_entry(
            "scatter_identity",
            groups_csv,
            "spec_scatter_identity.json",
            "pass",
            provenance=[
                {"row_index": 0, "column": "产量", "raw_cell": str(jia_values[0])},
                {"row_index": 1, "column": "产量", "raw_cell": str(jia_values[1])},
                {"row_index": 2, "column": "产量", "raw_cell": str(jia_values[2])},
                {"row_index": 3, "column": "产量", "raw_cell": str(jia_values[3])},
                {"row_index": 4, "column": "产量", "raw_cell": str(jia_values[4])},
            ],
        ),
        chart_entry(
            "rule_baseline",
            groups_csv,
            "spec_rule_baseline.json",
            "blocked",
            errors=["R001_BAR_NONZERO_BASELINE"],
        ),
        chart_entry(
            "rule_dual_y",
            groups_csv,
            "spec_rule_dual_y.json",
            "blocked",
            errors=["R002_DUAL_Y_AXIS"],
        ),
        chart_entry(
            "rule_pie",
            groups_csv,
            "spec_rule_pie.json",
            "blocked",
            errors=["R003_PIE_SECTORS_SUM"],
        ),
        chart_entry(
            "rule_3d",
            groups_csv,
            "spec_rule_3d.json",
            "blocked",
            errors=["R004_PSEUDO_3D"],
        ),
        chart_entry(
            "rule_radius",
            groups_csv,
            "spec_rule_radius.json",
            "blocked",
            errors=["R005_RADIUS_ENCODING"],
        ),
        chart_entry(
            "rule_smooth",
            groups_csv,
            "spec_rule_smooth.json",
            "blocked",
            errors=["R006_SMOOTH_OVERSHOOT"],
        ),
        chart_entry(
            "rule_time_uneven",
            groups_csv,
            "spec_rule_time_uneven.json",
            "blocked",
            errors=["R007_TIME_AXIS_UNEVEN"],
        ),
        chart_entry(
            "rule_contrast",
            groups_csv,
            "spec_rule_contrast.json",
            "blocked",
            errors=["R008_LOW_CONTRAST"],
        ),
        chart_entry(
            "rule_invalid_mark",
            groups_csv,
            "spec_rule_invalid_mark.json",
            "blocked",
            errors=["R009_SPEC_INVALID"],
            exit_code=2,
        ),
        chart_entry(
            "g2_skewed",
            groups_csv,
            "spec_g2_skewed.json",
            "blocked",
            errors=["G2_SMALL_N_MEAN_BAR"],
            stats=yi_stats,
        ),
        chart_entry(
            "g2_bimodal",
            groups_csv,
            "spec_g2_bimodal.json",
            "blocked",
            errors=["G2_SMALL_N_MEAN_BAR"],
            stats=bing_stats,
        ),
        chart_entry("g2_uniform_ok", groups_csv, "spec_g2_uniform_ok.json", "pass", stats=wu_stats),
        chart_entry(
            "g2_scatter_alt",
            groups_csv,
            "spec_g2_scatter_alt.json",
            "pass",
            infos=["G2_SMALL_N_MEAN_BAR"],
            stats=ding_stats,
        ),
        chart_entry(
            "g2_box_alt",
            groups_csv,
            "spec_g2_box_alt.json",
            "pass",
            infos=["G2_SMALL_N_MEAN_BAR"],
            stats=ding_stats,
        ),
        chart_entry("errorbar_sd", tsv, "spec_errorbar_sd.json", "pass"),
        chart_entry("errorbar_sem", tsv, "spec_errorbar_sem.json", "pass"),
        chart_entry("errorbar_ci", tsv, "spec_errorbar_ci.json", "pass"),
        chart_entry("errorbar_n", tsv, "spec_errorbar_n.json", "pass"),
        chart_entry(
            "g3_sd_missing",
            tsv,
            "spec_g3_sd_missing.json",
            "blocked",
            errors=["G3_SD_SOURCE_MISSING"],
        ),
        chart_entry(
            "g3_sem_missing",
            tsv,
            "spec_g3_sem_missing.json",
            "blocked",
            errors=["G3_SEM_SOURCE_MISSING"],
        ),
        chart_entry(
            "g3_n_mismatch",
            tsv,
            "spec_g3_n_mismatch.json",
            "blocked",
            errors=["G3_N_MISMATCH"],
        ),
        chart_entry(
            "g3_ci_incomplete",
            tsv,
            "spec_g3_ci_incomplete.json",
            "blocked",
            errors=["G3_CI_INCOMPLETE"],
        ),
        chart_entry(
            "g3_title_sem",
            tsv,
            "spec_g3_title_sem.json",
            "blocked",
            errors=["G3_SEM_WITHOUT_SOURCE"],
        ),
        # G1 四形态：M2 溯源层实现后由基准注入对应缺陷并断言（真值此处只登记输入与期望）
        chart_entry(
            "g1_missing_record",
            groups_csv,
            "spec_clean_bar.json",
            "blocked",
            errors=["G1_PROVENANCE_MISSING"],
            exit_code=1,
            injection="M2: 删除一条 rendered_value 溯源记录",
        ),
        chart_entry(
            "g1_match_false",
            groups_csv,
            "spec_clean_bar.json",
            "blocked",
            errors=["G1_PROVENANCE_MISMATCH"],
            exit_code=1,
            injection="M2: 篡改 recomputed_value 使 match=false",
        ),
        chart_entry(
            "g1_row_column_missing",
            groups_csv,
            "spec_clean_bar.json",
            "blocked",
            errors=["G1_ROW_COLUMN_NOT_FOUND"],
            exit_code=1,
            injection="M2: 溯源指向不存在的 row_index/column",
        ),
        chart_entry(
            "g1_hash_mismatch",
            groups_csv,
            "spec_clean_bar.json",
            "blocked",
            errors=["G1_HASH_MISMATCH"],
            exit_code=1,
            injection="M2: 源文件 SHA-256 与 provenance.json 记录不符",
        ),
    ]

    parser_expectations = {
        "synthetic_groups.csv": {
            "delimiter": ",",
            "row_count": 21,
            "columns": {
                "组别": "string",
                "批次": "date",
                "样本编号": "string",
                "产量": "integer",
            },
            "missing_cells": 0,
        },
        "synthetic_errorbars.tsv": {
            "delimiter": "\t",
            "row_count": 28,
            "columns": {
                "组别": "string",
                "样本编号": "string",
                "耗时": "integer",
                "耗时SD": "decimal",
                "耗时SEM": "string",  # 全列缺失 → 无类型证据，按 string
                "耗时CI下限": "decimal",
                "耗时CI上限": "decimal",
                "样本数": "integer",
            },
            "missing_cells": 116,
        },
    }

    return {
        "contract_version": 1,
        "seed": SEED,
        "n_min": N_MIN,
        "parser_expectations": parser_expectations,
        "charts": charts,
    }


# ---------------------------------------------------------------- 写盘


def json_bytes(obj):
    from chartaudit.serialize import dumps_json

    return dumps_json(obj)


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def render_csv(header, rows, delimiter):
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=delimiter, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def generate_artifacts():
    """返回 {filename: bytes}，全部由固定 seed 与常量决定。"""
    jia_values, wu_values, group_rows, tsv_rows = build_tables()
    specs = build_specs()
    truth = build_truth(jia_values, wu_values)

    artifacts = {
        "synthetic_groups.csv": render_csv(GROUPS_HEADER, group_rows, ","),
        "synthetic_errorbars.tsv": render_csv(ERRORBARS_HEADER, tsv_rows, "\t"),
        "truth.json": json_bytes(truth),
    }
    for name in sorted(specs):
        artifacts[name] = json_bytes(specs[name])
    return artifacts


def build_manifest(artifacts, data_dir):
    """manifest 覆盖全部冻结产物 + 生成器 + 口径文件。"""
    files = sorted(artifacts)
    manifest = {
        "contract_version": 1,
        "seed": SEED,
        "generator": {"path": GENERATOR_REL, "sha256": file_sha256(os.path.join(REPO_ROOT, GENERATOR_REL))},
        "caliber": {"path": CALIBER_REL, "sha256": file_sha256(os.path.join(REPO_ROOT, CALIBER_REL))},
        "files": {},
    }
    for name in files:
        manifest["files"][name] = hashlib.sha256(artifacts[name]).hexdigest()
    return manifest


def write_all(artifacts, manifest):
    from chartaudit.serialize import write_atomic

    os.makedirs(DATA_DIR, exist_ok=True)
    for name in sorted(artifacts):
        write_atomic(os.path.join(DATA_DIR, name), artifacts[name])
    write_atomic(os.path.join(DATA_DIR, "manifest.json"), json_bytes(manifest))


def check(data_dir):
    """两层守门。返回 (ok, messages)。"""
    messages = []
    manifest_path = os.path.join(data_dir, "manifest.json")
    if not os.path.isfile(manifest_path):
        return False, ["第一层失败：缺少 manifest.json"]

    with open(manifest_path, "rb") as f:
        manifest = json.loads(f.read().decode("utf-8"))

    artifacts = generate_artifacts()
    expected_names = set(artifacts) | {"manifest.json"}
    actual_names = set(os.listdir(data_dir))
    missing = sorted(expected_names - actual_names)
    extra = sorted(actual_names - expected_names)
    if missing:
        messages.append("第一层失败：缺件 %s" % ", ".join(missing))
    if extra:
        messages.append("第一层失败：多件 %s" % ", ".join(extra))
    if missing:
        return False, messages

    for name in sorted(manifest.get("files", {})):
        path = os.path.join(data_dir, name)
        if not os.path.isfile(path):
            messages.append("第一层失败：manifest 登记文件缺失 %s" % name)
            continue
        actual = file_sha256(path)
        if actual != manifest["files"][name]:
            messages.append("第一层失败：哈希不符 %s" % name)

    for name in sorted(artifacts):
        if name == "manifest.json":
            continue
        with open(os.path.join(data_dir, name), "rb") as f:
            frozen = f.read()
        if frozen != artifacts[name]:
            messages.append("第二层失败：重生成字节不一致 %s" % name)

    return (not messages), messages


def run_check(data_dir):
    ok, messages = check(data_dir)
    if ok:
        print("gen_synthetic --check: 两层守门通过（冻结产物与重生成逐字节一致）")
        return 0
    for message in messages:
        print(message, file=sys.stderr)
    return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="M1 合成数据生成器（固定 seed，确定性产物）")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true", help="重生成并写盘（M1 冻结时使用）")
    group.add_argument("--check", action="store_true", help="两层守门：形态 + 逐字节重生成比对")
    parser.add_argument("--data-dir", default=DATA_DIR, help="冻结目录（默认 data/synthetic）")
    args = parser.parse_args(argv)

    sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

    if args.write:
        artifacts = generate_artifacts()
        manifest = build_manifest(artifacts, args.data_dir)
        write_all(artifacts, manifest)
        print("已写入 %d 个冻结产物 + manifest.json 到 %s" % (len(artifacts), args.data_dir))
        return 0
    return run_check(args.data_dir)


if __name__ == "__main__":
    sys.exit(main())
