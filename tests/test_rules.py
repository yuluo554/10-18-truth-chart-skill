"""M3 规则门禁单元测试：配置唯一出处、零字面量扫描门、九条规则、排序、级别语义。

纪律：
- references/rules.json 是 rule_id / 严重级别 / 证据路径 / 阈值的唯一出处；
  本文件只"引用"规则 id（与 truth.json 同源），不定义第二份映射；
- K15：规格合法性（R009）由解析层 exit 2 拦截，规则层不二次改判；
- K16：扫描门 —— 引擎源码零 rule_id 字面量；rules.py 零级别字面量。
"""

import copy
import json
import os
import re

import pytest

from chartaudit import cli, parse, provenance, rules
from chartaudit.exitcodes import (
    EXIT_AUDIT_ERRORS,
    EXIT_CONFIG,
    EXIT_OK,
)
from chartaudit.serialize import dumps_json

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO_ROOT, "data", "synthetic")
GROUPS_CSV = os.path.join(DATA, "synthetic_groups.csv")
ERRORBARS_TSV = os.path.join(DATA, "synthetic_errorbars.tsv")
CLEAN_SPEC = os.path.join(DATA, "spec_clean_bar.json")

RULES_CFG = rules.load_rules()
BLOCK_ON = RULES_CFG["block_on"]


def run_audit(spec_name, data_name="synthetic_groups.csv", cfg=None):
    dataset, _, normalized = parse.run(
        os.path.join(DATA, data_name), os.path.join(DATA, spec_name)
    )
    prov = provenance.build(dataset, normalized)
    return rules.audit(dataset, normalized, prov, rules_cfg=cfg or RULES_CFG)


def blocking_ids(audit_obj):
    return {
        finding["rule_id"]
        for finding in audit_obj["findings"]
        if finding["severity"] == BLOCK_ON
    }


def write_config(tmp_path, config):
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# 规则包：唯一出处与枚举
# ---------------------------------------------------------------------------


def test_rules_config_is_single_source_of_truth():
    order = RULES_CFG["severity_order"]
    assert len(order) == len(set(order))
    assert set(order) == {"ERROR", "WARN", "INFO"}  # 口径 §13 唯一枚举
    assert BLOCK_ON in order
    entries = RULES_CFG["rules"]
    assert len(entries) == 9
    ids = [entry["rule_id"] for entry in entries]
    assert len(ids) == len(set(ids))
    checks = [entry["check"] for entry in entries]
    assert len(checks) == len(set(checks))
    for entry in entries:
        assert entry["severity"] in order
        assert entry["check"] in rules.CHECKERS
        assert entry["evidence_path"]
        assert entry["message"]
    assert RULES_CFG["alignment"].startswith("对齐已有工作")


def test_rule_ids_match_frozen_truth():
    with open(os.path.join(DATA, "truth.json"), encoding="utf-8") as f:
        truth = json.load(f)
    truth_rule_ids = {
        error
        for chart in truth["charts"]
        for error in chart["expected_errors"]
        if error.startswith("R")
    }
    config_ids = {entry["rule_id"] for entry in RULES_CFG["rules"]}
    assert truth_rule_ids == config_ids


def test_zero_rule_literal_scan_gate():
    """K16 扫描门：引擎源码不得含 rule_id 字面量；rules.py 不得含级别字符串字面量。

    级别在 Python 源码中只能以字符串字面量形式参与规则映射，故检查引号包裹形式；
    退出码常量名（如 EXIT_AUDIT_ERRORS）不是级别映射，不得被误伤。
    """
    package_dir = os.path.join(REPO_ROOT, "scripts", "chartaudit")
    rule_id_pattern = re.compile(r"R\d{3}_")
    for name in sorted(os.listdir(package_dir)):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(package_dir, name), encoding="utf-8") as f:
            source = f.read()
        assert not rule_id_pattern.search(source), "源码含 rule_id 字面量：%s" % name
    with open(os.path.join(package_dir, "rules.py"), encoding="utf-8") as f:
        rules_source = f.read()
    for level in RULES_CFG["severity_order"]:
        assert ('"%s"' % level) not in rules_source, "rules.py 含级别字面量：%s" % level
        assert ("'%s'" % level) not in rules_source, "rules.py 含级别字面量：%s" % level


# ---------------------------------------------------------------------------
# 九条规则：冻结图逐条命中（8 条审计层 + R009 解析层）
# ---------------------------------------------------------------------------


PLANTED_RULE_CASES = [
    ("spec_rule_baseline.json", "synthetic_groups.csv", "R001_BAR_NONZERO_BASELINE"),
    ("spec_rule_dual_y.json", "synthetic_groups.csv", "R002_DUAL_Y_AXIS"),
    ("spec_rule_pie.json", "synthetic_groups.csv", "R003_PIE_SECTORS_SUM"),
    ("spec_rule_3d.json", "synthetic_groups.csv", "R004_PSEUDO_3D"),
    ("spec_rule_radius.json", "synthetic_groups.csv", "R005_RADIUS_ENCODING"),
    ("spec_rule_smooth.json", "synthetic_groups.csv", "R006_SMOOTH_OVERSHOOT"),
    ("spec_rule_time_uneven.json", "synthetic_groups.csv", "R007_TIME_AXIS_UNEVEN"),
    ("spec_rule_contrast.json", "synthetic_groups.csv", "R008_LOW_CONTRAST"),
]


@pytest.mark.parametrize("spec_name,data_name,rule_id", PLANTED_RULE_CASES)
def test_each_audit_rule_hits_frozen_chart(spec_name, data_name, rule_id):
    audit_obj = run_audit(spec_name, data_name)
    assert rule_id in blocking_ids(audit_obj)
    assert audit_obj["verdict"] == "blocked"
    assert audit_obj["exit_code"] == EXIT_AUDIT_ERRORS
    assert audit_obj["render_allowed"] is False


def test_rule_nine_is_parse_layer_only():
    """K15：非法 mark → 解析层 exit 2；规则层不产生 R009 命中、不改判。"""
    with pytest.raises(parse.ParseError):
        parse.run(GROUPS_CSV, os.path.join(DATA, "spec_rule_invalid_mark.json"))
    audit_obj = run_audit("spec_clean_bar.json")
    assert "R009_SPEC_INVALID" not in {f["rule_id"] for f in audit_obj["findings"]}


PASS_CASES = [
    ("spec_clean_bar.json", "synthetic_groups.csv"),
    ("spec_scatter_identity.json", "synthetic_groups.csv"),
    ("spec_g2_uniform_ok.json", "synthetic_groups.csv"),
    ("spec_g2_scatter_alt.json", "synthetic_groups.csv"),
    ("spec_g2_box_alt.json", "synthetic_groups.csv"),
    ("spec_errorbar_sd.json", "synthetic_errorbars.tsv"),
    ("spec_errorbar_sem.json", "synthetic_errorbars.tsv"),
    ("spec_errorbar_ci.json", "synthetic_errorbars.tsv"),
    ("spec_errorbar_n.json", "synthetic_errorbars.tsv"),
]


@pytest.mark.parametrize("spec_name,data_name", PASS_CASES)
def test_pass_charts_have_no_rule_error(spec_name, data_name):
    audit_obj = run_audit(spec_name, data_name)
    assert blocking_ids(audit_obj) == set()
    assert audit_obj["verdict"] == "pass"
    assert audit_obj["exit_code"] == EXIT_OK
    assert audit_obj["render_allowed"] is True


# ---------------------------------------------------------------------------
# 排序与级别语义（K17 / 口径 §14）
# ---------------------------------------------------------------------------


def combo_spec(tmp_path):
    csv_path = tmp_path / "d.csv"
    csv_path.write_text("组别,产量\n甲组,1\n乙组,3\n", encoding="utf-8")
    spec = {
        "spec_id": "combo",
        "title": "合成示例：多规则组合",
        "mark": "pie",
        "encoding": {"x": {"field": "组别"}, "y": {"field": "产量", "decimals": 1}},
        "dual_y": True,
        "pseudo_3d": True,
        "size_channel": "radius",
        "low_contrast": True,
    }
    spec_path = tmp_path / "s.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    dataset, _, normalized = parse.run(str(csv_path), str(spec_path))
    return dataset, normalized, provenance.build(dataset, normalized)


def test_findings_sorted_by_severity_rule_evidence(tmp_path):
    dataset, normalized, prov = combo_spec(tmp_path)
    audit_obj = rules.audit(dataset, normalized, prov, rules_cfg=RULES_CFG)
    assert [f["rule_id"] for f in audit_obj["findings"]] == [
        "R002_DUAL_Y_AXIS",
        "R004_PSEUDO_3D",
        "R005_RADIUS_ENCODING",
        "R008_LOW_CONTRAST",
    ]
    assert {f["severity"] for f in audit_obj["findings"]} == {BLOCK_ON}


def test_severity_order_drives_sorting(tmp_path):
    mutated = copy.deepcopy(RULES_CFG)
    warn = mutated["severity_order"][1]
    for entry in mutated["rules"]:
        if entry["check"] == "low_contrast":
            entry["severity"] = warn
    dataset, normalized, prov = combo_spec(tmp_path)
    audit_obj = rules.audit(dataset, normalized, prov, rules_cfg=mutated)
    assert [f["rule_id"] for f in audit_obj["findings"]] == [
        "R002_DUAL_Y_AXIS",
        "R004_PSEUDO_3D",
        "R005_RADIUS_ENCODING",
        "R008_LOW_CONTRAST",
    ]
    assert [f["severity"] for f in audit_obj["findings"]] == [
        BLOCK_ON,
        BLOCK_ON,
        BLOCK_ON,
        warn,
    ]
    assert audit_obj["verdict"] == "blocked"  # 仍有阻断级命中


def test_registration_order_does_not_leak_into_output(tmp_path):
    """K17 排序契约：输出与规则包登记顺序无关（变异探活：去掉 audit 内排序必红）。"""
    mutated = copy.deepcopy(RULES_CFG)
    mutated["rules"].reverse()
    dataset, normalized, prov = combo_spec(tmp_path)
    audit_obj = rules.audit(dataset, normalized, prov, rules_cfg=mutated)
    assert [f["rule_id"] for f in audit_obj["findings"]] == [
        "R002_DUAL_Y_AXIS",
        "R004_PSEUDO_3D",
        "R005_RADIUS_ENCODING",
        "R008_LOW_CONTRAST",
    ]


def test_verdict_blocked_iff_blocking_level_present():
    # 对照：真实配置下 contrast 图 blocked；把唯一命中降为 WARN 后必须 pass（WARN 不阻断）
    blocked = run_audit("spec_rule_contrast.json")
    assert blocked["verdict"] == "blocked"
    assert blocked["exit_code"] == EXIT_AUDIT_ERRORS
    mutated = copy.deepcopy(RULES_CFG)
    warn = mutated["severity_order"][1]
    for entry in mutated["rules"]:
        if entry["check"] == "low_contrast":
            entry["severity"] = warn
    downgraded = run_audit("spec_rule_contrast.json", cfg=mutated)
    assert downgraded["findings"][0]["severity"] == warn
    assert downgraded["verdict"] == "pass"
    assert downgraded["exit_code"] == EXIT_OK
    assert downgraded["render_allowed"] is True


def test_pie_sector_threshold_comes_from_config(tmp_path):
    def pie_audit(groups, cfg=None):
        rows = ["组别,产量"] + ["G%d,%d" % (index, index + 1) for index in range(groups)]
        csv_path = tmp_path / ("d%d.csv" % groups)
        csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
        spec = {
            "spec_id": "pie%d" % groups,
            "title": "合成示例：扇区",
            "mark": "pie",
            "encoding": {"x": {"field": "组别"}, "y": {"field": "产量", "decimals": 1}},
        }
        spec_path = tmp_path / ("s%d.json" % groups)
        spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        dataset, _, normalized = parse.run(str(csv_path), str(spec_path))
        prov = provenance.build(dataset, normalized)
        return rules.audit(dataset, normalized, prov, rules_cfg=cfg or RULES_CFG)

    threshold = RULES_CFG["rules"][2]["thresholds"]["max_sectors"]
    over = pie_audit(threshold + 1)
    assert "R003_PIE_SECTORS_SUM" in blocking_ids(over)
    finding = [
        f for f in over["findings"] if f["rule_id"] == "R003_PIE_SECTORS_SUM"
    ][0]
    assert finding["evidence"]["sector_count"] == threshold + 1
    assert finding["evidence"]["max_sectors"] == threshold
    at_limit = pie_audit(threshold)
    assert "R003_PIE_SECTORS_SUM" not in blocking_ids(at_limit)


# ---------------------------------------------------------------------------
# 配置校验（缺失 / 非法 → RulesConfigError → exit 3）
# ---------------------------------------------------------------------------


def test_missing_rules_config_raises(tmp_path):
    with pytest.raises(rules.RulesConfigError):
        rules.load_rules(str(tmp_path / "nope.json"))


def test_invalid_severity_mapping_raises(tmp_path):
    broken = copy.deepcopy(RULES_CFG)
    broken["rules"][0]["severity"] = "FATAL"
    with pytest.raises(rules.RulesConfigError):
        rules.load_rules(write_config(tmp_path, broken))


def test_duplicate_rule_id_raises(tmp_path):
    broken = copy.deepcopy(RULES_CFG)
    broken["rules"][1]["rule_id"] = broken["rules"][0]["rule_id"]
    with pytest.raises(rules.RulesConfigError):
        rules.load_rules(write_config(tmp_path, broken))


def test_unknown_checker_raises(tmp_path):
    broken = copy.deepcopy(RULES_CFG)
    broken["rules"][0]["check"] = "no_such_check"
    with pytest.raises(rules.RulesConfigError):
        rules.load_rules(write_config(tmp_path, broken))


def test_missing_rule_entry_raises(tmp_path):
    """删一条规则 = 规则包不完整 → exit 3，绝不静默少检。"""
    broken = copy.deepcopy(RULES_CFG)
    broken["rules"].pop()
    with pytest.raises(rules.RulesConfigError):
        rules.load_rules(write_config(tmp_path, broken))


def test_missing_alignment_raises(tmp_path):
    broken = copy.deepcopy(RULES_CFG)
    del broken["alignment"]
    with pytest.raises(rules.RulesConfigError):
        rules.load_rules(write_config(tmp_path, broken))


def test_cli_exit_three_when_rules_pack_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        rules, "default_rules_path", lambda: str(tmp_path / "missing.json")
    )
    out = str(tmp_path / "out")
    assert cli.main(["check", GROUPS_CSV, CLEAN_SPEC, "--out", out]) == EXIT_CONFIG
    assert not os.path.exists(out)  # 配置失败零写入


# ---------------------------------------------------------------------------
# CLI 产物与确定性
# ---------------------------------------------------------------------------


def test_cli_writes_audit_json_and_exits_one_when_blocked(tmp_path):
    out = str(tmp_path / "out")
    assert (
        cli.main(
            [
                "check",
                GROUPS_CSV,
                os.path.join(DATA, "spec_rule_baseline.json"),
                "--out",
                out,
            ]
        )
        == EXIT_AUDIT_ERRORS
    )
    with open(os.path.join(out, "audit.json"), encoding="utf-8") as f:
        audit_obj = json.load(f)
    assert audit_obj["verdict"] == "blocked"
    assert audit_obj["alignment"].startswith("对齐已有工作")
    assert audit_obj["findings"][0]["rule_id"] == "R001_BAR_NONZERO_BASELINE"
    assert not [name for name in os.listdir(out) if name.endswith(".html")]


def test_cli_writes_audit_json_and_exits_zero_when_pass(tmp_path):
    out = str(tmp_path / "out")
    assert cli.main(["check", GROUPS_CSV, CLEAN_SPEC, "--out", out]) == EXIT_OK
    with open(os.path.join(out, "audit.json"), encoding="utf-8") as f:
        audit_obj = json.load(f)
    assert audit_obj["verdict"] == "pass"
    assert audit_obj["findings"] == []
    assert audit_obj["counts"]["total"] == 0
    assert audit_obj["render_allowed"] is True


def test_blocked_audit_is_byte_identical_across_runs(tmp_path):
    out_a = str(tmp_path / "a")
    out_b = str(tmp_path / "b")
    spec_path = os.path.join(DATA, "spec_rule_pie.json")
    assert cli.main(["check", GROUPS_CSV, spec_path, "--out", out_a]) == EXIT_AUDIT_ERRORS
    assert cli.main(["check", GROUPS_CSV, spec_path, "--out", out_b]) == EXIT_AUDIT_ERRORS
    for name in ("audit.json", "provenance.json", "dataset.json"):
        with open(os.path.join(out_a, name), "rb") as f:
            first = f.read()
        with open(os.path.join(out_b, name), "rb") as f:
            second = f.read()
        assert first == second, name


def test_audit_does_not_mutate_inputs():
    dataset, _, normalized = parse.run(
        GROUPS_CSV, os.path.join(DATA, "spec_rule_pie.json")
    )
    prov = provenance.build(dataset, normalized)
    dataset_before = copy.deepcopy(dataset)
    normalized_before = copy.deepcopy(normalized)
    prov_before = copy.deepcopy(prov)
    rules.audit(dataset, normalized, prov, rules_cfg=RULES_CFG)
    assert dataset == dataset_before
    assert normalized == normalized_before
    assert prov == prov_before


def test_audit_json_serialization_is_lf_and_sorted():
    audit_obj = run_audit("spec_rule_radius.json")
    raw = dumps_json(audit_obj)
    assert raw.endswith(b"\n")
    assert b"\r" not in raw
    text = raw.decode("utf-8")
    # 序列化单点：sort_keys=True → findings 内部键序字母序（detail/evidence 等）
    assert '"alignment"' in text and '"findings"' in text
