"""解析层单元测试：类型推断、缺失、重复、分隔符、规格校验。"""

import json

import pytest

from chartaudit import parse


def write(path, text):
    path.write_text(text, encoding="utf-8")
    return str(path)


def make_spec(tmp_path, **overrides):
    spec = {
        "spec_id": "unit",
        "title": "示例：单元测试",
        "mark": "bar",
        "encoding": {
            "x": {"field": "组别"},
            "y": {"field": "产量"},
        },
    }
    spec.update(overrides)
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    return str(path)


def test_type_inference_order():
    assert parse.infer_cell_type("10") == "integer"
    assert parse.infer_cell_type("-3") == "integer"
    assert parse.infer_cell_type("1.5") == "decimal"
    assert parse.infer_cell_type(".5") == "decimal"
    assert parse.infer_cell_type("1e3") == "string"  # 指数不进入十进制子集
    assert parse.infer_cell_type("2026-01-01") == "date"
    assert parse.infer_cell_type("2026-13-01") == "string"
    # 禁 locale：千分位不识别
    assert parse.infer_cell_type("1,234") == "string"


def test_missing_and_null_tokens(tmp_path):
    csv_path = write(
        tmp_path / "d.csv",
        "组别,产量\n甲组,10\n乙组,\n甲组,NA\n",
    )
    spec = make_spec(tmp_path, null_tokens=["NA"])
    dataset, diagnostics, _ = parse.run(csv_path, spec)
    assert dataset["columns"][1]["missing_count"] == 2
    assert len(diagnostics["missing_cells"]) == 2
    assert {(m["row_index"], m["column"]) for m in diagnostics["missing_cells"]} == {
        (1, "产量"),
        (2, "产量"),
    }


def test_mixed_type_degrades_to_string_with_conflicts(tmp_path):
    csv_path = write(tmp_path / "d.csv", "组别,产量\n甲组,10\n乙组,十\n")
    spec = make_spec(tmp_path)
    dataset, diagnostics, _ = parse.run(csv_path, spec)
    assert dataset["columns"][1]["type"] == "string"
    assert dataset["columns"][1]["conflict_count"] == 1
    assert diagnostics["type_conflicts"][0]["cell"] == "十"


def test_duplicate_rows_and_primary_keys_reported_separately(tmp_path):
    csv_path = write(
        tmp_path / "d.csv",
        "组别,记录编号,产量\n甲组,K1,10\n甲组,K1,10\n乙组,K1,20\n",
    )
    spec = make_spec(tmp_path, primary_key=["记录编号"])
    _, diagnostics, _ = parse.run(csv_path, spec)
    assert len(diagnostics["duplicate_rows"]) == 1
    assert diagnostics["duplicate_rows"][0]["row_indices"] == [0, 1]
    assert len(diagnostics["duplicate_keys"]) == 1
    assert diagnostics["duplicate_keys"][0]["key"] == ["K1"]


def test_delimiter_ambiguous_is_usage_error(tmp_path):
    csv_path = write(tmp_path / "d.csv", "a\tb,c\n1\t2,3\n")
    spec = make_spec(tmp_path, encoding={"x": {"field": "a\tb"}, "y": {"field": "c"}})
    with pytest.raises(parse.ParseError) as exc:
        parse.run(csv_path, spec)
    assert "歧义" in str(exc.value)


def test_ragged_rows_is_usage_error(tmp_path):
    csv_path = write(tmp_path / "d.csv", "组别,产量\n甲组,10,99\n")
    with pytest.raises(parse.ParseError):
        parse.run(csv_path, make_spec(tmp_path))


def test_non_utf8_is_usage_error(tmp_path):
    path = tmp_path / "d.csv"
    path.write_bytes(b"\xff\xfe\x00\x00")
    with pytest.raises(parse.ParseError) as exc:
        parse.run(str(path), make_spec(tmp_path))
    assert "UTF-8" in str(exc.value)


def test_empty_file_is_usage_error(tmp_path):
    csv_path = write(tmp_path / "d.csv", "")
    with pytest.raises(parse.ParseError):
        parse.run(csv_path, make_spec(tmp_path))


def test_unknown_top_level_spec_field_rejected(tmp_path):
    csv_path = write(tmp_path / "d.csv", "组别,产量\n甲组,10\n")
    with pytest.raises(parse.ParseError) as exc:
        parse.run(csv_path, make_spec(tmp_path, extra_field=True))
    assert "未知字段" in str(exc.value)


def test_unknown_encoding_channel_rejected(tmp_path):
    csv_path = write(tmp_path / "d.csv", "组别,产量\n甲组,10\n")
    spec = make_spec(tmp_path)
    with open(spec, encoding="utf-8") as f:
        obj = json.load(f)
    obj["encoding"]["z"] = {"field": "产量"}
    with open(spec, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    with pytest.raises(parse.ParseError) as exc:
        parse.run(csv_path, spec)
    assert "未知字段" in str(exc.value)


def test_aggregate_outside_whitelist_rejected(tmp_path):
    csv_path = write(tmp_path / "d.csv", "组别,产量\n甲组,10\n")
    spec = make_spec(
        tmp_path, encoding={"x": {"field": "组别"}, "y": {"field": "产量", "aggregate": "avg"}}
    )
    with pytest.raises(parse.ParseError) as exc:
        parse.run(csv_path, spec)
    assert "白名单" in str(exc.value)


def test_error_bar_type_outside_enum_rejected(tmp_path):
    csv_path = write(tmp_path / "d.csv", "组别,产量\n甲组,10\n")
    spec = make_spec(
        tmp_path,
        encoding={
            "x": {"field": "组别"},
            "y": {"field": "产量"},
            "error_bar": {"type": "stdev"},
        },
    )
    with pytest.raises(parse.ParseError) as exc:
        parse.run(csv_path, spec)
    assert "error_bar.type" in str(exc.value)


def test_spec_field_must_exist_in_header(tmp_path):
    csv_path = write(tmp_path / "d.csv", "组别,产量\n甲组,10\n")
    spec = make_spec(tmp_path, encoding={"x": {"field": "不存在"}, "y": {"field": "产量"}})
    with pytest.raises(parse.ParseError) as exc:
        parse.run(csv_path, spec)
    assert "不存在的列" in str(exc.value)


def test_normalized_spec_defaults_are_explicit(tmp_path):
    csv_path = write(tmp_path / "d.csv", "组别,产量\n甲组,10\n")
    _, _, normalized = parse.run(csv_path, make_spec(tmp_path))
    assert normalized["y_zero"] is True
    assert normalized["dual_y"] is False
    assert normalized["size_channel"] == "area"
    assert normalized["encoding"]["y"]["aggregate"] is None
