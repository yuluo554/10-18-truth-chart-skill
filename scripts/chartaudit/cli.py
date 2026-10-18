"""chartaudit CLI 入口。

子命令：
    build <csv> <spec.json> --out <dir>   交付态全链入口（M1–M5 逐棒接线）
    check <csv> <spec.json> --out <dir>   只跑审计不渲染
    selftest                              门禁自检

退出码：见 exitcodes.py（唯一语义）。
M1 已接线解析层；M2 接线溯源层并产出 provenance.json。溯源校验出现 ERROR 时
返回 1 且不进入渲染（M5 渲染器接线后由 render_allowed 强制）。
"""

import argparse
import os
import sys

from . import parse, provenance
from .exitcodes import (
    EXIT_AUDIT_ERRORS,
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
    sub = parser.add_subparsers(dest="command")

    p_build = sub.add_parser("build", help="全链：解析→溯源→门禁→渲染")
    p_build.add_argument("csv", help="输入 CSV/TSV（UTF-8）")
    p_build.add_argument("spec", help="图表规格 JSON")
    p_build.add_argument("--out", required=True, help="输出目录")
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


def _run_pipeline(args):
    try:
        dataset, diagnostics, normalized_spec = parse.run(args.csv, args.spec)
        provenance_obj = provenance.build(dataset, normalized_spec)
    except (parse.ParseError, provenance.ProvenanceError) as exc:
        print("输入/规格错误：%s" % exc, file=sys.stderr)
        return EXIT_USAGE
    _write_outputs(args.out, dataset, diagnostics, normalized_spec, provenance_obj)
    report = provenance.validate(provenance_obj, dataset, normalized_spec)
    if report["verdict"] == "blocked":
        for issue in report["errors"][:10]:
            print(
                "溯源 ERROR：%s（%s）%s"
                % (issue["gate_id"], issue["evidence_path"], issue["detail"]),
                file=sys.stderr,
            )
        print(
            "溯源校验阻断：%d 项 ERROR / %d 个渲染值；默认不渲染 HTML"
            % (report["error_count"], report["checked_count"]),
            file=sys.stderr,
        )
        return report["exit_code"]
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
    return EXIT_OK


def _selftest():
    """内部不变量自检：退出码语义唯一、序列化字节契约、类型推断顺序。"""
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
    if problems:
        for problem in problems:
            print("selftest 失败：%s" % problem, file=sys.stderr)
        return EXIT_AUDIT_ERRORS
    print("selftest 通过：退出码 / 序列化 / 类型推断不变量一致")
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
