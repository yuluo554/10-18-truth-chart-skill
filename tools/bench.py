"""M2 独立重算基准（交付态入口）。

判别标准：本文件的期望值全部由 CSV/TSV + spec 独立复算，不调用
`chartaudit.provenance` 的聚合/舍入实现；注释掉引擎，期望值仍能算出来。

用法：
    py -X utf8 tools/bench.py

退出码（基准三语义）：
    0 = 全部达标；1 = 未达标；2 = 用法错误。
"""

import contextlib
import copy
import csv
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
from fractions import Fraction

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from chartaudit import cli, parse, provenance  # noqa: E402

DATA = os.path.join(REPO_ROOT, "data", "synthetic")

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


def load_truth():
    with open(os.path.join(DATA, "truth.json"), encoding="utf-8") as f:
        return json.load(f)


def read_raw(filename):
    path = os.path.join(DATA, filename)
    delimiter = "\t" if filename.endswith(".tsv") else ","
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f, delimiter=delimiter))
    return rows[0], rows[1:]


def independent_round_scaled(value, decimals):
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
    if not selected:
        raise AssertionError("独立复算：过滤后无数据")

    y_field = spec["encoding"]["y"]["field"]
    x_field = spec["encoding"]["x"]["field"]
    series_field = spec["encoding"].get("series", {}).get("field")
    decimals = spec["encoding"]["y"].get("decimals")
    if decimals is None:
        raise AssertionError("基准要求 spec 显式 decimals")
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


def inject_g1(chart_id, prov):
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


def run_cli(csv_path, spec_path, out_dir):
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = cli.main(["check", csv_path, spec_path, "--out", out_dir])
    return code, stdout.getvalue(), stderr.getvalue()


def check_chart(chart, temp_root):
    chart_id = chart["chart_id"]
    csv_path = os.path.join(DATA, chart["data"])
    spec_path = os.path.join(DATA, chart["spec"])
    out_dir = os.path.join(temp_root, chart_id)
    code, _, stderr = run_cli(csv_path, spec_path, out_dir)

    if chart["expected_exit"] == 2 and "injection" not in chart:
        if code != 2:
            return False, "invalid-mark 期望 exit 2，实际 %d（%s）" % (code, stderr.strip())
        if os.path.isdir(out_dir):
            return False, "exit 2 失败路径不得写产物"
        return True, "exit=2 零写入"

    if code != 0:
        return False, "正常图表期望 exit 0，实际 %d（%s）" % (code, stderr.strip())
    provenance_path = os.path.join(out_dir, "provenance.json")
    if not os.path.isfile(provenance_path):
        return False, "缺少 provenance.json"
    with open(provenance_path, encoding="utf-8") as f:
        prov = json.load(f)

    # 基础不变量：id 唯一、每值 match
    ids = [record["rendered_value_id"] for record in prov["rendered_values"]]
    if len(ids) != len(set(ids)):
        return False, "rendered_value_id 重复"
    if any(record["match"] is not True for record in prov["rendered_values"]):
        return False, "存在 match != true 的记录"
    for record in prov["rendered_values"]:
        if record["csv_line"] != record["row_index"] + 2:
            return False, "csv_line != row_index + 2"
        if record["rendered_value_id"] != provenance.rendered_value_id(
            prov["spec_id"],
            record["mark_id"],
            record["series"],
            record["category"],
            record["row_index"],
            record["column"],
            record["transform_chain"],
        ):
            return False, "rendered_value_id 与字段重新计算不一致"

    if "injection" in chart:
        inject_g1(chart_id, prov)
        dataset, _, normalized = parse.run(csv_path, spec_path)
        report = provenance.validate(prov, dataset, normalized)
        if report["verdict"] != chart["expected_verdict"]:
            return False, "注入后 verdict=%r" % report["verdict"]
        if report["exit_code"] != chart["expected_exit"]:
            return False, "注入后 exit=%r" % report["exit_code"]
        gate_ids = [issue["gate_id"] for issue in report["errors"]]
        if gate_ids != chart["expected_errors"]:
            return False, "注入后 gate_id=%r" % gate_ids
        return True, "注入 %s → exit=%d" % (gate_ids[0], report["exit_code"])

    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)
    header, rows = read_raw(chart["data"])
    expected = independent_expected_records(spec, header, rows)
    actual = {
        (
            record["series"],
            record["category"],
            record["row_index"],
            record["column"],
        ): record
        for record in prov["rendered_values"]
    }
    if len(expected) != len(prov["rendered_values"]):
        return False, "期望 %d 条记录，实际 %d" % (
            len(expected),
            len(prov["rendered_values"]),
        )
    for item in expected:
        key = (item["series"], item["category"], item["row_index"], item["column"])
        if key not in actual:
            return False, "缺少记录 %r" % (key,)
        record = actual[key]
        if record["raw_cell"] != item["raw_cell"]:
            return False, "raw_cell 不符：%r != %r" % (
                record["raw_cell"],
                item["raw_cell"],
            )
        if record["rendered_label"] != item["label"]:
            return False, "渲染值不符：%r != %r" % (
                record["rendered_label"],
                item["label"],
            )
        if record["recomputed_value"] != item["label"]:
            return False, "重算值不符：%r != %r" % (
                record["recomputed_value"],
                item["label"],
            )
    return True, "%d 个渲染值独立重算一致" % len(expected)


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        print("用法：py -X utf8 tools/bench.py（无参数）", file=sys.stderr)
        return EXIT_USAGE
    truth = load_truth()
    temp_root = tempfile.mkdtemp(prefix="chartaudit-bench-")
    failures = []
    try:
        for chart in truth["charts"]:
            ok, message = check_chart(chart, temp_root)
            status = "PASS" if ok else "FAIL"
            print("[%s] %-24s %s" % (status, chart["chart_id"], message))
            if not ok:
                failures.append((chart["chart_id"], message))
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

    total = len(truth["charts"])
    print("汇总：%d/%d 达标；失败 %d" % (total - len(failures), total, len(failures)))
    if failures:
        for chart_id, message in failures:
            print("  - %s：%s" % (chart_id, message), file=sys.stderr)
        return EXIT_FAILED
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
