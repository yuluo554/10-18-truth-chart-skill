"""chartaudit CLI 入口。

子命令：
    build <csv> <spec.json> --out <dir>   交付态全链入口（M1–M5 逐棒接线）
    check <csv> <spec.json>               只跑审计不渲染
    selftest                              门禁自检

退出码：见 exitcodes.py（唯一语义）。
骨架期未接线的子命令以 EXIT_NOT_READY（4）显式拦截，不伪造空结果。
"""

import argparse
import sys

from .exitcodes import (
    EXIT_NOT_READY,
    EXIT_OK,
    EXIT_USAGE,
    ensure_utf8_stdio,
)


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


def main(argv=None):
    ensure_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_usage(sys.stderr)
        return EXIT_USAGE  # 统一入口返回码而非 SystemExit，防契约漂移

    if args.command == "build":
        # 骨架期：M1–M5 未接线，显式拦截（不伪造产物）
        print("build: 阶段未就绪（M1–M5 未接线，见 plan/05）", file=sys.stderr)
        return EXIT_NOT_READY
    if args.command == "check":
        print("check: 阶段未就绪（M1–M5 未接线，见 plan/05）", file=sys.stderr)
        return EXIT_NOT_READY
    if args.command == "selftest":
        print("selftest: 阶段未就绪（门禁未接线）", file=sys.stderr)
        return EXIT_NOT_READY
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
