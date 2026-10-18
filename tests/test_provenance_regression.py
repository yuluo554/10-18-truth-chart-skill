"""M2 溯源回归基准：truth 正例 + 独立重算 + G1 四形态注入。

独立性判别：本文件不 import `chartaudit.provenance` 的计算路径来求期望值；
期望由 CSV/TSV + spec 在测试内独立复算（注释掉引擎也能算出来）。
"""

import copy
import csv
import json
import os
from fractions import Fraction

import pytest

from chartaudit import parse, provenance

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO_ROOT, "data", "synthetic")


def load_truth():
    with open(os.path.join(DATA, "truth.json"), encoding="utf-8") as f:
        return json.load(f)


def read_raw(filename):
    path = os.path.join(DATA, filename)
    delimiter = "\t" if filename.endswith(".tsv") else ","
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f, delimiter=delimiter))
    return rows[0], rows[1:]


def load_spec(filename):
    with open(os.path.join(DATA, filename), encoding="utf-8") as f:
        return json.load(f)


def independent_round_scaled(value, decimals):
    """独立整数算术实现 ROUND_HALF_UP，不调用引擎的舍入函数。"""
    assert decimals is not None
    scale = 10 ** decimals
    numerator = value.numerator * scale
    denominator = value.denominator
    magnitude, remainder = divmod(abs(numerator), denominator)
    if remainder * 2 >= denominator:
        magnitude += 1
    if numerator < 0:
        magnitude = -magnitude
    return magnitude


def independent_format(value, decimals):
    scaled = independent_round_scaled(value, decimals)
    sign = "-" if scaled < 0 else ""
    digits = str(abs(scaled))
    if decimals == 0:
        return sign + digits
    digits = digits.rjust(decimals + 1, "0")
    return sign + digits[:-decimals] + "." + digits[-decimals:]


def independent_median(values):
    ordered = sorted(values)
    count = len(ordered)
    if count % 2:
        return ordered[count // 2]
    return (ordered[count // 2 - 1] + ordered[count // 2]) / 2


def independent_expected_records(spec, header, rows):
    index = {name: position for position, name in enumerate(header)}
    conditions = []
    for channel_name in ("x", "y"):
        filter_obj = spec["encoding"].get(channel_name, {}).get("filter")
        if filter_obj:
            conditions.append((filter_obj["field"], filter_obj["equals"]))
    selected = [
        (row_index, row)
        for row_index, row in enumerate(rows)
        if all(row[index[field]] == expected for field, expected in conditions)
    ]
    assert selected, "独立复算：过滤后无数据"

    y_field = spec["encoding"]["y"]["field"]
    x_field = spec["encoding"]["x"]["field"]
    series_field = spec["encoding"].get("series", {}).get("field")
    decimals = spec["encoding"]["y"].get("decimals")
    aggregate = spec["encoding"]["y"].get("aggregate")
    if aggregate is None and spec["mark"] == "pie":
        aggregate = "group_sum"
    if aggregate is None:
        expected = []
        for row_index, row in selected:
            raw_cell = row[index[y_field]]
            expected.append(
                {
                    "series": row[index[series_field]] if series_field else None,
                    "category": row[index[x_field]],
                    "row_index": row_index,
                    "column": y_field,
                    "raw_cell": raw_cell,
                    "label": independent_format(Fraction(raw_cell), decimals),
                }
            )
        return expected

    groups = []
    group_index = {}
    for row_index, row in selected:
        series = row[index[series_field]] if series_field else None
        category = row[index[x_field]]
        key = (series, category)
        if key not in group_index:
            group_index[key] = len(groups)
            groups.append({"series": series, "category": category, "rows": []})
        groups[group_index[key]]["rows"].append((row_index, row))

    denominator = None
    if aggregate == "ratio":
        denominator = sum(
            (Fraction(row[index[y_field]]) for _, row in selected), Fraction(0)
        )
    expected = []
    for group in groups:
        values = [Fraction(row[index[y_field]]) for _, row in group["rows"]]
        if aggregate == "group_sum":
            value = sum(values, Fraction(0))
        elif aggregate == "group_mean":
            value = sum(values, Fraction(0)) / len(values)
        elif aggregate == "group_median":
            value = independent_median(values)
        elif aggregate == "group_count":
            value = Fraction(len(values))
        elif aggregate == "ratio":
            value = sum(values, Fraction(0)) / denominator
        else:
            raise AssertionError("独立复算未覆盖的聚合：%r" % aggregate)
        first_row_index, first_row = group["rows"][0]
        expected.append(
            {
                "series": group["series"],
                "category": group["category"],
                "row_index": first_row_index,
                "column": y_field,
                "raw_cell": first_row[index[y_field]],
                "label": independent_format(value, decimals),
            }
        )
    return expected


def test_truth_provenance_positives_all_hit():
    truth = load_truth()
    chart = next(c for c in truth["charts"] if c["chart_id"] == "scatter_identity")
    dataset, _, normalized = parse.run(
        os.path.join(DATA, chart["data"]), os.path.join(DATA, chart["spec"])
    )
    prov = provenance.build(dataset, normalized)
    records = prov["rendered_values"]
    assert len(records) == len(chart["expected_provenance"]) == 5

    header, rows = read_raw(chart["data"])
    column_index = header.index("产量")
    for expected in chart["expected_provenance"]:
        matches = [
            record
            for record in records
            if record["row_index"] == expected["row_index"]
            and record["column"] == expected["column"]
            and record["raw_cell"] == expected["raw_cell"]
        ]
        assert len(matches) == 1, expected
        record = matches[0]
        assert record["csv_line"] == expected["row_index"] + 2
        assert record["sources"] == [
            {
                "row_index": expected["row_index"],
                "csv_line": expected["row_index"] + 2,
                "column": expected["column"],
                "raw_cell": expected["raw_cell"],
                "parsed_value": matches[0]["parsed_value"],
            }
        ]
        # raw_cell 逐字符相等（不是数值相等）
        assert record["raw_cell"] == rows[expected["row_index"]][column_index]
        assert record["rendered_label"] == "%.1f" % int(expected["raw_cell"])
        assert record["match"] is True


@pytest.mark.parametrize(
    "chart_id",
    [chart["chart_id"] for chart in load_truth()["charts"]],
)
def test_independent_recompute_matches_engine(chart_id):
    truth = load_truth()
    chart = next(c for c in truth["charts"] if c["chart_id"] == chart_id)
    csv_path = os.path.join(DATA, chart["data"])
    spec_path = os.path.join(DATA, chart["spec"])

    if chart["expected_exit"] == 2:
        with pytest.raises(parse.ParseError):
            parse.run(csv_path, spec_path)
        return

    dataset, _, normalized = parse.run(csv_path, spec_path)
    prov = provenance.build(dataset, normalized)
    records = prov["rendered_values"]
    spec = load_spec(chart["spec"])
    header, rows = read_raw(chart["data"])
    expected_records = independent_expected_records(spec, header, rows)

    assert len(records) == len(expected_records), chart_id
    assert len({record["rendered_value_id"] for record in records}) == len(records)

    actual = {
        (
            record["series"],
            record["category"],
            record["row_index"],
            record["column"],
        ): record
        for record in records
    }
    for expected in expected_records:
        key = (
            expected["series"],
            expected["category"],
            expected["row_index"],
            expected["column"],
        )
        assert key in actual, (chart_id, key)
        record = actual[key]
        assert record["raw_cell"] == expected["raw_cell"], (chart_id, key)
        assert record["rendered_label"] == expected["label"], (chart_id, key)
        assert record["recomputed_value"] == expected["label"], (chart_id, key)
        assert record["match"] is True, (chart_id, key)

    report = provenance.validate(prov, dataset, normalized)
    assert report["verdict"] == "pass", (chart_id, report["errors"])
    assert report["error_count"] == 0


def test_row_index_and_csv_line_convention():
    truth = load_truth()
    checked = 0
    for chart in truth["charts"]:
        if chart["expected_exit"] == 2:
            continue
        dataset, _, normalized = parse.run(
            os.path.join(DATA, chart["data"]), os.path.join(DATA, chart["spec"])
        )
        prov = provenance.build(dataset, normalized)
        for record in prov["rendered_values"]:
            assert "row_index" in record and "csv_line" in record
            assert "line" not in record and "line_number" not in record
            assert 0 <= record["row_index"] < dataset["row_count"]
            assert record["csv_line"] == record["row_index"] + 2
            assert record["row_index"] == record["sources"][0]["row_index"]
            assert record["csv_line"] == record["sources"][0]["csv_line"]
            for source in record["sources"]:
                assert source["csv_line"] == source["row_index"] + 2
                assert 0 <= source["row_index"] < dataset["row_count"]
            checked += 1
    assert checked > 0


def _inject(chart_id, prov):
    if chart_id == "g1_missing_record":
        prov["rendered_values"].pop()
    elif chart_id == "g1_match_false":
        prov["rendered_values"][0]["recomputed_value"] = "999.9"
        prov["rendered_values"][0]["match"] = False
    elif chart_id == "g1_row_column_missing":
        prov["rendered_values"][0]["row_index"] = 999
        prov["rendered_values"][0]["csv_line"] = 1001
    elif chart_id == "g1_hash_mismatch":
        prov["source"]["sha256"] = "0" * 64
    else:  # pragma: no cover
        raise AssertionError(chart_id)


@pytest.mark.parametrize(
    "chart_id",
    [
        "g1_missing_record",
        "g1_match_false",
        "g1_row_column_missing",
        "g1_hash_mismatch",
    ],
)
def test_g1_four_form_injection(chart_id):
    truth = load_truth()
    chart = next(c for c in truth["charts"] if c["chart_id"] == chart_id)
    dataset, _, normalized = parse.run(
        os.path.join(DATA, chart["data"]), os.path.join(DATA, chart["spec"])
    )
    prov = provenance.build(dataset, normalized)
    _inject(chart_id, prov)

    report = provenance.validate(prov, dataset, normalized)
    assert report["verdict"] == "blocked"
    assert report["render_allowed"] is False
    assert report["exit_code"] == chart["expected_exit"] == 1
    assert [issue["gate_id"] for issue in report["errors"]] == chart["expected_errors"]
    assert all(issue["severity"] == "ERROR" for issue in report["errors"])


def test_injection_does_not_touch_frozen_data():
    """注入只发生在内存中的 provenance 对象；冻结目录哈希不变由生成器守门覆盖。"""
    with open(os.path.join(DATA, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["files"]
    assert manifest["caliber"]["path"] == "data/README.md"
    assert os.path.isfile(os.path.join(DATA, "synthetic_groups.csv"))
