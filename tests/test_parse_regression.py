"""解析器回归基准（冻结样例）+ 独立复算 + 变异探活。

- 期望来自 `data/synthetic/truth.json`（生成器与 CSV 同源产出，禁手抄）；
- 统计期望在测试内**独立复算**（不调用生成器/引擎实现）；
- 溯源正例在数据层先验证 `(row_index, column, raw_cell)` 逐字符一致；
  完整 provenance 断言由 M2 基准启用。
"""

import csv
import json
import math
import os
from fractions import Fraction

import pytest

from chartaudit import parse

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO_ROOT, "data", "synthetic")


def load_truth():
    with open(os.path.join(DATA, "truth.json"), encoding="utf-8") as f:
        return json.load(f)


def read_rows(filename):
    path = os.path.join(DATA, filename)
    delimiter = "\t" if filename.endswith(".tsv") else ","
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter=delimiter)
        rows = list(reader)
    return rows[0], rows[1:]


def independent_g1(values):
    n = len(values)
    if n < 3:
        return None
    mean = Fraction(sum(values), n)
    m2 = sum((Fraction(v) - mean) ** 2 for v in values) / n
    if m2 == 0:
        return None
    m3 = sum((Fraction(v) - mean) ** 3 for v in values) / n
    return float(m3 / (m2 ** Fraction(3, 2)))


def independent_bins(values, bins=6):
    n = len(values)
    lo, hi = min(values), max(values)
    if n < 4 or hi == lo:
        return None
    width = Fraction(hi - lo, bins)
    counts = [0] * bins
    for value in values:
        index = int((value - lo) / width)
        counts[min(index, bins - 1)] += 1
    return counts


def independent_multimodal(counts, n):
    threshold = max(2, int(math.ceil(n / 6.0)))
    maxima = [
        i
        for i, count in enumerate(counts)
        if count >= threshold
        and (i == 0 or count > counts[i - 1])
        and (i == len(counts) - 1 or count > counts[i + 1])
    ]
    return any(maxima[b] - maxima[a] >= 2 for a in range(len(maxima)) for b in range(a + 1, len(maxima)))


def test_frozen_artifacts_exist():
    names = set(os.listdir(DATA))
    for name in ("synthetic_groups.csv", "synthetic_errorbars.tsv", "truth.json", "manifest.json"):
        assert name in names
    assert any(name.startswith("spec_") and name.endswith(".json") for name in names)


def test_every_truth_entry_points_to_existing_files():
    truth = load_truth()
    for chart in truth["charts"]:
        assert os.path.isfile(os.path.join(DATA, chart["data"])), chart["chart_id"]
        assert os.path.isfile(os.path.join(DATA, chart["spec"])), chart["chart_id"]


def test_parser_expectations_match_frozen_files():
    truth = load_truth()
    for filename, expectation in truth["parser_expectations"].items():
        header, rows = read_rows(filename)
        assert len(header) == len(expectation["columns"])
        assert len(rows) == expectation["row_count"]
        assert set(header) == set(expectation["columns"])
        missing = 0
        for row in rows:
            for cell in row:
                if cell == "":
                    missing += 1
        assert missing == expectation["missing_cells"], filename
        dataset, diagnostics, _ = parse.run(
            os.path.join(DATA, filename),
            os.path.join(DATA, "spec_clean_bar.json")
            if filename.endswith(".csv")
            else os.path.join(DATA, "spec_errorbar_sd.json"),
        )
        assert dataset["row_count"] == expectation["row_count"]
        assert dataset["delimiter"] == expectation["delimiter"]
        by_name = {column["name"]: column for column in dataset["columns"]}
        for column, expected_type in expectation["columns"].items():
            assert by_name[column]["type"] == expected_type, (filename, column)
        assert len(diagnostics["missing_cells"]) == expectation["missing_cells"]
        assert diagnostics["duplicate_rows"] == []
        assert diagnostics["duplicate_keys"] == []


@pytest.mark.parametrize(
    "chart_id", [c["chart_id"] for c in load_truth()["charts"]]
)
def test_chart_specs_parse_as_truth_expects(chart_id, tmp_path):
    truth = load_truth()
    chart = next(c for c in truth["charts"] if c["chart_id"] == chart_id)
    csv_path = os.path.join(DATA, chart["data"])
    spec_path = os.path.join(DATA, chart["spec"])

    if chart["expected_exit"] == 2:
        with pytest.raises(parse.ParseError):
            parse.run(csv_path, spec_path)
        return

    dataset, diagnostics, normalized = parse.run(csv_path, spec_path)
    assert dataset["row_count"] == truth["parser_expectations"][chart["data"]]["row_count"]
    assert normalized["spec_id"]


def test_g2_expected_stats_independently_recomputed():
    truth = load_truth()
    checked = 0
    for chart in truth["charts"]:
        stats = chart.get("expected_stats")
        if not stats:
            continue
        with open(os.path.join(DATA, chart["spec"]), encoding="utf-8") as f:
            spec = json.load(f)
        filter_obj = spec["encoding"]["y"]["filter"]
        assert filter_obj["field"] == "组别"
        group = filter_obj["equals"]
        header, rows = read_rows(chart["data"])
        group_index = header.index("组别")
        value_index = header.index("产量")
        values = [int(row[value_index]) for row in rows if row[group_index] == group]
        assert len(values) == stats["n"]
        g1 = independent_g1(values)
        assert round(g1, 6) == stats["g1"], chart["chart_id"]
        counts = independent_bins(values)
        assert counts == stats["bin_counts"], chart["chart_id"]
        assert (abs(g1) > 1.0) is stats["skewed"]
        assert independent_multimodal(counts, len(values)) is stats["multimodal"]
        assert (len(values) < truth["n_min"]) is stats["n_below_min"]
        checked += 1
    assert checked == 5


def test_provenance_expectations_match_frozen_cells():
    truth = load_truth()
    checked = 0
    for chart in truth["charts"]:
        if not chart["expected_provenance"]:
            continue
        header, rows = read_rows(chart["data"])
        for expected in chart["expected_provenance"]:
            column_index = header.index(expected["column"])
            cell = rows[expected["row_index"]][column_index]
            assert cell == expected["raw_cell"], chart["chart_id"]
            checked += 1
    assert checked == 5
