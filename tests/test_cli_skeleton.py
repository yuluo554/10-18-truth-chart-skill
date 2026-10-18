"""CLI 契约测试（M1 接线后）：退出码 0/1/2/3 + 解析产物写出。"""

import json
import os

from chartaudit import cli
from chartaudit.exitcodes import EXIT_AUDIT_ERRORS, EXIT_CONFIG, EXIT_OK, EXIT_USAGE

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO_ROOT, "data", "synthetic")
GROUPS_CSV = os.path.join(DATA, "synthetic_groups.csv")
CLEAN_SPEC = os.path.join(DATA, "spec_clean_bar.json")


def test_no_args_is_usage_error():
    # 无子命令：不抛 SystemExit，统一返回用法错误码（契约统一入口，防 2/1 漂移）
    assert cli.main([]) == EXIT_USAGE


def test_exit_code_contract_constants():
    """口径 §15 四语义，常量值锁死；骨架期 exit 4 已退役。"""
    assert (EXIT_OK, EXIT_AUDIT_ERRORS, EXIT_USAGE, EXIT_CONFIG) == (0, 1, 2, 3)
    import chartaudit.exitcodes as exitcodes

    assert not hasattr(exitcodes, "EXIT_NOT_READY")


def test_build_writes_parse_artifacts(tmp_path):
    out = str(tmp_path / "out")
    assert cli.main(["build", GROUPS_CSV, CLEAN_SPEC, "--out", out]) == EXIT_OK
    for name in ("dataset.json", "diagnostics.json", "chart_spec.normalized.json"):
        assert os.path.isfile(os.path.join(out, name)), name
    with open(os.path.join(out, "dataset.json"), encoding="utf-8") as f:
        dataset = json.load(f)
    assert dataset["row_count"] == 21
    assert dataset["source"]["sha256"]


def test_check_writes_parse_artifacts(tmp_path):
    out = str(tmp_path / "check")
    assert cli.main(["check", GROUPS_CSV, CLEAN_SPEC, "--out", out]) == EXIT_OK
    assert os.path.isfile(os.path.join(out, "diagnostics.json"))


def test_missing_input_is_usage_error(tmp_path):
    assert (
        cli.main(
            ["check", str(tmp_path / "nope.csv"), CLEAN_SPEC, "--out", str(tmp_path / "o")]
        )
        == EXIT_USAGE
    )


def test_unknown_spec_field_is_usage_error(tmp_path):
    with open(CLEAN_SPEC, encoding="utf-8") as f:
        spec = json.load(f)
    spec["unexpected_field"] = 1
    bad = tmp_path / "bad_spec.json"
    bad.write_text(json.dumps(spec), encoding="utf-8")
    assert (
        cli.main(["check", GROUPS_CSV, str(bad), "--out", str(tmp_path / "o")])
        == EXIT_USAGE
    )
    # 失败路径零写入
    assert not os.path.exists(str(tmp_path / "o"))


def test_invalid_mark_is_usage_error(tmp_path):
    # truth 中 rule_invalid_mark 的期望退出码为 2，由此处锁定
    assert (
        cli.main(
            [
                "check",
                GROUPS_CSV,
                os.path.join(DATA, "spec_rule_invalid_mark.json"),
                "--out",
                str(tmp_path / "o"),
            ]
        )
        == EXIT_USAGE
    )


def test_selftest_passes():
    assert cli.main(["selftest"]) == EXIT_OK
