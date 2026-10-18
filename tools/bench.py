"""M2 + M3 独立基准（交付态入口）。

判别标准：
- M2：期望值由 CSV/TSV + spec 独立复算，不调用 `chartaudit.provenance` 的
  聚合 / 舍入实现；注释掉引擎，期望值仍能算出来。
- M3：规则命中期望只来自 truth.json 与 `references/rules.json` 的规则包（直接读
  JSON 文件，不 import 规则判定实现）。

K13-A 口径（2026-10-18 决策，见 plan/06 D28）：truth 的 `expected_exit` 重定义为
"解析层退出码"（0 = 解析通过，2 = 解析拒绝，冻结数据不改）；最终退出码由
`expected_verdict` 推导：
    - 解析层拒绝 → exit 2（零写入；K15：R009 规格合法性由解析层拦截）
    - blocked（存在已接线审计层 ERROR）→ exit 1
    - pass → exit 0
M3 阶段 G2/G3 门禁尚未接线：仅由 G2/G3 期望阻断的图按"过渡态"断言（exit 0 +
规则层零 ERROR），M4 接线 gates.json 后必须把该分支改为阻断断言。

用法：
    py -X utf8 tools/bench.py

退出码（基准三语义）：
    0 = 全部达标；1 = 未达标；2 = 用法错误。
"""

import contextlib
import csv
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
RULES_PATH = os.path.join(REPO_ROOT, "references", "rules.json")

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


def load_rule_ids():
    """规则 id 只从规则包读取（基准不 import 判定实现，避免自证）。"""
    with open(RULES_PATH, encoding="utf-8") as f:
        config = json.load(f)
    return {entry["rule_id"] for entry in config["rules"]}


RULE_IDS = load_rule_ids()


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
    """返回 (ok, message, hit_rule_ids)。"""
    chart_id = chart["chart_id"]
    csv_path = os.path.join(DATA, chart["data"])
    spec_path = os.path.join(DATA, chart["spec"])
    out_dir = os.path.join(temp_root, chart_id)
    code, _, stderr = run_cli(csv_path, spec_path, out_dir)

    # K13-A：expected_exit 是解析层退出码；2 = 解析拒绝（K15 规格合法性）
    if chart["expected_exit"] == 2 and "injection" not in chart:
        if code != 2:
            return (
                False,
                "invalid-mark 期望 exit 2，实际 %d（%s）" % (code, stderr.strip()),
                set(),
            )
        if os.path.isdir(out_dir):
            return False, "exit 2 失败路径不得写产物", set()
        return True, "exit=2 零写入（规格合法性由解析层拦截）", set()

    expected_error_ids = list(chart["expected_errors"])
    rule_layer = bool(expected_error_ids) and set(expected_error_ids) <= RULE_IDS
    deferred_layer = bool(expected_error_ids) and not rule_layer
    # K13-A：最终退出码由 expected_verdict / 已接线层推导（M3：规则层已接线，G2/G3 未接线）
    expected_cli_exit = EXIT_FAILED if rule_layer else EXIT_OK
    if code != expected_cli_exit:
        return (
            False,
            "期望 exit %d（K13-A 推导），实际 %d（%s）"
            % (expected_cli_exit, code, stderr.strip()),
            set(),
        )

    provenance_path = os.path.join(out_dir, "provenance.json")
    if not os.path.isfile(provenance_path):
        return False, "缺少 provenance.json", set()
    with open(provenance_path, encoding="utf-8") as f:
        prov = json.load(f)

    # 基础不变量：id 唯一、每值 match
    ids = [record["rendered_value_id"] for record in prov["rendered_values"]]
    if len(ids) != len(set(ids)):
        return False, "rendered_value_id 重复", set()
    if any(record["match"] is not True for record in prov["rendered_values"]):
        return False, "存在 match != true 的记录", set()
    for record in prov["rendered_values"]:
        if record["csv_line"] != record["row_index"] + 2:
            return False, "csv_line != row_index + 2", set()
        if record["rendered_value_id"] != provenance.rendered_value_id(
            prov["spec_id"],
            record["mark_id"],
            record["series"],
            record["category"],
            record["row_index"],
            record["column"],
            record["transform_chain"],
        ):
            return False, "rendered_value_id 与字段重新计算不一致", set()

    if "injection" in chart:
        inject_g1(chart_id, prov)
        dataset, _, normalized = parse.run(csv_path, spec_path)
        report = provenance.validate(prov, dataset, normalized)
        if report["verdict"] != chart["expected_verdict"]:
            return False, "注入后 verdict=%r" % report["verdict"], set()
        if report["exit_code"] != chart["expected_exit"]:
            return False, "注入后 exit=%r" % report["exit_code"], set()
        gate_ids = [issue["gate_id"] for issue in report["errors"]]
        if gate_ids != chart["expected_errors"]:
            return False, "注入后 gate_id=%r" % gate_ids, set()
        return True, "注入 %s → exit=%d" % (gate_ids[0], report["exit_code"]), set()

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
        return (
            False,
            "期望 %d 条记录，实际 %d"
            % (len(expected), len(prov["rendered_values"])),
            set(),
        )
    for item in expected:
        key = (item["series"], item["category"], item["row_index"], item["column"])
        if key not in actual:
            return False, "缺少记录 %r" % (key,), set()
        record = actual[key]
        if record["raw_cell"] != item["raw_cell"]:
            return (
                False,
                "raw_cell 不符：%r != %r" % (record["raw_cell"], item["raw_cell"]),
                set(),
            )
        if record["rendered_label"] != item["label"]:
            return (
                False,
                "渲染值不符：%r != %r"
                % (record["rendered_label"], item["label"]),
                set(),
            )
        if record["recomputed_value"] != item["label"]:
            return (
                False,
                "重算值不符：%r != %r"
                % (record["recomputed_value"], item["label"]),
                set(),
            )

    # M3 规则层（audit.json 由交付态 CLI 写出）
    audit_path = os.path.join(out_dir, "audit.json")
    if not os.path.isfile(audit_path):
        return False, "缺少 audit.json", set()
    with open(audit_path, encoding="utf-8") as f:
        audit_obj = json.load(f)
    order = {
        level: index for index, level in enumerate(audit_obj["severity_order"])
    }
    sort_keys = [
        (order[finding["severity"]], finding["rule_id"], finding["evidence_path"])
        for finding in audit_obj["findings"]
    ]
    if sort_keys != sorted(sort_keys):
        return (
            False,
            "audit.json 排序不稳定（severity, rule_id, evidence_path）",
            set(),
        )
    blocking = sorted(
        finding["rule_id"]
        for finding in audit_obj["findings"]
        if finding["severity"] == audit_obj["block_on"]
    )
    blocking_ids = set(blocking)

    if rule_layer:
        if audit_obj["verdict"] != chart["expected_verdict"]:
            return (
                False,
                "规则层 verdict=%r（期望 %r）"
                % (audit_obj["verdict"], chart["expected_verdict"]),
                set(),
            )
        missing = [
            rule_id for rule_id in expected_error_ids if rule_id not in blocking_ids
        ]
        if missing:
            return (
                False,
                "规则未命中 %s（实际 %s）" % (missing, blocking),
                blocking_ids,
            )
        return True, "规则命中 %s → exit=1" % ",".join(blocking), blocking_ids

    if blocking:
        return (
            False,
            "非规则层图表不应有规则 ERROR：%s" % ",".join(blocking),
            blocking_ids,
        )
    if deferred_layer:
        return (
            True,
            "M3 过渡态：exit=0；%s 由 M4 门禁接线后阻断"
            % ",".join(expected_error_ids),
            set(),
        )
    if chart["expected_infos"]:
        return (
            True,
            "%d 个渲染值独立重算一致；INFO %s 待 M4 gates 接线"
            % (len(expected), ",".join(chart["expected_infos"])),
            set(),
        )
    return True, "%d 个渲染值独立重算一致；规则 0 命中" % len(expected), set()


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        print("用法：py -X utf8 tools/bench.py（无参数）", file=sys.stderr)
        return EXIT_USAGE
    truth = load_truth()
    temp_root = tempfile.mkdtemp(prefix="chartaudit-bench-")
    failures = []
    hit_rule_ids = set()
    try:
        for chart in truth["charts"]:
            ok, message, hit_ids = check_chart(chart, temp_root)
            status = "PASS" if ok else "FAIL"
            print("[%s] %-24s %s" % (status, chart["chart_id"], message))
            hit_rule_ids |= hit_ids
            if not ok:
                failures.append((chart["chart_id"], message))
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

    # 逐类覆盖：truth 里植入的规则 id 必须全部在 audit 中检出（R009 走解析层）
    planted_rule_ids = set()
    parse_layer_ids = set()
    for chart in truth["charts"]:
        if chart["expected_errors"] and set(chart["expected_errors"]) <= RULE_IDS:
            planted_rule_ids |= set(chart["expected_errors"])
        if chart["expected_exit"] == 2 and "injection" not in chart:
            parse_layer_ids |= set(chart["expected_errors"])
    audit_planted = planted_rule_ids - parse_layer_ids
    missing_rules = sorted(audit_planted - hit_rule_ids)
    print(
        "M3 规则覆盖：%d/%d 类审计层规则检出；%d 类由解析层 exit 2 拦截"
        % (
            len(audit_planted & hit_rule_ids),
            len(audit_planted),
            len(parse_layer_ids),
        )
    )
    if missing_rules:
        print("M3 规则覆盖失败：未检出 %s" % ", ".join(missing_rules), file=sys.stderr)

    total = len(truth["charts"])
    print("汇总：%d/%d 达标；失败 %d" % (total - len(failures), total, len(failures)))
    if failures:
        for chart_id, message in failures:
            print("  - %s：%s" % (chart_id, message), file=sys.stderr)
        return EXIT_FAILED
    if missing_rules:
        return EXIT_FAILED
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
