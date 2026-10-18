"""CLI 契约测试（M1 解析 + M2 溯源接线）：退出码 0/1/2/3 + 产物写出。"""

import json
import os

from chartaudit import cli, provenance
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
    for name in (
        "dataset.json",
        "diagnostics.json",
        "chart_spec.normalized.json",
        "provenance.json",
    ):
        assert os.path.isfile(os.path.join(out, name)), name
    with open(os.path.join(out, "dataset.json"), encoding="utf-8") as f:
        dataset = json.load(f)
    assert dataset["row_count"] == 21
    assert dataset["source"]["sha256"]
    with open(os.path.join(out, "provenance.json"), encoding="utf-8") as f:
        prov = json.load(f)
    assert prov["spec_id"] == "clean_bar"
    assert len(prov["rendered_values"]) == 1
    assert prov["rendered_values"][0]["match"] is True
    assert not [name for name in os.listdir(out) if name.endswith(".html")]


def test_check_writes_parse_artifacts(tmp_path):
    out = str(tmp_path / "check")
    assert cli.main(["check", GROUPS_CSV, CLEAN_SPEC, "--out", out]) == EXIT_OK
    assert os.path.isfile(os.path.join(out, "diagnostics.json"))
    assert os.path.isfile(os.path.join(out, "provenance.json"))


def test_build_is_byte_identical_across_runs(tmp_path):
    out_a = str(tmp_path / "a")
    out_b = str(tmp_path / "b")
    assert cli.main(["build", GROUPS_CSV, CLEAN_SPEC, "--out", out_a]) == EXIT_OK
    assert cli.main(["build", GROUPS_CSV, CLEAN_SPEC, "--out", out_b]) == EXIT_OK
    names = sorted(os.listdir(out_a))
    assert names == sorted(os.listdir(out_b))
    for name in names:
        with open(os.path.join(out_a, name), "rb") as f:
            first = f.read()
        with open(os.path.join(out_b, name), "rb") as f:
            second = f.read()
        assert first == second, name


def test_cli_returns_audit_error_when_provenance_blocked(tmp_path, monkeypatch):
    real_build = provenance.build

    def broken_build(dataset, normalized_spec):
        prov = real_build(dataset, normalized_spec)
        prov["rendered_values"].pop()  # G1_PROVENANCE_MISSING
        return prov

    monkeypatch.setattr(cli.provenance, "build", broken_build)
    out = str(tmp_path / "blocked")
    assert cli.main(["check", GROUPS_CSV, CLEAN_SPEC, "--out", out]) == EXIT_AUDIT_ERRORS
    assert os.path.isfile(os.path.join(out, "provenance.json"))
    assert not [name for name in os.listdir(out) if name.endswith(".html")]


def test_cli_returns_usage_error_when_transform_rejected(tmp_path, monkeypatch):
    def broken_build(dataset, normalized_spec):
        raise provenance.ProvenanceError("变换不在白名单")

    monkeypatch.setattr(cli.provenance, "build", broken_build)
    out = str(tmp_path / "usage")
    assert cli.main(["check", GROUPS_CSV, CLEAN_SPEC, "--out", out]) == EXIT_USAGE
    assert not os.path.exists(out)  # 失败路径零写入


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
