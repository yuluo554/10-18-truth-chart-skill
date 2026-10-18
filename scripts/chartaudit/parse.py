"""M1 解析层：CSV/TSV → dataset.json / diagnostics.json / chart_spec.normalized.json。

纪律：
- 纯函数、无网络、无时钟、无随机、无 locale；
- 编码仅 UTF-8（含 BOM），解码失败显式 exit 2，不做猜测性转码；
- 类型推断固定顺序 整数 → 十进制数 → ISO 8601 日期 → 字符串；列类型全列一致；
  全列缺失时无类型证据，按 string 处理；
- 缺失值 = 空单元格 + spec 声明的 null 标记；
- 整行重复与声明主键后的重复键分开统计；
- 规格未知字段直接报错，不静默忽略。
"""

import csv
import datetime
import hashlib
import io
import os
import re

INT_RE = re.compile(r"^[+-]?\d+$")
DEC_RE = re.compile(r"^[+-]?(?:\d+\.\d*|\.\d+)(?:[eE][+-]?\d+)?$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

TYPE_ORDER = ("integer", "decimal", "date", "string")

TOP_LEVEL_FIELDS = {
    "spec_id",
    "title",
    "mark",
    "encoding",
    "null_tokens",
    "primary_key",
    "y_zero",
    "dual_y",
    "pseudo_3d",
    "smooth",
    "size_channel",
    "overlay_scatter",
    "low_contrast",
    "y_decimals",
}
ENCODING_FIELDS = {"x", "y", "series", "error_bar"}
MARK_TYPES = {"bar", "line", "scatter", "box", "pie"}
AGGREGATES = {
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
ERROR_BAR_TYPES = {"sd", "sem", "ci", "n"}


class ParseError(Exception):
    """输入 / 规格错误，映射退出码 2。"""


def _is_date(cell):
    if not DATE_RE.match(cell):
        return False
    try:
        year, month, day = (int(part) for part in cell.split("-"))
        datetime.date(year, month, day)
    except ValueError:
        return False
    return True


def infer_cell_type(cell):
    if INT_RE.match(cell):
        return "integer"
    if DEC_RE.match(cell):
        return "decimal"
    if _is_date(cell):
        return "date"
    return "string"


def _decode(path):
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as exc:
        raise ParseError("无法读取输入文件 %s：%s" % (os.path.basename(path), exc))
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ParseError(
            "输入文件不是合法 UTF-8：%s（%s）；本工具不做猜测性转码"
            % (os.path.basename(path), exc)
        )
    return raw, text


def _parse_with(text, delimiter):
    return list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter))


def _consistent(rows):
    if not rows:
        return False
    width = len(rows[0])
    return width > 0 and all(len(row) == width for row in rows)


def detect_and_parse(text):
    """按表头列数一致性实测判定分隔符；两种候选都自洽 → 歧义 exit 2。"""
    candidates = []
    for delimiter in (",", "\t"):
        rows = _parse_with(text, delimiter)
        if _consistent(rows) and len(rows[0]) > 1:
            candidates.append((delimiter, rows))
    if not candidates:
        raise ParseError("列数不齐或无法识别分隔符（仅支持 CSV 逗号 / TSV 制表符）")
    if len(candidates) > 1:
        raise ParseError("分隔符歧义：逗号与制表符解析均自洽，无法判定 CSV/TSV")
    return candidates[0]


def load_spec(path):
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as exc:
        raise ParseError("无法读取规格文件 %s：%s" % (os.path.basename(path), exc))
    try:
        spec = json_loads(raw)
    except ValueError as exc:
        raise ParseError("规格 JSON 解析失败：%s" % exc)
    if not isinstance(spec, dict):
        raise ParseError("规格必须是 JSON 对象")
    return spec


def json_loads(raw):
    import json

    return json.loads(raw.decode("utf-8-sig"))


def validate_spec_shape(spec):
    unknown = sorted(set(spec) - TOP_LEVEL_FIELDS)
    if unknown:
        raise ParseError("规格含未知字段：%s" % ", ".join(unknown))
    for required in ("spec_id", "title", "mark", "encoding"):
        if required not in spec:
            raise ParseError("规格缺少必填字段：%s" % required)
    if spec["mark"] not in MARK_TYPES:
        raise ParseError(
            "非法 mark：%r（允许 %s）" % (spec["mark"], ", ".join(sorted(MARK_TYPES)))
        )
    encoding = spec["encoding"]
    if not isinstance(encoding, dict):
        raise ParseError("encoding 必须是对象")
    unknown_enc = sorted(set(encoding) - ENCODING_FIELDS)
    if unknown_enc:
        raise ParseError("encoding 含未知字段：%s" % ", ".join(unknown_enc))
    for axis in ("x", "y"):
        if axis not in encoding:
            raise ParseError("encoding 缺少 %s 通道" % axis)
        channel = encoding[axis]
        if not isinstance(channel, dict) or "field" not in channel:
            raise ParseError("encoding.%s 必须是含 field 的对象" % axis)
        for key in channel:
            if key not in ("field", "aggregate", "filter", "decimals"):
                raise ParseError("encoding.%s 含未知字段：%s" % (axis, key))
        if "aggregate" in channel and channel["aggregate"] not in AGGREGATES:
            raise ParseError(
                "encoding.%s.aggregate 不在变换白名单：%r" % (axis, channel["aggregate"])
            )
        if "filter" in channel:
            flt = channel["filter"]
            if not isinstance(flt, dict) or set(flt) != {"field", "equals"}:
                raise ParseError("encoding.%s.filter 必须是 {field, equals}" % axis)
        if "decimals" in channel and not isinstance(channel["decimals"], int):
            raise ParseError("encoding.%s.decimals 必须是整数" % axis)
    if "error_bar" in encoding:
        eb = encoding["error_bar"]
        if not isinstance(eb, dict) or "type" not in eb:
            raise ParseError("encoding.error_bar 必须是含 type 的对象")
        for key in eb:
            if key not in ("type", "column", "confidence"):
                raise ParseError("encoding.error_bar 含未知字段：%s" % key)
        if eb["type"] not in ERROR_BAR_TYPES:
            raise ParseError(
                "error_bar.type 不在枚举内：%r（允许 %s）"
                % (eb["type"], ", ".join(sorted(ERROR_BAR_TYPES)))
            )
    if "null_tokens" in spec:
        if not isinstance(spec["null_tokens"], list) or not all(
            isinstance(token, str) for token in spec["null_tokens"]
        ):
            raise ParseError("null_tokens 必须是字符串数组")
    if "primary_key" in spec:
        if not isinstance(spec["primary_key"], list) or not all(
            isinstance(col, str) for col in spec["primary_key"]
        ):
            raise ParseError("primary_key 必须是字符串数组")
    if "size_channel" in spec and spec["size_channel"] not in ("area", "radius"):
        raise ParseError("size_channel 只允许 area / radius")


def normalize_spec(spec, header):
    """字段序固定 + 默认值显式化；未知字段已在校验阶段拒绝。"""
    validate_spec_shape(spec)
    columns = set(header)
    encoding = spec["encoding"]

    def channel(name):
        channel_obj = dict(encoding[name])
        field = channel_obj["field"]
        if field not in columns:
            raise ParseError("encoding.%s.field 指向不存在的列：%r" % (name, field))
        if "filter" in channel_obj and channel_obj["filter"]["field"] not in columns:
            raise ParseError(
                "encoding.%s.filter.field 指向不存在的列：%r"
                % (name, channel_obj["filter"]["field"])
            )
        channel_obj.setdefault("aggregate", None)
        channel_obj.setdefault("decimals", None)
        return channel_obj

    normalized = {
        "spec_id": spec["spec_id"],
        "title": spec["title"],
        "mark": spec["mark"],
        "encoding": {
            "x": channel("x"),
            "y": channel("y"),
        },
        "null_tokens": list(spec.get("null_tokens", [])),
        "primary_key": list(spec.get("primary_key", [])),
        "y_zero": bool(spec.get("y_zero", True)),
        "dual_y": bool(spec.get("dual_y", False)),
        "pseudo_3d": bool(spec.get("pseudo_3d", False)),
        "smooth": bool(spec.get("smooth", False)),
        "size_channel": spec.get("size_channel", "area"),
        "overlay_scatter": bool(spec.get("overlay_scatter", False)),
        "low_contrast": bool(spec.get("low_contrast", False)),
    }
    if "series" in encoding:
        series = dict(encoding["series"])
        if set(series) != {"field"}:
            raise ParseError("encoding.series 只允许 field")
        if series["field"] not in columns:
            raise ParseError("encoding.series.field 指向不存在的列：%r" % series["field"])
        normalized["encoding"]["series"] = series
    if "error_bar" in encoding:
        eb = dict(encoding["error_bar"])
        if "column" in eb and eb["column"] not in columns:
            raise ParseError("error_bar.column 指向不存在的列：%r" % eb["column"])
        normalized["encoding"]["error_bar"] = eb
    for key in normalized["primary_key"]:
        if key not in columns:
            raise ParseError("primary_key 指向不存在的列：%r" % key)
    return normalized


def parse_table(path, null_tokens=()):
    raw, text = _decode(path)
    if not text.strip():
        raise ParseError("输入文件为空：%s" % os.path.basename(path))
    delimiter, rows = detect_and_parse(text)
    if len(rows) < 2:
        raise ParseError("缺少表头或数据行：%s" % os.path.basename(path))
    header = rows[0]
    data_rows = rows[1:]
    if any(cell == "" for cell in header):
        raise ParseError("表头存在空列名：%s" % os.path.basename(path))
    if len(set(header)) != len(header):
        raise ParseError("表头存在重复列名：%s" % os.path.basename(path))
    return {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        "delimiter": delimiter,
        "header": header,
        "rows": data_rows,
        "name": os.path.basename(path),
    }


def build_dataset(table, null_tokens):
    header = table["header"]
    rows = table["rows"]
    null_set = set(null_tokens)
    columns = []
    missing_cells = []
    type_conflicts = []
    for col_index, name in enumerate(header):
        cells = [row[col_index] for row in rows]
        present = [cell for cell in cells if cell != "" and cell not in null_set]
        missing_count = len(cells) - len(present)
        for row_index, cell in enumerate(cells):
            if cell == "" or cell in null_set:
                missing_cells.append(
                    {"row_index": row_index, "column": name, "column_index": col_index}
                )
        type_counts = {}
        for cell in present:
            cell_type = infer_cell_type(cell)
            type_counts[cell_type] = type_counts.get(cell_type, 0) + 1
        if not type_counts:
            column_type = "string"
        elif len(type_counts) == 1:
            column_type = next(iter(type_counts))
        else:
            column_type = "string"
            majority = max(
                type_counts,
                key=lambda key: (type_counts[key], -TYPE_ORDER.index(key)),
            )
            for row_index, cell in enumerate(cells):
                if cell == "" or cell in null_set:
                    continue
                cell_type = infer_cell_type(cell)
                if cell_type != majority:
                    type_conflicts.append(
                        {
                            "row_index": row_index,
                            "column": name,
                            "cell": cell,
                            "cell_type": cell_type,
                        }
                    )
        columns.append(
            {
                "name": name,
                "type": column_type,
                "missing_count": missing_count,
                "conflict_count": sum(1 for c in type_conflicts if c["column"] == name),
            }
        )

    dataset = {
        "source": {
            "name": table["name"],
            "sha256": table["sha256"],
            "size_bytes": table["size_bytes"],
        },
        "delimiter": table["delimiter"],
        "header": list(header),
        "row_count": len(rows),
        "columns": columns,
        "rows": [list(row) for row in rows],
    }

    diagnostics = {
        "delimiter": table["delimiter"],
        "null_tokens": list(null_tokens),
        "missing_cells": missing_cells,
        "type_conflicts": type_conflicts,
        "duplicate_rows": [],
        "duplicate_keys": [],
    }
    diagnostics["duplicate_rows"] = _duplicate_rows(rows)
    diagnostics["issue_count"] = (
        len(missing_cells)
        + len(type_conflicts)
        + len(diagnostics["duplicate_rows"])
        + len(diagnostics["duplicate_keys"])
    )
    return dataset, diagnostics


def _duplicate_rows(rows):
    seen = {}
    for row_index, row in enumerate(rows):
        key = tuple(row)
        seen.setdefault(key, []).append(row_index)
    duplicates = []
    for key in seen:
        if len(seen[key]) > 1:
            duplicates.append({"row_indices": seen[key], "count": len(seen[key])})
    duplicates.sort(key=lambda item: item["row_indices"][0])
    return duplicates


def duplicate_keys(rows, header, primary_key):
    if not primary_key:
        return []
    indices = [header.index(column) for column in primary_key]
    seen = {}
    for row_index, row in enumerate(rows):
        key = tuple(row[index] for index in indices)
        seen.setdefault(key, []).append(row_index)
    duplicates = []
    for key in sorted(seen):
        if len(seen[key]) > 1:
            duplicates.append(
                {
                    "key": list(key),
                    "columns": list(primary_key),
                    "row_indices": seen[key],
                    "count": len(seen[key]),
                }
            )
    return duplicates


def run(csv_path, spec_path):
    """执行解析层，返回 (dataset, diagnostics, normalized_spec)。"""
    spec = load_spec(spec_path)
    null_tokens = spec.get("null_tokens", []) if isinstance(spec, dict) else []
    table = parse_table(csv_path, null_tokens)
    normalized = normalize_spec(spec, table["header"])
    dataset, diagnostics = build_dataset(table, null_tokens)
    diagnostics["duplicate_keys"] = duplicate_keys(
        table["rows"], table["header"], normalized["primary_key"]
    )
    diagnostics["issue_count"] += len(diagnostics["duplicate_keys"])
    return dataset, diagnostics, normalized
