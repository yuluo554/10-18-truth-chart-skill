"""M3 规则回归：truth 逐图对上（R* 命中 / pass 图零 ERROR / G2·G3 过渡态注记）。

K13-A 口径：truth 的 expected_exit 重定义为"解析层退出码"（0=解析通过，2=解析拒绝）；
最终退出码由 expected_verdict 推导。M3 阶段 G2/G3 门禁尚未接线，相关阻塞期望按
过渡态断言（exit 0 + 规则层零 ERROR）；M4 接线 gates.json 后本文件需收紧为阻断断言。
"""

import json
import os

import pytest

from chartaudit import parse, provenance, rules

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO_ROOT, "data", "synthetic")

RULES_CFG = rules.load_rules()
RULE_IDS = {entry["rule_id"] for entry in RULES_CFG["rules"]}
BLOCK_ON = RULES_CFG["block_on"]


def load_truth():
    with open(os.path.join(DATA, "truth.json"), encoding="utf-8") as f:
        return json.load(f)


TRUTH = load_truth()
CASES = TRUTH["charts"]


@pytest.mark.parametrize("chart", CASES, ids=[c["chart_id"] for c in CASES])
def test_truth_chart_rule_expectations(chart):
    csv_path = os.path.join(DATA, chart["data"])
    spec_path = os.path.join(DATA, chart["spec"])
    if chart["expected_exit"] == 2:
        # K15：规格合法性由解析层拦截（R009 证据）；规则层不参与
        with pytest.raises(parse.ParseError):
            parse.run(csv_path, spec_path)
        return
    dataset, _, normalized = parse.run(csv_path, spec_path)
    prov = provenance.build(dataset, normalized)
    audit_obj = rules.audit(dataset, normalized, prov, rules_cfg=RULES_CFG)
    blocking = {
        finding["rule_id"]
        for finding in audit_obj["findings"]
        if finding["severity"] == BLOCK_ON
    }
    expected = list(chart["expected_errors"])
    rule_layer = bool(expected) and set(expected) <= RULE_IDS
    if rule_layer:
        assert set(expected) <= blocking, "植入真值未命中：%r（实际 %r）" % (
            expected,
            sorted(blocking),
        )
        assert audit_obj["verdict"] == chart["expected_verdict"] == "blocked"
        assert audit_obj["exit_code"] == 1
    elif expected:
        # G2 / G3 / G1 注入期望：M3 规则层不应产生 ERROR；M4 gates 接线后翻转
        assert blocking == set(), "M3 规则层不应越权报门禁错误：%r" % sorted(blocking)
        assert audit_obj["verdict"] == "pass"
    else:
        assert blocking == set()
        assert audit_obj["verdict"] == chart["expected_verdict"] == "pass"
        assert audit_obj["exit_code"] == 0


def test_audit_findings_are_sorted_for_every_truth_chart():
    for chart in CASES:
        if chart["expected_exit"] == 2:
            continue
        dataset, _, normalized = parse.run(
            os.path.join(DATA, chart["data"]), os.path.join(DATA, chart["spec"])
        )
        prov = provenance.build(dataset, normalized)
        audit_obj = rules.audit(dataset, normalized, prov, rules_cfg=RULES_CFG)
        order = {
            level: index for index, level in enumerate(audit_obj["severity_order"])
        }
        keys = [
            (order[finding["severity"]], finding["rule_id"], finding["evidence_path"])
            for finding in audit_obj["findings"]
        ]
        assert keys == sorted(keys), chart["chart_id"]


def test_rule_radius_reports_pie_rule_as_superset_fact():
    """既定事实留档：radius 饼图同时命中 R003（5 扇区 > 上限 4）。

    truth 的 expected_errors 是最小植入集（只登记 R005）；基准按"植入集 ⊆ 实际命中"
    断言，不把合法附加命中当失败。M4/M5 复核时不得据此改冻结真值。
    """
    dataset, _, normalized = parse.run(
        os.path.join(DATA, "synthetic_groups.csv"),
        os.path.join(DATA, "spec_rule_radius.json"),
    )
    prov = provenance.build(dataset, normalized)
    audit_obj = rules.audit(dataset, normalized, prov, rules_cfg=RULES_CFG)
    ids = {finding["rule_id"] for finding in audit_obj["findings"]}
    assert {"R003_PIE_SECTORS_SUM", "R005_RADIUS_ENCODING"} <= ids
