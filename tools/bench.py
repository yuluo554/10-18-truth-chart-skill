"""M2 + M3 + M4 + M5 独立基准（交付态入口）。

判别标准：
- M2：期望值由 CSV/TSV + spec 独立复算，不调用 `chartaudit.provenance` 的
  聚合 / 舍入实现；注释掉引擎，期望值仍能算出来。
- M3：规则命中期望只来自 truth.json 与 `references/rules.json` 的规则包（直接读
  JSON 文件，不 import 规则判定实现）。
- M4：门禁命中期望只来自 truth.json 与 `references/gates.json` 门禁包（同样只读
  JSON，不 import 门禁判定实现）；G2 期望统计逐值对 truth 的 expected_stats。
- M5：全链 `build` 实跑 —— 发布门产物存在性 + HTML 哈希双跑断言 + 零 CDN
  静态扫描门 + hover 载荷与 provenance 逐键对照 + 注入式证伪（渲染值被篡改 →
  必须阻断）。几何常量只从 `references/geometry.json` 读取。

K13-A 口径（2026-10-18 决策，见 plan/06 D28）：truth 的 `expected_exit` 重定义为
"解析层退出码"（0 = 解析通过，2 = 解析拒绝，冻结数据不改）；最终退出码由
`expected_verdict` 推导：
    - 解析层拒绝 → exit 2（零写入；K15：R009 规格合法性由解析层拦截）
    - blocked（存在已接线审计层 ERROR）→ exit 1
    - pass → exit 0
M4 起 G1/G2/G3 门禁全部接线：g2_*/g3_* 共 9 张图由 M3 过渡态（exit 0）收紧为
阻断断言（blocked → exit 1）；g2_scatter_alt / g2_box_alt 的 INFO 在 gates.json
中兑现（exit 0）。
M5 发布门（D10/K27）：blocked → 默认零可发布 HTML（dist/ 无 <name>.html）；
`--emit-audit-html` 调试件 `<name>.audit.html` 仅供审计（exit 仍 1）；pass →
`dist/<name>.html` 且 sha256 双跑一致。

用法：
    py -X utf8 tools/bench.py

退出码（基准三语义）：
    0 = 全部达标；1 = 未达标；2 = 用法错误。
"""

import contextlib
import csv
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
from fractions import Fraction

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from chartaudit import cli, parse, provenance  # noqa: E402

DATA = os.path.join(REPO_ROOT, "data", "synthetic")
RULES_PATH = os.path.join(REPO_ROOT, "references", "rules.json")
GATES_PATH = os.path.join(REPO_ROOT, "references", "gates.json")
GEOMETRY_PATH = os.path.join(REPO_ROOT, "references", "geometry.json")

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

# M5 零 CDN 静态扫描门（K25/K26）：产物 HTML 不得含任何外部资源引用
CDN_PATTERNS = (
    "<script src=",
    "<script\t",
    "<link",
    "url(",
    "@import",
    "http://",
    "https://",
)


def load_rule_ids():
    """规则 id 只从规则包读取（基准不 import 判定实现，避免自证）。"""
    with open(RULES_PATH, encoding="utf-8") as f:
        config = json.load(f)
    return {entry["rule_id"] for entry in config["rules"]}


def load_gate_ids():
    """门禁 id 只从门禁包读取（基准不 import 门禁判定实现，避免自证）。"""
    with open(GATES_PATH, encoding="utf-8") as f:
        config = json.load(f)
    return {entry["gate_id"] for entry in config["gates"]}


RULE_IDS = load_rule_ids()
GATE_IDS = load_gate_ids()


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


def run_build(csv_path, spec_path, out_dir, extra=()):
    """交付态 build 入口实跑（M5 全链基准）。"""
    stdout = io.StringIO()
    stderr = io.StringIO()
    argv = ["build", csv_path, spec_path, "--out", out_dir] + list(extra)
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = cli.main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def load_geometry_values():
    """几何常量只从 references/geometry.json 读取（K25：不引用引擎实现）。"""
    with open(GEOMETRY_PATH, encoding="utf-8") as f:
        return json.load(f)["values"]


def scan_zero_cdn(html_text):
    """静态零 CDN 扫描门：返回命中的违规模式列表（空 = 通过）。"""
    return [pattern for pattern in CDN_PATTERNS if pattern in html_text.lower()]


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def extract_payload(html_text):
    """从产物 HTML 提取 hover 溯源载荷 JSON（独立解析，不经引擎）。"""
    match = re.search(
        r'<script type="application/json" id="chartaudit-provenance"[^>]*>(.*?)</script>',
        html_text,
        re.S,
    )
    if match is None:
        raise AssertionError("产物 HTML 缺少 chartaudit-provenance 数据岛")
    return json.loads(match.group(1))


def check_m5_build(chart, temp_root):
    """M5 全链发布门基准：返回 (ok, message, html_sha256)。

    独立于 render 实现：期望全部由 truth + 配置文件 + provenance.json 推导。
    """
    chart_id = chart["chart_id"]
    csv_path = os.path.join(DATA, chart["data"])
    spec_path = os.path.join(DATA, chart["spec"])

    # 解析层拒绝（rule_invalid_mark）：exit 2 零写入，无 dist
    if chart["expected_exit"] == 2 and "injection" not in chart:
        out_dir = os.path.join(temp_root, "m5-" + chart_id)
        code, _, _ = run_build(csv_path, spec_path, out_dir)
        if code != 2:
            return False, "build 期望 exit 2，实际 %d" % code, None
        if os.path.isdir(out_dir):
            return False, "exit 2 路径不得写任何产物", None
        return True, "exit=2 零写入（无渲染）", None

    # G1 注入图：check 路径在 check_chart 已覆盖判定；此处验证 build 的发布门
    # 语义（正常 build 无注入 → exit 0 + 产物，与 truth 注入期望是两回事）。
    if "injection" in chart:
        out_dir = os.path.join(temp_root, "m5-" + chart_id)
        code, _, _ = run_build(csv_path, spec_path, out_dir)
        with open(spec_path, encoding="utf-8") as f:
            spec = json.load(f)
        name = re.sub(r"[^A-Za-z0-9._-]", "_", spec["spec_id"])
        if code != 0:
            return False, "无注入 build 期望 exit 0，实际 %d" % code, None
        published = os.path.join(out_dir, "dist", name + ".html")
        if not os.path.isfile(published):
            return False, "无注入 build 缺少 dist/%s.html" % name, None
        with open(published, "rb") as f:
            html_bytes = f.read()
        violations = scan_zero_cdn(html_bytes.decode("utf-8"))
        if violations:
            return False, "产物含外部资源引用：%s" % violations, None
        # 注入复算（与 check_chart 同桩）：篡改后 validate 必须阻断（M2 语义）
        with open(os.path.join(out_dir, "provenance.json"), encoding="utf-8") as f:
            prov = json.load(f)
        inject_g1(chart_id, prov)
        dataset, _, normalized = parse.run(csv_path, spec_path)
        report = provenance.validate(prov, dataset, normalized)
        if report["verdict"] != "blocked":
            return False, "G1 注入 build 侧复算未阻断", None
        return (
            True,
            "G1 注入：build pass 出图 + 注入复算 blocked；发布门不受注入桩影响",
            sha256_bytes(html_bytes),
        )

    expected_verdict = chart["expected_verdict"]
    expected_error_ids = set(chart["expected_errors"])
    blocked = expected_verdict == "blocked"
    out_dir = os.path.join(temp_root, "m5-" + chart_id)

    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)
    name = re.sub(r"[^A-Za-z0-9._-]", "_", spec["spec_id"])

    if blocked:
        code, _, _ = run_build(csv_path, spec_path, out_dir)
        if code != 1:
            return False, "blocked build 期望 exit 1，实际 %d" % code, None
        dist = os.path.join(out_dir, "dist")
        if os.path.isdir(dist) and os.listdir(dist):
            return False, "blocked 默认不得产出 HTML：%s" % os.listdir(dist), None
        # --emit-audit-html：调试件带阻断横幅 + 审计条目 + 零 CDN，exit 仍 1
        out_dbg = os.path.join(temp_root, "m5dbg-" + chart_id)
        code_dbg, _, _ = run_build(csv_path, spec_path, out_dbg, ["--emit-audit-html"])
        if code_dbg != 1:
            return False, "调试件 build 期望 exit 1，实际 %d" % code_dbg, None
        audit_html = os.path.join(out_dbg, "dist", name + ".audit.html")
        if not os.path.isfile(audit_html):
            return False, "缺少调试件 %s.audit.html" % name, None
        with open(audit_html, encoding="utf-8") as f:
            html_text = f.read()
        violations = scan_zero_cdn(html_text)
        if violations:
            return False, "调试件含外部资源引用：%s" % violations, None
        if "审计阻断" not in html_text:
            return False, "调试件缺少阻断横幅", None
        if not os.path.isfile(os.path.join(out_dbg, "gates.json")):
            return False, "调试件路径缺少 gates.json", None
        return True, "blocked → 默认零 HTML；调试件含横幅 + 零 CDN + exit 1", None

    # pass：exit 0 + dist/<name>.html + 零 CDN + hover 载荷对照 + 双跑哈希
    code, _, _ = run_build(csv_path, spec_path, out_dir)
    if code != 0:
        return False, "pass build 期望 exit 0，实际 %d" % code, None
    published = os.path.join(out_dir, "dist", name + ".html")
    if not os.path.isfile(published):
        return False, "缺少可发布产物 dist/%s.html" % name, None
    with open(published, "rb") as f:
        first_bytes = f.read()
    html_text = first_bytes.decode("utf-8")
    violations = scan_zero_cdn(html_text)
    if violations:
        return False, "产物含外部资源引用：%s" % violations, None

    # hover 载荷与 provenance.json 逐键对照（K29：渲染层不得改值）
    with open(os.path.join(out_dir, "provenance.json"), encoding="utf-8") as f:
        prov = json.load(f)
    payload = extract_payload(html_text)
    expected_records = {r["rendered_value_id"]: r for r in prov["rendered_values"]}
    if set(payload["records"]) != set(expected_records):
        return False, "hover 载荷 id 集合与 provenance 不符", None
    for rid, record in expected_records.items():
        item = payload["records"][rid]
        if item["csv_line"] != record["csv_line"]:
            return False, "hover csv_line 与 provenance 不符：%s" % rid, None
        if item["raw_cell"] != record["raw_cell"]:
            return False, "hover raw_cell 与 provenance 不符：%s" % rid, None
        if item["rendered_label"] != record["rendered_label"]:
            return False, "hover rendered_label 与 provenance 不符：%s" % rid, None

    # 双跑哈希一致（K26）
    out_dir2 = os.path.join(temp_root, "m5r-" + chart_id)
    code2, _, _ = run_build(csv_path, spec_path, out_dir2)
    if code2 != 0:
        return False, "复跑 exit %d" % code2, None
    with open(os.path.join(out_dir2, "dist", name + ".html"), "rb") as f:
        second_bytes = f.read()
    if first_bytes != second_bytes:
        return False, "两次渲染 HTML 字节不一致", None

    # 注入式证伪（每张 pass 图）：篡改 provenance 渲染标签 → build 必须阻断
    falsified = dict(prov)
    falsified["rendered_values"] = [dict(r) for r in prov["rendered_values"]]
    falsified["rendered_values"][0]["rendered_label"] = "999.9"
    falsified["rendered_values"][0]["recomputed_value"] = "999.9"
    tampered_dir = os.path.join(temp_root, "m5tamper-" + chart_id)
    os.makedirs(tampered_dir, exist_ok=True)
    with open(os.path.join(tampered_dir, "provenance.json"), "w", encoding="utf-8") as f:
        json.dump(falsified, f, ensure_ascii=False)
    # 直接用 validate 独立复算（不经 CLI 注入桩）：match 校验必须翻红
    dataset, _, normalized = parse.run(csv_path, spec_path)
    report = provenance.validate(falsified, dataset, normalized)
    if report["verdict"] != "blocked":
        return False, "注入式证伪失败：篡改渲染值未被检出", None

    return (
        True,
        "pass → dist/%s.html（sha256=%s…）；零 CDN；载荷对照一致；双跑一致；篡改证伪检出"
        % (name, sha256_bytes(first_bytes)[:12]),
        sha256_bytes(first_bytes),
    )


def check_chart(chart, temp_root):
    """返回 (ok, message, hit_rule_ids, hit_gate_ids, seen_info_gate_ids)。"""
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
                set(),
            )
        if os.path.isdir(out_dir):
            return False, "exit 2 失败路径不得写产物", set(), set(), set()
        return True, "exit=2 零写入（规格合法性由解析层拦截）", set(), set(), set()

    expected_error_ids = list(chart["expected_errors"])
    rule_layer = bool(expected_error_ids) and set(expected_error_ids) <= RULE_IDS
    gate_layer = bool(expected_error_ids) and set(expected_error_ids) <= GATE_IDS
    if set(expected_error_ids) <= (RULE_IDS | GATE_IDS) and not (
        set(expected_error_ids) & RULE_IDS and set(expected_error_ids) & GATE_IDS
    ):
        pass  # 单一已接线层
    else:
        # 混层期望（规则 + 门禁同时植入）或未知 id：先按已接线层并集推导
        rule_layer = set(expected_error_ids) & RULE_IDS
        gate_layer = set(expected_error_ids) & GATE_IDS
    # K13-A 最终语义（M4 收紧后）：任一已接线审计层 blocked → exit 1
    expected_cli_exit = EXIT_FAILED if (rule_layer or gate_layer) else EXIT_OK
    if code != expected_cli_exit:
        return (
            False,
            "期望 exit %d（K13-A 推导），实际 %d（%s）"
            % (expected_cli_exit, code, stderr.strip()),
            set(),
            set(),
            set(),
        )

    provenance_path = os.path.join(out_dir, "provenance.json")
    if not os.path.isfile(provenance_path):
        return False, "缺少 provenance.json", set(), set(), set()
    with open(provenance_path, encoding="utf-8") as f:
        prov = json.load(f)

    # 基础不变量：id 唯一、每值 match
    ids = [record["rendered_value_id"] for record in prov["rendered_values"]]
    if len(ids) != len(set(ids)):
        return False, "rendered_value_id 重复", set(), set(), set()
    if any(record["match"] is not True for record in prov["rendered_values"]):
        return False, "存在 match != true 的记录", set(), set(), set()
    for record in prov["rendered_values"]:
        if record["csv_line"] != record["row_index"] + 2:
            return False, "csv_line != row_index + 2", set(), set(), set()
        if record["rendered_value_id"] != provenance.rendered_value_id(
            prov["spec_id"],
            record["mark_id"],
            record["series"],
            record["category"],
            record["row_index"],
            record["column"],
            record["transform_chain"],
        ):
            return False, "rendered_value_id 与字段重新计算不一致", set(), set(), set()

    if "injection" in chart:
        inject_g1(chart_id, prov)
        dataset, _, normalized = parse.run(csv_path, spec_path)
        report = provenance.validate(prov, dataset, normalized)
        if report["verdict"] != chart["expected_verdict"]:
            return False, "注入后 verdict=%r" % report["verdict"], set(), set(), set()
        if report["exit_code"] != chart["expected_exit"]:
            return False, "注入后 exit=%r" % report["exit_code"], set(), set(), set()
        gate_ids = [issue["gate_id"] for issue in report["errors"]]
        if gate_ids != chart["expected_errors"]:
            return False, "注入后 gate_id=%r" % gate_ids, set(), set(), set()
        return (
            True,
            "注入 %s → exit=%d" % (gate_ids[0], report["exit_code"]),
            set(),
            set(gate_ids),
            set(),
        )

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
            set(),
            set(),
        )
    for item in expected:
        key = (item["series"], item["category"], item["row_index"], item["column"])
        if key not in actual:
            return False, "缺少记录 %r" % (key,), set(), set(), set()
        record = actual[key]
        if record["raw_cell"] != item["raw_cell"]:
            return (
                False,
                "raw_cell 不符：%r != %r" % (record["raw_cell"], item["raw_cell"]),
                set(),
                set(),
                set(),
            )
        if record["rendered_label"] != item["label"]:
            return (
                False,
                "渲染值不符：%r != %r"
                % (record["rendered_label"], item["label"]),
                set(),
                set(),
                set(),
            )
        if record["recomputed_value"] != item["label"]:
            return (
                False,
                "重算值不符：%r != %r"
                % (record["recomputed_value"], item["label"]),
                set(),
                set(),
                set(),
            )

    # M3 规则层（audit.json 由交付态 CLI 写出）
    audit_path = os.path.join(out_dir, "audit.json")
    if not os.path.isfile(audit_path):
        return False, "缺少 audit.json", set(), set(), set()
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
            set(),
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
                set(),
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
                set(),
                set(),
            )
        return (
            True,
            "规则命中 %s → exit=1" % ",".join(blocking),
            blocking_ids,
            set(),
            set(),
        )

    if blocking:
        return (
            False,
            "非规则层图表不应有规则 ERROR：%s" % ",".join(blocking),
            blocking_ids,
            set(),
            set(),
        )

    # M4 窄缝门禁层（gates.json 由交付态 CLI 写出）
    gates_path = os.path.join(out_dir, "gates.json")
    if not os.path.isfile(gates_path):
        return False, "缺少 gates.json", set(), set(), set()
    with open(gates_path, encoding="utf-8") as f:
        gates_obj = json.load(f)
    gates_order = {
        level: index for index, level in enumerate(gates_obj["severity_order"])
    }
    gates_sort_keys = [
        (order_, finding["gate_id"], finding["evidence_path"])
        for order_, finding in zip(
            (gates_order[f["severity"]] for f in gates_obj["findings"]),
            gates_obj["findings"],
        )
    ]
    if gates_sort_keys != sorted(gates_sort_keys):
        return (
            False,
            "gates.json 排序不稳定（severity, gate_id, evidence_path）",
            set(),
            set(),
            set(),
        )
    gate_blocking = sorted(
        finding["gate_id"]
        for finding in gates_obj["findings"]
        if finding["severity"] == gates_obj["block_on"]
    )
    gate_info = sorted(
        finding["gate_id"]
        for finding in gates_obj["findings"]
        if finding["severity"] == gates_obj["severity_order"][-1]
    )

    # G2 期望统计逐值对照：truth 的 expected_stats 是生成期独立实算的对照基准，
    # 与 gates.json 内 g2.groups 的实算输出必须逐键一致（K21）。
    expected_stats = chart.get("expected_stats")
    if expected_stats is not None:
        groups = gates_obj["g2"]["groups"]
        if len(groups) != 1:
            return (
                False,
                "expected_stats 图应恰有一个分组，实际 %d" % len(groups),
                set(),
                set(),
                set(),
            )
        group = groups[0]
        for key in ("n", "n_below_min", "skewed", "multimodal", "g1", "bin_counts"):
            if group[key] != expected_stats[key]:
                return (
                    False,
                    "G2 stats[%s]=%r（期望 %r）"
                    % (key, group[key], expected_stats[key]),
                    set(),
                    set(),
                    set(),
                )

    if gates_obj["g1"]["verdict"] == "blocked":
        return (
            False,
            "无 G1 注入的真值图不应有溯源 ERROR：%s"
            % ",".join(gates_obj["g1"]["gate_ids"]),
            set(),
            set(gates_obj["g1"]["gate_ids"]),
            set(),
        )

    if gate_layer:
        if gates_obj["verdict"] != chart["expected_verdict"]:
            return (
                False,
                "门禁层 verdict=%r（期望 %r）"
                % (gates_obj["verdict"], chart["expected_verdict"]),
                set(),
                set(gate_blocking),
                set(),
            )
        missing = [
            gate_id for gate_id in expected_error_ids if gate_id not in gate_blocking
        ]
        if missing:
            return (
                False,
                "门禁未命中 %s（实际 %s）" % (missing, gate_blocking),
                set(),
                set(gate_blocking),
                set(),
            )
        return (
            True,
            "门禁命中 %s → exit=1" % ",".join(gate_blocking),
            set(),
            set(gate_blocking),
            set(),
        )

    if gate_blocking:
        return (
            False,
            "非门禁层图表不应有门禁 ERROR：%s" % ",".join(gate_blocking),
            set(),
            set(gate_blocking),
            set(),
        )
    expected_infos = list(chart["expected_infos"])
    if expected_infos:
        if gates_obj["verdict"] != "pass":
            return (
                False,
                "INFO 期望图应为 pass，实际 %r" % gates_obj["verdict"],
                set(),
                set(),
                set(),
            )
        if sorted(expected_infos) != gate_info:
            return (
                False,
                "INFO 未兑现 %s（实际 %s）" % (expected_infos, gate_info),
                set(),
                set(),
                set(gate_info),
            )
        return (
            True,
            "%d 个渲染值独立重算一致；INFO %s 已兑现（合规替代）"
            % (len(expected), ",".join(gate_info)),
            set(),
            set(),
            set(gate_info),
        )
    return (
        True,
        "%d 个渲染值独立重算一致；规则 0 命中" % len(expected),
        set(),
        set(),
        set(),
    )


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        print("用法：py -X utf8 tools/bench.py（无参数）", file=sys.stderr)
        return EXIT_USAGE
    truth = load_truth()
    temp_root = tempfile.mkdtemp(prefix="chartaudit-bench-")
    failures = []
    hit_rule_ids = set()
    hit_gate_ids = set()
    gate_info_seen = set()
    html_hashes = {}
    try:
        for chart in truth["charts"]:
            ok, message, hit_rule, hit_gate, seen_info = check_chart(
                chart, temp_root
            )
            status = "PASS" if ok else "FAIL"
            print("[%s] %-24s %s" % (status, chart["chart_id"], message))
            hit_rule_ids |= hit_rule
            hit_gate_ids |= hit_gate
            gate_info_seen |= seen_info
            if not ok:
                failures.append((chart["chart_id"], message))

        # M5 全链 build：29 张真值图逐一实跑发布门（独立于 check 路径）
        m5_failures = 0
        for chart in truth["charts"]:
            ok, message, html_sha = check_m5_build(chart, temp_root)
            status = "PASS" if ok else "FAIL"
            print("[%s] %-24s [M5] %s" % (status, chart["chart_id"], message))
            if html_sha is not None:
                html_hashes[chart["chart_id"]] = html_sha
            if not ok:
                m5_failures += 1
                failures.append((chart["chart_id"] + " [M5]", message))
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

    # M4 逐类覆盖：truth 里植入的门禁 id（含 INFO 合规替代）必须在 gates 中兑现
    planted_gate_ids = set()
    for chart in truth["charts"]:
        if "injection" in chart:
            planted_gate_ids |= set(chart["expected_errors"])
        elif chart["expected_errors"] and set(chart["expected_errors"]) <= GATE_IDS:
            planted_gate_ids |= set(chart["expected_errors"])
        elif chart["expected_infos"]:
            planted_gate_ids |= set(chart["expected_infos"])
    injected_gate_ids = {
        "G1_PROVENANCE_MISSING",
        "G1_PROVENANCE_MISMATCH",
        "G1_ROW_COLUMN_NOT_FOUND",
        "G1_HASH_MISMATCH",
    }
    gates_planted = planted_gate_ids - injected_gate_ids
    missing_gates = sorted(gates_planted - hit_gate_ids - set(gate_info_seen))
    print(
        "M4 门禁覆盖：%d/%d 类门禁检出（G2×2 形态 + G3 五反例 + INFO 合规替代；"
        "G1 四形态由注入路径检出）"
        % (
            len(gates_planted & (hit_gate_ids | set(gate_info_seen))),
            len(gates_planted),
        )
    )
    if missing_gates:
        print("M4 门禁覆盖失败：未检出 %s" % ", ".join(missing_gates), file=sys.stderr)

    total = len(truth["charts"])
    print(
        "M5 全链 build：%d/%d 图发布门达标（pass 图 HTML 哈希双跑一致；blocked 图默认零可发布 HTML；零 CDN 扫描门通过）"
        % (total - m5_failures, total)
    )
    published = len(html_hashes)
    print("M5 可发布产物：%d 张（双跑 sha256 断言覆盖）" % published)
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
