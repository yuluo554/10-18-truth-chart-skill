"""chartaudit CLI 入口。

子命令：
    build <csv> <spec.json> --out <dir> [--emit-audit-html]   全链：解析→溯源→门禁→渲染（发布门）
    check <csv> <spec.json> --out <dir>                       只跑审计不渲染
    selftest                                                  门禁自检

退出码：见 exitcodes.py（唯一语义）。

发布门（D10 / K27，口径 §15）：
- 三层（溯源 / 规则 / 门禁）任一 blocked → exit 1；默认**不写**可发布
  `dist/<name>.html`；仅显式 `--emit-audit-html` 时写 `<name>.audit.html`
  （带阻断横幅的审计调试件，不得冒充发布产物），退出码仍为 1；
- 无 ERROR → 写 `dist/<name>.html`（同内容亦可于 --out 复查），exit 0；
- 配置缺失 / 非法（规则包 / 门禁包 / 别名表 / 几何包）→ exit 3 且零写入。
"""

import argparse
import os
import sys

from . import gates, parse, provenance, render, rules
from . import __version__
from .exitcodes import (
    EXIT_AUDIT_ERRORS,
    EXIT_CONFIG,
    EXIT_OK,
    EXIT_USAGE,
    ensure_utf8_stdio,
)
from .serialize import dumps_json, write_atomic


def build_parser():
    parser = argparse.ArgumentParser(
        prog="chartaudit",
        description="CSV → 单文件 HTML 图表 + 机器可读诚信审计报告（逐值溯源 / 样本量门禁 / 误差棒来源真实性）",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="chartaudit %s" % __version__,
        help="打印版本并退出",
    )
    sub = parser.add_subparsers(dest="command")

    p_build = sub.add_parser("build", help="全链：解析→溯源→门禁→渲染（发布门）")
    p_build.add_argument("csv", help="输入 CSV/TSV（UTF-8）")
    p_build.add_argument("spec", help="图表规格 JSON")
    p_build.add_argument("--out", required=True, help="审计 JSON 输出目录")
    p_build.add_argument(
        "--emit-audit-html",
        action="store_true",
        help="存在 ERROR 时额外写出阻断标记调试件 <name>.audit.html（退出码仍非 0）",
    )

    p_check = sub.add_parser("check", help="只跑审计，不渲染 HTML")
    p_check.add_argument("csv", help="输入 CSV/TSV（UTF-8）")
    p_check.add_argument("spec", help="图表规格 JSON")
    p_check.add_argument("--out", required=True, help="审计 JSON 输出目录")

    sub.add_parser("selftest", help="门禁自检")

    return parser


def _write_outputs(out_dir, dataset, diagnostics, normalized_spec, provenance_obj):
    write_atomic(os.path.join(out_dir, "dataset.json"), dumps_json(dataset))
    write_atomic(os.path.join(out_dir, "diagnostics.json"), dumps_json(diagnostics))
    write_atomic(
        os.path.join(out_dir, "chart_spec.normalized.json"),
        dumps_json(normalized_spec),
    )
    write_atomic(
        os.path.join(out_dir, "provenance.json"), dumps_json(provenance_obj)
    )


def _load_configs():
    """配置先行加载：规则包 / 门禁包 / 别名表 / 几何包；任一缺失非法 → exit 3 零写入。"""
    rules_cfg = rules.load_rules()
    gates_cfg = gates.load_gates(rules_cfg=rules_cfg)
    aliases_cfg = gates.load_aliases()
    geometry_cfg = render.load_geometry()
    return rules_cfg, gates_cfg, aliases_cfg, geometry_cfg


def _publish_gate(
    args,
    normalized_spec,
    provenance_obj,
    provenance_report,
    audit_obj,
    gates_obj,
    geometry_cfg,
    blocked,
):
    """发布门（K27）：默认只写 dist/<name>.html（无 ERROR）；阻断时默认零可发布 HTML。"""
    name = render.output_name(normalized_spec["spec_id"])
    dist_dir = os.path.join(os.path.abspath(args.out), "dist")
    if not blocked:
        html_text = render.render_html(
            dataset=None,
            normalized_spec=normalized_spec,
            provenance_obj=provenance_obj,
            provenance_report=provenance_report,
            audit_obj=audit_obj,
            gates_obj=gates_obj,
            geometry_cfg=geometry_cfg,
            blocked=False,
            audit_debug=False,
        )
        write_atomic(os.path.join(dist_dir, "%s.html" % name), html_text)
        return os.path.join(dist_dir, "%s.html" % name)
    if getattr(args, "emit_audit_html", False):
        html_text = render.render_html(
            dataset=None,
            normalized_spec=normalized_spec,
            provenance_obj=provenance_obj,
            provenance_report=provenance_report,
            audit_obj=audit_obj,
            gates_obj=gates_obj,
            geometry_cfg=geometry_cfg,
            blocked=True,
            audit_debug=True,
        )
        path = os.path.join(dist_dir, "%s.audit.html" % name)
        write_atomic(path, html_text)
        return path
    return None


def _run_pipeline(args):
    # 配置先行加载：缺失 / 非法 → exit 3 且零写入（不得静默零规则 / 零门禁通过）
    try:
        rules_cfg, gates_cfg, aliases_cfg, geometry_cfg = _load_configs()
    except (
        rules.RulesConfigError,
        gates.GatesConfigError,
        render.GeometryConfigError,
    ) as exc:
        print("配置错误（退出码 3）：%s" % exc, file=sys.stderr)
        return EXIT_CONFIG
    try:
        dataset, diagnostics, normalized_spec = parse.run(args.csv, args.spec)
        provenance_obj = provenance.build(dataset, normalized_spec)
    except (parse.ParseError, provenance.ProvenanceError) as exc:
        print("输入/规格错误：%s" % exc, file=sys.stderr)
        return EXIT_USAGE
    _write_outputs(args.out, dataset, diagnostics, normalized_spec, provenance_obj)
    report = provenance.validate(provenance_obj, dataset, normalized_spec)
    try:
        audit_obj = rules.audit(
            dataset, normalized_spec, provenance_obj, rules_cfg=rules_cfg
        )
        gates_obj = gates.audit(
            dataset,
            normalized_spec,
            provenance_obj,
            gates_cfg=gates_cfg,
            aliases_cfg=aliases_cfg,
            provenance_report=report,
            rules_cfg=rules_cfg,
        )
    except (rules.RulesConfigError, gates.GatesConfigError) as exc:
        print("配置错误（退出码 3）：%s" % exc, file=sys.stderr)
        return EXIT_CONFIG
    write_atomic(os.path.join(args.out, "audit.json"), dumps_json(audit_obj))
    write_atomic(os.path.join(args.out, "gates.json"), dumps_json(gates_obj))

    for issue in report["errors"][:10]:
        print(
            "溯源 ERROR：%s（%s）%s"
            % (issue["gate_id"], issue["evidence_path"], issue["detail"]),
            file=sys.stderr,
        )
    if report["verdict"] == "blocked":
        print(
            "溯源校验阻断：%d 项 ERROR / %d 个渲染值"
            % (report["error_count"], report["checked_count"]),
            file=sys.stderr,
        )

    counts_text = " / ".join(
        "%s %d" % (level, audit_obj["counts"][level])
        for level in audit_obj["severity_order"]
    )
    if audit_obj["verdict"] == "blocked":
        for finding in audit_obj["findings"]:
            if finding["severity"] == audit_obj["block_on"]:
                print(
                    "规则 %s（%s）%s"
                    % (
                        finding["rule_id"],
                        finding["evidence_path"],
                        finding["message"],
                    ),
                    file=sys.stderr,
                )
        print(
            "规则审计阻断：命中 %d 项（%s）；%s"
            % (len(audit_obj["findings"]), counts_text, audit_obj["alignment"]),
            file=sys.stderr,
        )

    gate_counts_text = " / ".join(
        "%s %d" % (level, gates_obj["counts"][level])
        for level in gates_obj["severity_order"]
    )
    if gates_obj["verdict"] == "blocked":
        for finding in gates_obj["findings"]:
            if finding["severity"] == gates_obj["block_on"]:
                print(
                    "门禁 %s（%s）%s"
                    % (
                        finding["gate_id"],
                        finding["evidence_path"],
                        finding["message"],
                    ),
                    file=sys.stderr,
                )
        if gates_obj["g1"]["verdict"] == "blocked":
            print(
                "溯源门禁阻断：%s"
                % ", ".join(gates_obj["g1"]["gate_ids"]),
                file=sys.stderr,
            )
        print(
            "窄缝门禁阻断：%s；默认不渲染 HTML" % gate_counts_text,
            file=sys.stderr,
        )

    blocked = (
        report["verdict"] == "blocked"
        or audit_obj["verdict"] == "blocked"
        or gates_obj["verdict"] == "blocked"
    )

    # 发布门（仅 build；check 永不写 HTML）
    if args.command == "build":
        published = _publish_gate(
            args,
            normalized_spec,
            provenance_obj,
            report,
            audit_obj,
            gates_obj,
            geometry_cfg,
            blocked,
        )
        if published is not None:
            print("渲染完成：%s" % published)
    if blocked:
        return EXIT_AUDIT_ERRORS

    print(
        "解析完成：%d 行 × %d 列（delimiter=%r，诊断项 %d）→ %s"
        % (
            dataset["row_count"],
            len(dataset["header"]),
            dataset["delimiter"],
            diagnostics["issue_count"],
            args.out,
        )
    )
    print(
        "溯源完成：%d 个渲染值，全部 match 且逐值可回溯 → %s"
        % (report["checked_count"], os.path.join(args.out, "provenance.json"))
    )
    print(
        "规则审计完成：命中 %d 项（%s）→ %s"
        % (
            len(audit_obj["findings"]),
            counts_text,
            os.path.join(args.out, "audit.json"),
        )
    )
    print(
        "窄缝门禁完成：命中 %d 项（%s）→ %s"
        % (
            len(gates_obj["findings"]),
            gate_counts_text,
            os.path.join(args.out, "gates.json"),
        )
    )
    return EXIT_OK


def _selftest():
    """内部不变量自检：退出码语义唯一、序列化字节契约、类型推断顺序、规则包可加载。"""
    from . import exitcodes

    problems = []
    codes = (exitcodes.EXIT_OK, exitcodes.EXIT_AUDIT_ERRORS, exitcodes.EXIT_USAGE, exitcodes.EXIT_CONFIG)
    if codes != (0, 1, 2, 3) or len(set(codes)) != 4:
        problems.append("退出码契约不是 0/1/2/3")
    sample = {"b": 1, "a": "中"}
    raw = dumps_json(sample)
    if not raw.endswith(b"\n") or b"\r" in raw or raw.decode("utf-8").index('"a"') > raw.decode("utf-8").index('"b"'):
        problems.append("序列化字节契约不符")
    if parse.infer_cell_type("10") != "integer" or parse.infer_cell_type("1.5") != "decimal":
        problems.append("类型推断顺序不符")
    if parse.infer_cell_type("2026-01-01") != "date":
        problems.append("日期推断不符")
    rules_cfg = None
    try:
        rules_cfg = rules.load_rules()
        rule_ids = [entry["rule_id"] for entry in rules_cfg["rules"]]
        if len(rule_ids) != len(set(rule_ids)):
            problems.append("规则包 rule_id 不唯一")
        if rules_cfg["block_on"] not in rules_cfg["severity_order"]:
            problems.append("规则包 block_on 不在 severity_order 内")
    except rules.RulesConfigError as exc:
        problems.append("规则包不可加载：%s" % exc)
    if rules_cfg is not None:
        try:
            gates_cfg = gates.load_gates(rules_cfg=rules_cfg)
            gates.load_aliases()
            gate_ids = [entry["gate_id"] for entry in gates_cfg["gates"]]
            if len(gate_ids) != len(set(gate_ids)):
                problems.append("门禁包 gate_id 不唯一")
        except (rules.RulesConfigError, gates.GatesConfigError) as exc:
            problems.append("门禁包不可加载：%s" % exc)
    try:
        geometry_cfg = render.load_geometry()
        values = geometry_cfg["values"]
        if set(values) != set(render.GEOMETRY_KEYS):
            problems.append("几何包键集合与 render.GEOMETRY_KEYS 不一致")
    except render.GeometryConfigError as exc:
        problems.append("几何包不可加载：%s" % exc)
    if problems:
        for problem in problems:
            print("selftest 失败：%s" % problem, file=sys.stderr)
        return EXIT_AUDIT_ERRORS
    print("selftest 通过：退出码 / 序列化 / 类型推断 / 规则包 / 门禁包 / 几何包不变量一致")
    return EXIT_OK


def main(argv=None):
    ensure_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_usage(sys.stderr)
        return EXIT_USAGE  # 统一入口返回码而非 SystemExit，防契约漂移

    if args.command == "build":
        return _run_pipeline(args)
    if args.command == "check":
        return _run_pipeline(args)
    if args.command == "selftest":
        return _selftest()
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
