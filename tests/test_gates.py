"""M4 窄缝门禁测试：配置唯一出处、零字面量扫描门、G1/G2/G3 判定、排序与 verdict。

纪律：
- references/gates.json 是 gate_id / 级别 / 证据路径 / 阈值的唯一出处；
  references/aliases.json 是误差棒列名别名与大小写规则的唯一出处（K24）；
  本文件只"引用"gate id（与 truth.json 同源），不定义第二份映射；
- K19：G1 判定只由 provenance.validate 给出（gates.g1 只引用）；
- K20：G2/G3 阈值零代码字面量（truth.json 的 n_min 是期望不是配置）；
- K23：gates 与 rules 两层各自出 JSON，最终退出码取两层 ERROR 并集。
"""

import copy
import json
import os

import pytest

from chartaudit import cli, gates, parse, provenance, rules
from chartaudit.exitcodes import EXIT_AUDIT_ERRORS, EXIT_CONFIG, EXIT_OK
from chartaudit.serialize import dumps_json

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO_ROOT, "data", "synthetic")
GROUPS_CSV = os.path.join(DATA, "synthetic_groups.csv")
ERRORBARS_TSV = os.path.join(DATA, "synthetic_errorbars.tsv")
CLEAN_SPEC = os.path.join(DATA, "spec_clean_bar.json")

RULES_CFG = rules.load_rules()
GATES_CFG = gates.load_gates(rules_cfg=RULES_CFG)
ALIASES_CFG = gates.load_aliases()
BLOCK_ON = RULES_CFG["block_on"]


def load_truth():
    with open(os.path.join(DATA, "truth.json"), encoding="utf-8") as f:
        return json.load(f)


def run_gates(spec_name, data_name="synthetic_groups.csv", gates_cfg=None,
              aliases_cfg=None):
    dataset, _, normalized = parse.run(
        os.path.join(DATA, data_name), os.path.join(DATA, spec_name)
    )
    prov = provenance.build(dataset, normalized)
    report = provenance.validate(prov, dataset, normalized)
    obj = gates.audit(
        dataset,
        normalized,
        prov,
        gates_cfg=gates_cfg or GATES_CFG,
        aliases_cfg=aliases_cfg or ALIASES_CFG,
        provenance_report=report,
        rules_cfg=RULES_CFG,
    )
    return obj


def blocking_gate_ids(gates_obj):
    return {
        finding["gate_id"]
        for finding in gates_obj["findings"]
        if finding["severity"] == BLOCK_ON
    }


def info_gate_ids(gates_obj):
    info_level = gates_obj["severity_order"][-1]
    return {
        finding["gate_id"]
        for finding in gates_obj["findings"]
        if finding["severity"] == info_level
    }


def write_config(tmp_path, config, name="gates.json"):
    path = tmp_path / name
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# 门禁包 / 别名表：唯一出处与枚举
# ---------------------------------------------------------------------------


def test_gates_config_is_single_source_of_truth():
    order = RULES_CFG["severity_order"]
    assert set(order) == {"ERROR", "WARN", "INFO"}  # 口径 §13 唯一枚举（复用规则包）
    entries = GATES_CFG["gates"]
    assert len(entries) >= 12
    ids = [entry["gate_id"] for entry in entries]
    assert len(ids) == len(set(ids))
    checks = [entry["check"] for entry in entries]
    assert len(checks) == len(set(checks))
    for entry in entries:
        severity = entry["severity"]
        if isinstance(severity, str):
            assert severity in order
        else:
            for value in severity.values():
                assert value in order
        assert entry["evidence_path"]
        assert entry["message"]
    truth_gate_ids = {
        error
        for chart in load_truth()["charts"]
        for error in chart["expected_errors"] + chart["expected_infos"]
        if error.startswith("G")
    }
    injected = {
        "G1_PROVENANCE_MISSING",
        "G1_PROVENANCE_MISMATCH",
        "G1_ROW_COLUMN_NOT_FOUND",
        "G1_HASH_MISMATCH",
    }
    # truth 植入的非注入门禁 id 必须全部登记在门禁包里（G1 四形态由 M2 判定提供）
    assert truth_gate_ids - injected <= set(ids)


def test_n_min_only_in_config_not_from_truth():
    """K20：运行时阈值只来自 references/gates.json，与 truth.json 的 n_min 是两回事。"""
    truth = load_truth()
    thresholds = GATES_CFG["thresholds"]
    assert thresholds["n_min"] == truth["n_min"] == 5  # 数值一致但出处不同
    gates_obj = run_gates("spec_clean_bar.json")
    assert "thresholds" not in gates_obj  # gates.json 不回显配置


def test_zero_gate_literal_scan_gate():
    """K16 扫描门（M4 扩展）：gates.py / cli.py / rules.py 零 gate_id 与级别字面量。

    provenance.py 的 G1 gate_id 字符串是 M2 既有判定语义的产出位（唯一出处），
    不在 M4 扫描范围内——M4 只新增"不写第二份判定"的约束（K19）。
    """
    import re

    package_dir = os.path.join(REPO_ROOT, "scripts", "chartaudit")
    gate_id_pattern = re.compile(r"G[123]_[A-Z]")
    for name in ("gates.py", "cli.py", "rules.py"):
        with open(os.path.join(package_dir, name), encoding="utf-8") as f:
            source = f.read()
        assert not gate_id_pattern.search(source), "源码含 gate_id 字面量：%s" % name
    with open(os.path.join(package_dir, "gates.py"), encoding="utf-8") as f:
        gates_source = f.read()
    for level in RULES_CFG["severity_order"]:
        assert ('"%s"' % level) not in gates_source, "gates.py 含级别字面量：%s" % level
        assert ("'%s'" % level) not in gates_source, "gates.py 含级别字面量：%s" % level


# ---------------------------------------------------------------------------
# G1：判定只出自 provenance.validate（K19）
# ---------------------------------------------------------------------------


def test_g1_reuses_provenance_validate_not_second_judgment(tmp_path, monkeypatch):
    real_build = provenance.build

    def broken_build(dataset, normalized_spec):
        prov = real_build(dataset, normalized_spec)
        prov["source"]["sha256"] = "0" * 64  # G1_HASH_MISMATCH
        return prov

    monkeypatch.setattr(provenance, "build", broken_build)
    out = str(tmp_path / "out")
    assert cli.main(["check", GROUPS_CSV, CLEAN_SPEC, "--out", out]) == EXIT_AUDIT_ERRORS
    with open(os.path.join(out, "gates.json"), encoding="utf-8") as f:
        gates_obj = json.load(f)
    assert gates_obj["g1"]["verdict"] == "blocked"
    assert gates_obj["g1"]["gate_ids"] == ["G1_HASH_MISMATCH"]
    assert gates_obj["verdict"] == "blocked"
    assert gates_obj["exit_code"] == EXIT_AUDIT_ERRORS
    # g1 的 gate_ids 只引用 validate 的结果，findings 里不重复登记第二份判定
    assert not [f for f in gates_obj["findings"] if f["gate_id"].startswith("G1")]


def test_g1_blocked_counts_toward_final_exit(tmp_path, monkeypatch):
    real_build = provenance.build

    def broken_build(dataset, normalized_spec):
        prov = real_build(dataset, normalized_spec)
        prov["rendered_values"].pop()  # G1_PROVENANCE_MISSING
        return prov

    monkeypatch.setattr(provenance, "build", broken_build)
    out = str(tmp_path / "out")
    assert cli.main(["check", GROUPS_CSV, CLEAN_SPEC, "--out", out]) == EXIT_AUDIT_ERRORS
    with open(os.path.join(out, "gates.json"), encoding="utf-8") as f:
        gates_obj = json.load(f)
    assert gates_obj["counts"][BLOCK_ON] >= 1
    assert gates_obj["render_allowed"] is False


# ---------------------------------------------------------------------------
# G2：truth 逐图 + expected_stats 逐值对照（K21）
# ---------------------------------------------------------------------------


G2_CASES = [
    ("spec_g2_skewed.json", "blocked", ["G2_SMALL_N_MEAN_BAR"]),
    ("spec_g2_bimodal.json", "blocked", ["G2_SMALL_N_MEAN_BAR"]),
    ("spec_g2_uniform_ok.json", "pass", []),
]


@pytest.mark.parametrize("spec_name,expected_verdict,expected_errors", G2_CASES)
def test_g2_truth_charts(spec_name, expected_verdict, expected_errors):
    obj = run_gates(spec_name)
    assert obj["verdict"] == expected_verdict
    assert sorted(blocking_gate_ids(obj)) == sorted(expected_errors)


def test_g2_compliant_alternatives_are_info():
    truth = load_truth()
    for chart_id in ("g2_scatter_alt", "g2_box_alt"):
        chart = next(c for c in truth["charts"] if c["chart_id"] == chart_id)
        obj = run_gates(chart["spec"])
        assert obj["verdict"] == "pass"
        assert info_gate_ids(obj) == set(chart["expected_infos"])
        assert blocking_gate_ids(obj) == set()


def test_g2_expected_stats_match_value_by_value():
    truth = load_truth()
    for chart in truth["charts"]:
        stats = chart.get("expected_stats")
        if stats is None:
            continue
        obj = run_gates(chart["spec"])
        groups = obj["g2"]["groups"]
        assert len(groups) == 1, chart["chart_id"]
        group = groups[0]
        for key in ("n", "n_below_min", "skewed", "multimodal", "g1", "bin_counts"):
            assert group[key] == stats[key], (chart["chart_id"], key)


def test_g2_threshold_comes_from_config(tmp_path):
    """变异探活锚点：阈值改动必须改变判定结果（配置生效，非代码常量）。

    - n_min 调大后均匀小样本图的 n_below_min 翻转（状态推导仍按口径 §9）；
    - multimodal_min_count_floor 调小后均匀图的直方图判为多峰 → 阻断；
    - skew_abs_threshold 调大后乙组不再判偏斜 → 通过。
    """
    mutated = copy.deepcopy(GATES_CFG)
    mutated["thresholds"]["n_min"] = 100
    obj = run_gates("spec_g2_uniform_ok.json", gates_cfg=mutated)
    assert obj["g2"]["groups"][0]["n_below_min"] is True

    mutated2 = copy.deepcopy(GATES_CFG)
    mutated2["thresholds"]["multimodal_min_count_floor"] = 1
    obj2 = run_gates("spec_g2_uniform_ok.json", gates_cfg=mutated2)
    assert obj2["verdict"] == "blocked"
    assert blocking_gate_ids(obj2) == {"G2_SMALL_N_MEAN_BAR"}

    mutated3 = copy.deepcopy(GATES_CFG)
    mutated3["thresholds"]["skew_abs_threshold"] = 100.0
    obj3 = run_gates("spec_g2_skewed.json", gates_cfg=mutated3)
    assert obj3["verdict"] == "pass"


def test_g2_no_mean_aggregate_not_applicable(tmp_path):
    """无 group_mean 聚合（identity 散点）不走 G2 均值柱判定。"""
    obj = run_gates("spec_scatter_identity.json")
    assert obj["g2"]["groups"] == []
    assert obj["verdict"] == "pass"


# ---------------------------------------------------------------------------
# G3：四声明正反例（truth 植入图逐条对上）
# ---------------------------------------------------------------------------


G3_CASES = [
    ("spec_errorbar_sd.json", "pass", []),
    ("spec_errorbar_sem.json", "pass", []),
    ("spec_errorbar_ci.json", "pass", []),
    ("spec_errorbar_n.json", "pass", []),
    ("spec_g3_sd_missing.json", "blocked", ["G3_SD_SOURCE_MISSING"]),
    ("spec_g3_sem_missing.json", "blocked", ["G3_SEM_SOURCE_MISSING"]),
    ("spec_g3_n_mismatch.json", "blocked", ["G3_N_MISMATCH"]),
    ("spec_g3_ci_incomplete.json", "blocked", ["G3_CI_INCOMPLETE"]),
    ("spec_g3_title_sem.json", "blocked", ["G3_SEM_WITHOUT_SOURCE"]),
]


@pytest.mark.parametrize("spec_name,expected_verdict,expected_errors", G3_CASES)
def test_g3_truth_charts(spec_name, expected_verdict, expected_errors):
    obj = run_gates(spec_name, data_name="synthetic_errorbars.tsv")
    assert obj["verdict"] == expected_verdict
    assert sorted(blocking_gate_ids(obj)) == sorted(expected_errors)


def test_g3_undeclared_suspicious_column_is_info(tmp_path):
    """口径 §11：未声明误差棒但存在可疑 SD 列 → INFO（不阻断）。"""
    obj = run_gates("spec_clean_bar.json")  # groups.csv 无 SD 列 → 不命中
    assert info_gate_ids(obj) == set()
    csv_path = tmp_path / "d.csv"
    csv_path.write_text("组别,产量,产量SD\n甲组,1,0.5\n乙组,2,0.5\n", encoding="utf-8")
    spec = {
        "spec_id": "undeclared_sd",
        "title": "合成示例：未声明误差棒",
        "mark": "bar",
        "encoding": {"x": {"field": "组别"}, "y": {"field": "产量", "decimals": 1}},
    }
    spec_path = tmp_path / "s.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    dataset, _, normalized = parse.run(str(csv_path), str(spec_path))
    prov = provenance.build(dataset, normalized)
    obj = gates.audit(
        dataset, normalized, prov,
        gates_cfg=GATES_CFG, aliases_cfg=ALIASES_CFG, rules_cfg=RULES_CFG,
    )
    assert obj["verdict"] == "pass"
    assert info_gate_ids(obj) == {"G3_ERRORBAR_UNDECLARED"}
    assert obj["g3"]["suspicious_columns"] == ["产量SD"]


def test_g3_aliases_case_insensitive_and_suffix_match(tmp_path):
    """别名表命中语义：大小写不敏感 + 后缀匹配（规则在 aliases.json 一处定义）。"""
    assert ALIASES_CFG["case_sensitive"] is False
    header = ["组别", "产量", "产量sd"]
    matched = [c for c in header if gates._matches_alias(c, ["SD"], ALIASES_CFG)]
    assert matched == ["产量sd"]


def test_g3_alias_table_mutation_breaks_detection(tmp_path):
    """变异探活锚点：删掉 SD 别名后，errorbar_sd 正例必须转为来源缺失。"""
    mutated = copy.deepcopy(ALIASES_CFG)
    mutated["types"]["sd"]["columns"] = ["完全无关的列名"]
    obj = run_gates(
        "spec_errorbar_sd.json",
        data_name="synthetic_errorbars.tsv",
        aliases_cfg=mutated,
    )
    assert obj["verdict"] == "blocked"
    assert blocking_gate_ids(obj) == {"G3_SD_SOURCE_MISSING"}


# ---------------------------------------------------------------------------
# verdict 语义 / 排序 / 双跑一致 / CLI 接线
# ---------------------------------------------------------------------------


def test_verdict_blocked_iff_blocking_level_present():
    blocked = run_gates("spec_g3_title_sem.json", data_name="synthetic_errorbars.tsv")
    assert blocked["verdict"] == "blocked"
    assert blocked["exit_code"] == EXIT_AUDIT_ERRORS
    assert blocked["render_allowed"] is False
    # 把唯一命中降为 WARN 后必须 pass（WARN 不阻断，口径 §14）
    mutated = copy.deepcopy(GATES_CFG)
    warn = RULES_CFG["severity_order"][1]
    for entry in mutated["gates"]:
        if entry["check"] == "error_bar_sem_title":
            entry["severity"] = warn
    downgraded = run_gates(
        "spec_g3_title_sem.json",
        data_name="synthetic_errorbars.tsv",
        gates_cfg=mutated,
    )
    assert downgraded["findings"][0]["severity"] == warn
    assert downgraded["verdict"] == "pass"
    assert downgraded["exit_code"] == EXIT_OK
    assert downgraded["render_allowed"] is True


def test_gates_findings_sorted_stably():
    for spec_name, data_name in (
        ("spec_g2_bimodal.json", "synthetic_groups.csv"),
        ("spec_g3_title_sem.json", "synthetic_errorbars.tsv"),
        ("spec_clean_bar.json", "synthetic_groups.csv"),
    ):
        obj = run_gates(spec_name, data_name=data_name)
        order = {
            level: index for index, level in enumerate(obj["severity_order"])
        }
        keys = [
            (
                order[finding["severity"]],
                finding["gate_id"],
                finding["evidence_path"],
                str(finding["evidence"].get("category", "")),
            )
            for finding in obj["findings"]
        ]
        assert keys == sorted(keys), spec_name


def test_gates_json_byte_identical_across_runs(tmp_path):
    out_a = str(tmp_path / "a")
    out_b = str(tmp_path / "b")
    spec_path = os.path.join(DATA, "spec_g2_skewed.json")
    assert cli.main(["check", GROUPS_CSV, spec_path, "--out", out_a]) == EXIT_AUDIT_ERRORS
    assert cli.main(["check", GROUPS_CSV, spec_path, "--out", out_b]) == EXIT_AUDIT_ERRORS
    with open(os.path.join(out_a, "gates.json"), "rb") as f:
        first = f.read()
    with open(os.path.join(out_b, "gates.json"), "rb") as f:
        second = f.read()
    assert first == second
    assert first.endswith(b"\n") and b"\r" not in first


def test_gates_audit_does_not_mutate_inputs():
    dataset, _, normalized = parse.run(
        GROUPS_CSV, os.path.join(DATA, "spec_g2_skewed.json")
    )
    prov = provenance.build(dataset, normalized)
    dataset_before = copy.deepcopy(dataset)
    normalized_before = copy.deepcopy(normalized)
    prov_before = copy.deepcopy(prov)
    gates.audit(
        dataset, normalized, prov,
        gates_cfg=GATES_CFG, aliases_cfg=ALIASES_CFG, rules_cfg=RULES_CFG,
    )
    assert dataset == dataset_before
    assert normalized == normalized_before
    assert prov == prov_before


def test_cli_final_exit_is_union_of_both_layers():
    """K23：audit 层命中但 gates 层 pass → exit 1；反之亦然；两层都 pass → 0。"""
    out = str(tmp_path_out())
    # 规则层命中（audit blocked，gates pass）
    out1 = str(tmp_path_out())
    assert (
        cli.main(
            [
                "check",
                GROUPS_CSV,
                os.path.join(DATA, "spec_rule_baseline.json"),
                "--out",
                out1,
            ]
        )
        == EXIT_AUDIT_ERRORS
    )
    # 门禁层命中（gates blocked，audit pass）
    out2 = str(tmp_path_out())
    assert (
        cli.main(
            [
                "check",
                GROUPS_CSV,
                os.path.join(DATA, "spec_g2_skewed.json"),
                "--out",
                out2,
            ]
        )
        == EXIT_AUDIT_ERRORS
    )
    # 两层都 pass
    out3 = str(tmp_path_out())
    assert cli.main(["check", GROUPS_CSV, CLEAN_SPEC, "--out", out3]) == EXIT_OK
    assert os.path.isfile(os.path.join(out3, "gates.json"))


def tmp_path_out():
    import tempfile

    return tempfile.mkdtemp(prefix="chartaudit-gates-test-")


def test_cli_exit_three_when_gates_pack_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        gates, "default_gates_path", lambda: str(tmp_path / "missing.json")
    )
    out = str(tmp_path / "out")
    assert cli.main(["check", GROUPS_CSV, CLEAN_SPEC, "--out", out]) == EXIT_CONFIG
    assert not os.path.exists(out)  # 配置失败零写入


def test_cli_exit_three_when_aliases_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        gates, "default_aliases_path", lambda: str(tmp_path / "missing.json")
    )
    out = str(tmp_path / "out")
    assert cli.main(["check", GROUPS_CSV, CLEAN_SPEC, "--out", out]) == EXIT_CONFIG
    assert not os.path.exists(out)


# ---------------------------------------------------------------------------
# 配置校验（缺失 / 非法 → GatesConfigError → exit 3）
# ---------------------------------------------------------------------------


def test_missing_gates_config_raises(tmp_path):
    with pytest.raises(gates.GatesConfigError):
        gates.load_gates(str(tmp_path / "nope.json"), rules_cfg=RULES_CFG)


def test_missing_threshold_key_raises(tmp_path):
    broken = copy.deepcopy(GATES_CFG)
    del broken["thresholds"]["n_min"]
    with pytest.raises(gates.GatesConfigError):
        gates.load_gates(write_config(tmp_path, broken), rules_cfg=RULES_CFG)


def test_duplicate_gate_id_raises(tmp_path):
    broken = copy.deepcopy(GATES_CFG)
    broken["gates"][1]["gate_id"] = broken["gates"][0]["gate_id"]
    with pytest.raises(gates.GatesConfigError):
        gates.load_gates(write_config(tmp_path, broken), rules_cfg=RULES_CFG)


def test_unknown_gate_check_raises(tmp_path):
    broken = copy.deepcopy(GATES_CFG)
    broken["gates"][0]["check"] = "no_such_check"
    with pytest.raises(gates.GatesConfigError):
        gates.load_gates(write_config(tmp_path, broken), rules_cfg=RULES_CFG)


def test_missing_gate_entry_raises(tmp_path):
    """删一条门禁 = 门禁包不完整 → exit 3，绝不静默少检。"""
    broken = copy.deepcopy(GATES_CFG)
    broken["gates"].pop()
    with pytest.raises(gates.GatesConfigError):
        gates.load_gates(write_config(tmp_path, broken), rules_cfg=RULES_CFG)


def test_invalid_gate_severity_raises(tmp_path):
    broken = copy.deepcopy(GATES_CFG)
    broken["gates"][0]["severity"] = "FATAL"
    with pytest.raises(gates.GatesConfigError):
        gates.load_gates(write_config(tmp_path, broken), rules_cfg=RULES_CFG)


def test_invalid_severity_mapping_value_raises(tmp_path):
    broken = copy.deepcopy(GATES_CFG)
    for entry in broken["gates"]:
        if isinstance(entry["severity"], dict):
            entry["severity"]["violation"] = "FATAL"
            break
    with pytest.raises(gates.GatesConfigError):
        gates.load_gates(write_config(tmp_path, broken), rules_cfg=RULES_CFG)


def test_missing_aliases_raises(tmp_path):
    with pytest.raises(gates.GatesConfigError):
        gates.load_aliases(str(tmp_path / "nope.json"))


def test_aliases_missing_type_raises(tmp_path):
    broken = copy.deepcopy(ALIASES_CFG)
    del broken["types"]["n"]
    with pytest.raises(gates.GatesConfigError):
        gates.load_aliases(write_config(tmp_path, broken, "aliases.json"))


def test_gates_json_serialization_is_lf_and_sorted():
    obj = run_gates("spec_g2_skewed.json")
    raw = dumps_json(obj)
    assert raw.endswith(b"\n")
    assert b"\r" not in raw
    text = raw.decode("utf-8")
    assert '"g1"' in text and '"g2"' in text and '"g3"' in text
