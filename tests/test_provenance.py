"""M2 溯源层单元测试：ID 字段序、白名单、Fraction 舍入、G1 不变量。"""

import copy
import hashlib
import json
import os
from fractions import Fraction

import pytest

from chartaudit import parse, provenance

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO_ROOT, "data", "synthetic")
GROUPS_CSV = os.path.join(DATA, "synthetic_groups.csv")
CLEAN_SPEC = os.path.join(DATA, "spec_clean_bar.json")


def build_clean():
    dataset, diagnostics, normalized = parse.run(GROUPS_CSV, CLEAN_SPEC)
    return dataset, normalized, provenance.build(dataset, normalized)


def write_csv(path, text):
    path.write_text(text, encoding="utf-8")
    return str(path)


def write_spec(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return str(path)


def test_rendered_value_id_field_order_locked():
    payload = provenance.canonical_id_payload(
        "s",
        "m",
        "x",
        "c",
        3,
        "col",
        [{"op": "identity", "field": "col"}],
    )
    assert payload == '["s","m","x","c",3,"col",[{"field":"col","op":"identity"}]]'
    expected = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    assert (
        provenance.rendered_value_id(
            "s", "m", "x", "c", 3, "col", [{"op": "identity", "field": "col"}]
        )
        == expected
    )
    # 字段序改变必须改变哈希（防未来重构悄悄换序）
    assert provenance.canonical_id_payload(
        "s",
        "m",
        "x",
        "c",
        3,
        "col",
        [{"op": "identity", "field": "col"}],
    ) != provenance.canonical_id_payload(
        "s", "m", "c", "x", 3, "col", [{"op": "identity", "field": "col"}]
    )


def test_transform_whitelist_is_closed():
    assert set(provenance.TRANSFORM_WHITELIST) == {
        "identity",
        "filter",
        "group_sum",
        "group_mean",
        "group_median",
        "group_count",
        "ratio",
        "sort",
        "top_n",
        "stack_offset",
    }
    with pytest.raises(provenance.ProvenanceError) as exc:
        provenance.apply_transform("moving_average", [Fraction(1)])
    assert "白名单" in str(exc.value)


def test_every_whitelisted_transform_is_callable():
    values = [Fraction(2), Fraction(4), Fraction(9)]
    assert provenance.apply_transform("identity", values) == values
    assert provenance.apply_transform("filter", values) == values
    assert provenance.apply_transform("group_sum", values) == [15]
    assert provenance.apply_transform("group_mean", values) == [5]
    assert provenance.apply_transform("group_median", values) == [4]
    assert provenance.apply_transform("group_count", values) == [3]
    assert provenance.apply_transform("ratio", [Fraction(3)], denominator="5") == [
        Fraction(3, 5)
    ]
    assert provenance.apply_transform("sort", values) == [2, 4, 9]
    assert provenance.apply_transform("top_n", values, n=2) == [9, 4]
    assert provenance.apply_transform("stack_offset", values) == [2, 6, 15]


def test_round_half_up_is_exact_and_not_float():
    # float(1.005) = 1.00499999...，先转 float 会舍成 1.00；按字符串 Fraction 才是 1.01
    assert provenance.format_value(Fraction("1.005"), 2) == "1.01"
    assert provenance.format_value(Fraction("2.675"), 2) == "2.68"
    assert provenance.format_value(Fraction("3.25"), 1) == "3.3"
    assert provenance.format_value(Fraction("-1.25"), 1) == "-1.3"
    assert provenance.format_value(Fraction("12.4"), 1) == "12.4"
    assert provenance.format_value(Fraction(1, 3), None) == "1/3"


def test_build_clean_bar_aggregate_record():
    dataset, normalized, prov = build_clean()
    assert len(prov["rendered_values"]) == 1
    record = prov["rendered_values"][0]
    assert record["category"] == "甲组"
    assert record["series"] is None
    assert record["row_index"] == 0
    assert record["csv_line"] == 2
    assert record["column"] == "产量"
    assert record["raw_cell"] == "11"
    assert record["parsed_value"] == "11"
    assert [source["row_index"] for source in record["sources"]] == [0, 1, 2, 3, 4]
    assert [source["raw_cell"] for source in record["sources"]] == [
        "11",
        "12",
        "14",
        "11",
        "14",
    ]
    assert record["exact_value"] == "12.4"
    assert record["rendered_label"] == "12.4"
    assert record["recomputed_value"] == "12.4"
    assert record["match"] is True
    assert record["transform_chain"] == [
        {"op": "filter", "field": "组别", "equals": "甲组"},
        {"op": "group_mean", "field": "产量"},
    ]
    assert len(record["rendered_value_id"]) == 16
    assert record["rendered_value_id"] == provenance.rendered_value_id(
        normalized["spec_id"],
        record["mark_id"],
        record["series"],
        record["category"],
        record["row_index"],
        record["column"],
        record["transform_chain"],
    )
    assert prov["source"]["sha256"] == dataset["source"]["sha256"]
    report = provenance.validate(prov, dataset, normalized)
    assert report["verdict"] == "pass"
    assert report["exit_code"] == 0
    assert report["render_allowed"] is True


def test_identity_record_raw_cell_and_csv_line():
    dataset, _, normalized = parse.run(
        GROUPS_CSV, os.path.join(DATA, "spec_scatter_identity.json")
    )
    prov = provenance.build(dataset, normalized)
    assert [record["row_index"] for record in prov["rendered_values"]] == [0, 1, 2, 3, 4]
    assert [record["csv_line"] for record in prov["rendered_values"]] == [2, 3, 4, 5, 6]
    assert all(record["match"] is True for record in prov["rendered_values"])


def test_ratio_transform_recomputes_exactly(tmp_path):
    csv_path = write_csv(tmp_path / "d.csv", "组别,产量\n甲组,1\n乙组,3\n")
    spec_path = write_spec(
        tmp_path / "s.json",
        {
            "spec_id": "ratio",
            "title": "示例：占比",
            "mark": "bar",
            "encoding": {
                "x": {"field": "组别"},
                "y": {"field": "产量", "aggregate": "ratio", "decimals": 2},
            },
        },
    )
    dataset, _, normalized = parse.run(csv_path, spec_path)
    prov = provenance.build(dataset, normalized)
    labels = [(record["category"], record["rendered_label"]) for record in prov["rendered_values"]]
    assert labels == [("甲组", "0.25"), ("乙组", "0.75")]
    assert all(record["match"] is True for record in prov["rendered_values"])
    assert all(
        record["transform_chain"][-1]["op"] == "ratio"
        for record in prov["rendered_values"]
    )
    assert provenance.validate(prov, dataset, normalized)["verdict"] == "pass"


def test_duplicate_rendered_value_id_is_conflict():
    dataset, normalized, prov = build_clean()
    prov["rendered_values"].append(copy.deepcopy(prov["rendered_values"][0]))
    report = provenance.validate(prov, dataset, normalized)
    assert report["verdict"] == "blocked"
    assert report["exit_code"] == 1
    assert report["render_allowed"] is False
    assert [issue["gate_id"] for issue in report["errors"]] == [
        "G1_DUPLICATE_RENDERED_VALUE_ID"
    ]


def test_missing_record_is_error():
    dataset, normalized, prov = build_clean()
    prov["rendered_values"].pop()
    report = provenance.validate(prov, dataset, normalized)
    assert [issue["gate_id"] for issue in report["errors"]] == [
        "G1_PROVENANCE_MISSING"
    ]
    assert report["verdict"] == "blocked"
    assert report["exit_code"] == 1


def test_match_false_is_error():
    dataset, normalized, prov = build_clean()
    prov["rendered_values"][0]["recomputed_value"] = "999.9"
    prov["rendered_values"][0]["match"] = False
    report = provenance.validate(prov, dataset, normalized)
    assert [issue["gate_id"] for issue in report["errors"]] == [
        "G1_PROVENANCE_MISMATCH"
    ]
    assert report["verdict"] == "blocked"


@pytest.mark.parametrize("field_value", [999, -1])
def test_row_index_out_of_range_is_error(field_value):
    dataset, normalized, prov = build_clean()
    prov["rendered_values"][0]["row_index"] = field_value
    prov["rendered_values"][0]["csv_line"] = field_value + 2
    report = provenance.validate(prov, dataset, normalized)
    assert [issue["gate_id"] for issue in report["errors"]] == [
        "G1_ROW_COLUMN_NOT_FOUND"
    ]


def test_column_not_found_is_error():
    dataset, normalized, prov = build_clean()
    prov["rendered_values"][0]["column"] = "不存在"
    report = provenance.validate(prov, dataset, normalized)
    assert [issue["gate_id"] for issue in report["errors"]] == [
        "G1_ROW_COLUMN_NOT_FOUND"
    ]


def test_raw_cell_tamper_is_error():
    dataset, normalized, prov = build_clean()
    prov["rendered_values"][0]["raw_cell"] = "999"
    report = provenance.validate(prov, dataset, normalized)
    assert [issue["gate_id"] for issue in report["errors"]] == [
        "G1_RAW_CELL_MISMATCH"
    ]


def test_source_hash_tamper_is_error():
    dataset, normalized, prov = build_clean()
    prov["source"]["sha256"] = "0" * 64
    report = provenance.validate(prov, dataset, normalized)
    assert [issue["gate_id"] for issue in report["errors"]] == ["G1_HASH_MISMATCH"]
    assert report["verdict"] == "blocked"


def test_unexpected_record_is_error():
    dataset, normalized, prov = build_clean()
    extra = copy.deepcopy(prov["rendered_values"][0])
    extra["rendered_value_id"] = "0" * 16
    prov["rendered_values"].append(extra)
    report = provenance.validate(prov, dataset, normalized)
    assert [issue["gate_id"] for issue in report["errors"]] == [
        "G1_UNEXPECTED_RECORD"
    ]


def test_swapped_rendered_value_ids_are_detected():
    dataset, _, normalized = parse.run(
        GROUPS_CSV, os.path.join(DATA, "spec_scatter_identity.json")
    )
    prov = provenance.build(dataset, normalized)
    records = prov["rendered_values"]
    records[0]["rendered_value_id"], records[1]["rendered_value_id"] = (
        records[1]["rendered_value_id"],
        records[0]["rendered_value_id"],
    )
    report = provenance.validate(prov, dataset, normalized)
    assert report["verdict"] == "blocked"
    assert {issue["gate_id"] for issue in report["errors"]} == {"G1_ID_MISMATCH"}


def test_csv_line_must_equal_row_index_plus_two():
    dataset, normalized, prov = build_clean()
    prov["rendered_values"][0]["csv_line"] = 3
    report = provenance.validate(prov, dataset, normalized)
    assert [issue["gate_id"] for issue in report["errors"]] == [
        "G1_MALFORMED_RECORD"
    ]


def test_aggregate_outside_whitelist_raises_usage_error():
    dataset, _, normalized = parse.run(GROUPS_CSV, CLEAN_SPEC)
    broken = copy.deepcopy(normalized)
    broken["encoding"]["y"]["aggregate"] = "avg"
    with pytest.raises(provenance.ProvenanceError) as exc:
        provenance.build(dataset, broken)
    assert "白名单" in str(exc.value)


def test_negative_decimals_raises_usage_error():
    dataset, _, normalized = parse.run(GROUPS_CSV, CLEAN_SPEC)
    broken = copy.deepcopy(normalized)
    broken["encoding"]["y"]["decimals"] = -1
    with pytest.raises(provenance.ProvenanceError):
        provenance.build(dataset, broken)
