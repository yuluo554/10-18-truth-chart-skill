"""M5 渲染层：dataset + normalized spec + provenance + audit + gates → 单文件 HTML。

纪律（唯一口径见 data/README.md 第四节）：
- 单文件 HTML：内联 SVG + 内联 CSS + 少量内联 JS；零 CDN（无 `<script src>` /
  `<link>` / `url()` / `@import` / `http(s)://`；扫描门见 tests/test_render.py）；
- 几何常量全部来自 `references/geometry.json`（口径 §16）；本模块零几何字面量
  （扫描门：tokenize 后仅允许控制流小整数 0/1/2/3/4/5/10）；禁止随机抖动 / 自适应；
- 确定性：无时间戳 / 随机数 / 进程 ID / 绝对路径 / locale；同一输入两次渲染
  字节级一致（测试锁）；SVG 属性顺序由构造顺序固定；
- hover 溯源提示的数据源只来自 provenance.json 记录（K29）：`csv_line` 直接取
  记录字段（= row_index + 2，口径 §1），不在渲染时重算任何数值；
- 审计区块：ERROR / WARN / INFO 列表与计数；`blocked` 时页面显示阻断横幅；
- 发布门语义（K27）：本模块只负责"生成什么 HTML"，是否写盘 / 写哪个文件名由
  CLI 依据 `render_allowed` 决定（可发布 `<name>.html` vs 调试件 `<name>.audit.html`）。

`HTML_PROVENANCE_FIELDS` 是 hover 数据载荷的字段集合与顺序唯一出处；`SKILL.md`
的机器可解析契约块与 `tests/test_render.py` 的"声明 ↔ 常量 ↔ 实际输出"三方断言
共同锁定（K28）。
"""

import html as html_module
import json
import math
import os
import re
from fractions import Fraction

from .provenance import format_value

CONTRACT_VERSION = 1

# 几何常量键集合（值唯一出处：references/geometry.json）
GEOMETRY_KEYS = (
    "canvas_width",
    "canvas_height",
    "margin_top",
    "margin_right",
    "margin_bottom",
    "margin_left",
    "bar_width",
    "bar_gap",
    "line_radius",
    "scatter_radius",
    "scatter_stack_step",
    "pie_radius",
    "pie_start_angle",
    "pie_full_angle",
    "pie_half_turn",
    "pie_label_radius",
    "box_width",
    "box_whisker_cap",
    "box_median_stroke",
    "font_size_title",
    "font_size_axis",
    "font_size_label",
    "font_size_legend",
    "font_size_hover",
    "label_offset",
    "y_tick_count",
    "x_tick_label_maxlen",
    "legend_cell_width",
    "legend_swatch_size",
    "hover_panel_width",
    "hover_cursor_offset",
    "coord_decimals",
    "spacing_small",
    "spacing_medium",
    "spacing_large",
    "stroke_width_axis",
    "stroke_width_mark",
    "font_weight_bold",
    "z_index_tip",
    "line_height_tip",
    "color_palette",
    "color_text",
    "color_axis",
    "color_grid",
    "color_banner",
    "color_background",
    "color_hover_panel",
    "hover_opacity",
)

# hover 数据载荷字段集合与顺序（K28 契约块三方断言的代码侧常量）
HTML_PROVENANCE_FIELDS = (
    "rendered_value_id",
    "csv_line",
    "column",
    "raw_cell",
    "parsed_value",
    "transform_chain",
    "transform_summary",
    "rendered_label",
    "exact_value",
    "series",
    "category",
    "sources",
    "sources_count",
)

# HTML 必备区块标记（data-section 属性值）
HTML_SECTIONS = ("chart", "audit", "provenance-data")

_COLOR_RE = re.compile(r"^#[0-9a-f]{6}$")
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]")


class GeometryConfigError(Exception):
    """几何配置缺失 / 校验失败，映射退出码 3。"""


# ---------------------------------------------------------------------------
# 几何配置加载（references/geometry.json 是唯一出处）
# ---------------------------------------------------------------------------


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def default_geometry_path():
    return os.path.join(_repo_root(), "references", "geometry.json")


def load_geometry(path=None):
    """读取并校验几何包；缺失 / 非法 → GeometryConfigError（exit 3）。"""
    if path is None:
        path = default_geometry_path()
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as exc:
        raise GeometryConfigError("无法读取几何包 %s：%s" % (path, exc))
    try:
        config = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise GeometryConfigError("几何包不是合法 UTF-8 JSON：%s" % exc)
    if not isinstance(config, dict):
        raise GeometryConfigError("几何包必须是 JSON 对象")
    if config.get("contract_version") != CONTRACT_VERSION:
        raise GeometryConfigError(
            "几何包 contract_version=%r（期望 %d）"
            % (config.get("contract_version"), CONTRACT_VERSION)
        )
    values = config.get("values")
    if not isinstance(values, dict):
        raise GeometryConfigError("几何包缺少 values 对象")
    missing = [key for key in GEOMETRY_KEYS if key not in values]
    extra = [key for key in values if key not in GEOMETRY_KEYS]
    if missing:
        raise GeometryConfigError("几何包缺少键：%s" % ", ".join(missing))
    if extra:
        raise GeometryConfigError("几何包含未知键：%s" % ", ".join(sorted(extra)))
    for key in GEOMETRY_KEYS:
        value = values[key]
        if key == "color_palette":
            if not isinstance(value, list) or not value:
                raise GeometryConfigError("color_palette 必须是非空数组")
            for item in value:
                if not isinstance(item, str) or not _COLOR_RE.match(item):
                    raise GeometryConfigError(
                        "color_palette 含非法颜色：%r" % (item,)
                    )
        elif key.startswith("color_"):
            if not isinstance(value, str) or not _COLOR_RE.match(value):
                raise GeometryConfigError("%s 必须是 #rrggbb 颜色：%r" % (key, value))
        elif key == "hover_opacity":
            try:
                opacity = Fraction(str(value))
            except (ValueError, ZeroDivisionError):
                raise GeometryConfigError("hover_opacity 不是数值：%r" % (value,))
            if opacity < 0 or opacity > 1:
                raise GeometryConfigError("hover_opacity 必须在 [0, 1] 内")
        elif key in ("line_height_tip",):
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
                raise GeometryConfigError("%s 必须是正数：%r" % (key, value))
        else:
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise GeometryConfigError("%s 必须是正整数：%r" % (key, value))
    if values["margin_left"] + values["margin_right"] >= values["canvas_width"]:
        raise GeometryConfigError("左右边距之和必须小于画布宽度")
    if values["margin_top"] + values["margin_bottom"] >= values["canvas_height"]:
        raise GeometryConfigError("上下边距之和必须小于画布高度")
    if values["y_tick_count"] < 2:
        raise GeometryConfigError("y_tick_count 必须 >= 2")
    if values["pie_half_turn"] * 2 != values["pie_full_angle"]:
        raise GeometryConfigError("pie_full_angle 必须等于 pie_half_turn 的 2 倍")
    return config


def output_name(spec_id):
    """可发布 / 调试 HTML 的文件名基名（同 dir 下 `<name>.html` / `<name>.audit.html`）。"""
    name = _SAFE_NAME_RE.sub("_", str(spec_id))
    return name or "chart"


# ---------------------------------------------------------------------------
# 基础格式化 / SVG 工具
# ---------------------------------------------------------------------------


def _esc(value):
    return html_module.escape(str(value), quote=True)


def _px(value):
    """Fraction / int → 精确十进制串（禁 float 中转）。"""
    if isinstance(value, Fraction):
        return format_value(value, None)
    return str(value)


def _coord(value, geometry):
    """浮点坐标（仅饼图三角函数）→ 固定小数位字符串；-0 归一为 0。"""
    decimals = geometry["coord_decimals"]
    rounded = round(value, decimals)
    text = format(rounded, ".%df" % decimals)
    if text.startswith("-") and float(text) == 0:
        text = text[1:]
    return text


def _el(name, attrs, children=None):
    parts = [name]
    for key, value in attrs:
        parts.append('%s="%s"' % (key, _esc(value)))
    head = "<" + " ".join(parts)
    if children is None:
        return head + "/>"
    return head + ">" + "".join(children) + "</" + name + ">"


def _text(x, y, value, attrs):
    return _el("text", [("x", x), ("y", y)] + list(attrs), [_esc(value)])


def _fraction(text):
    return Fraction(text)


# ---------------------------------------------------------------------------
# hover 载荷（K29：只消费 provenance.json 记录）
# ---------------------------------------------------------------------------


def _transform_summary(chain):
    parts = []
    for step in chain:
        name = step.get("op")
        params = []
        for key in sorted(step):
            if key == "op":
                continue
            params.append("%s=%s" % (key, step[key]))
        if params:
            parts.append("%s(%s)" % (name, ", ".join(params)))
        else:
            parts.append(str(name))
    return " → ".join(parts)


def _payload(record):
    sources = []
    for source in record.get("sources", []):
        sources.append(
            {
                "csv_line": source.get("csv_line"),
                "column": source.get("column"),
                "raw_cell": source.get("raw_cell"),
            }
        )
    return {
        "rendered_value_id": record.get("rendered_value_id"),
        "csv_line": record.get("csv_line"),
        "column": record.get("column"),
        "raw_cell": record.get("raw_cell"),
        "parsed_value": record.get("parsed_value"),
        "transform_chain": record.get("transform_chain"),
        "transform_summary": _transform_summary(record.get("transform_chain") or []),
        "rendered_label": record.get("rendered_label"),
        "exact_value": record.get("exact_value"),
        "series": record.get("series"),
        "category": record.get("category"),
        "sources": sources,
        "sources_count": len(sources),
    }


# ---------------------------------------------------------------------------
# 图表模型（只读 provenance 记录；坏记录跳过，不崩溃——阻断调试件也要能出）
# ---------------------------------------------------------------------------


def _usable_records(provenance_obj):
    records = []
    for record in provenance_obj.get("rendered_values", []):
        try:
            value = _fraction(record["exact_value"])
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            continue
        records.append((record, value))
    return records


def _category_order(records):
    categories = []
    for record, _ in records:
        category = record.get("category")
        if category not in categories:
            categories.append(category)
    return categories


def _series_order(records):
    series = []
    for record, _ in records:
        value = record.get("series")
        if value not in series:
            series.append(value)
    return series


def _series_color(index, geometry):
    palette = geometry["color_palette"]
    return palette[index % len(palette)]


def _overlay_dots(records):
    dots = []
    for record, _ in records:
        for index, source in enumerate(record.get("sources", [])):
            try:
                value = _fraction(source["parsed_value"])
            except (KeyError, TypeError, ValueError, ZeroDivisionError):
                continue
            dots.append((record, index, source, value))
    return dots


# ---------------------------------------------------------------------------
# 刻度与坐标（全部 Fraction 精确算术）
# ---------------------------------------------------------------------------


def _y_domain(values, y_zero):
    if not values:
        return Fraction(0), Fraction(1)
    low = min(values)
    high = max(values)
    if y_zero:
        low = min(low, Fraction(0))
        high = max(high, Fraction(0))
    if low == high:
        if low == 0:
            high = Fraction(1)
        elif low > 0:
            low = Fraction(0)
        else:
            high = Fraction(0)
    return low, high


def _nice_step(raw):
    magnitude = Fraction(1)
    while magnitude < raw:
        magnitude *= 10
    for divisor in (10, 5, 2, 1):
        candidate = magnitude / divisor
        if candidate >= raw:
            return candidate
    return magnitude


def _ticks(low, high, count):
    span = high - low
    step = _nice_step(span / (count - 1))
    first_index = low // step
    last_index = -((-high) // step)
    first = Fraction(first_index) * step
    last = Fraction(last_index) * step
    ticks = []
    for index in range(last_index - first_index + 1):
        ticks.append(first + step * index)
    return ticks, first, last


def _y_position(value, low, high, plot_top, plot_height):
    return plot_top + (high - value) * plot_height / (high - low)


def _slot_center(index, total, plot_left, plot_width):
    return plot_left + plot_width * Fraction(2 * index + 1, 2 * total)


def _tick_label(value, geometry):
    text = _px(value)
    limit = geometry["x_tick_label_maxlen"]
    if len(text) > limit:
        return text[:limit] + "…"
    return text


def _quantile(ordered, numerator, denominator):
    if not ordered:
        return Fraction(0)
    position = Fraction(numerator, denominator) * (len(ordered) - 1)
    lower = position // 1
    if lower >= len(ordered) - 1:
        return ordered[-1]
    fraction = position - lower
    if fraction == 0:
        return ordered[lower]
    return ordered[lower] + fraction * (ordered[lower + 1] - ordered[lower])


# ---------------------------------------------------------------------------
# SVG 组装
# ---------------------------------------------------------------------------


def _draw_legend(parts, entries, geometry):
    if not entries:
        return
    plot_left = geometry["margin_left"]
    y_center = Fraction(geometry["margin_top"], 2)
    swatch = geometry["legend_swatch_size"]
    for index, (name, color) in enumerate(entries):
        x = plot_left + index * geometry["legend_cell_width"]
        parts.append(
            _el(
                "rect",
                [
                    ("x", _px(x)),
                    ("y", _px(y_center - Fraction(swatch, 2))),
                    ("width", str(swatch)),
                    ("height", str(swatch)),
                    ("fill", color),
                ],
            )
        )
        parts.append(
            _text(
                _px(x + swatch + geometry["label_offset"]),
                _px(y_center),
                name,
                [
                    ("text-anchor", "start"),
                    ("dominant-baseline", "central"),
                    ("font-size", str(geometry["font_size_legend"])),
                    ("fill", geometry["color_text"]),
                ],
            )
        )


def _draw_axes(parts, categories, ticks, domain, geometry):
    plot_left = geometry["margin_left"]
    plot_top = geometry["margin_top"]
    plot_width = geometry["canvas_width"] - geometry["margin_left"] - geometry["margin_right"]
    plot_height = geometry["canvas_height"] - geometry["margin_top"] - geometry["margin_bottom"]
    low, high = domain
    color = geometry["color_axis"]
    grid = geometry["color_grid"]
    for tick in ticks:
        y = _y_position(tick, low, high, plot_top, plot_height)
        parts.append(
            _el(
                "line",
                [
                    ("x1", _px(plot_left)),
                    ("y1", _px(y)),
                    ("x2", _px(plot_left + plot_width)),
                    ("y2", _px(y)),
                    ("stroke", grid),
                    ("stroke-width", str(geometry["stroke_width_axis"])),
                ],
            )
        )
        parts.append(
            _text(
                _px(plot_left - geometry["label_offset"]),
                _px(y),
                _px(tick),
                [
                    ("text-anchor", "end"),
                    ("dominant-baseline", "central"),
                    ("font-size", str(geometry["font_size_axis"])),
                    ("fill", color),
                ],
            )
        )
    zero = Fraction(0)
    if low <= zero <= high:
        axis_y = _y_position(zero, low, high, plot_top, plot_height)
    else:
        axis_y = plot_top + plot_height
    parts.append(
        _el(
            "line",
            [
                ("x1", _px(plot_left)),
                ("y1", _px(axis_y)),
                ("x2", _px(plot_left + plot_width)),
                ("y2", _px(axis_y)),
                ("stroke", color),
                ("stroke-width", str(geometry["stroke_width_axis"])),
            ],
        )
    )
    parts.append(
        _el(
            "line",
            [
                ("x1", _px(plot_left)),
                ("y1", _px(plot_top)),
                ("x2", _px(plot_left)),
                ("y2", _px(plot_top + plot_height)),
                ("stroke", color),
                ("stroke-width", str(geometry["stroke_width_axis"])),
            ],
        )
    )
    label_y = plot_top + plot_height + geometry["label_offset"] + geometry["font_size_axis"]
    for index, category in enumerate(categories):
        center = _slot_center(index, len(categories), plot_left, plot_width)
        parts.append(
            _text(
                _px(center),
                _px(Fraction(label_y)),
                _tick_label(category, geometry),
                [
                    ("text-anchor", "middle"),
                    ("font-size", str(geometry["font_size_axis"])),
                    ("fill", color),
                ],
            )
        )


def _draw_bar(parts, records, categories, series, domain, geometry):
    plot_left = geometry["margin_left"]
    plot_top = geometry["margin_top"]
    plot_width = geometry["canvas_width"] - geometry["margin_left"] - geometry["margin_right"]
    plot_height = geometry["canvas_height"] - geometry["margin_top"] - geometry["margin_bottom"]
    low, high = domain
    zero = Fraction(0)
    if low <= zero <= high:
        baseline = zero
    elif high < zero:
        baseline = high
    else:
        baseline = low
    series_index = {value: index for index, value in enumerate(series)}
    bar_width = geometry["bar_width"]
    bar_gap = geometry["bar_gap"]
    centers = {}
    for category_index, category in enumerate(categories):
        entries = [(record, value) for record, value in records if record.get("category") == category]
        count = len(entries)
        slot_center = _slot_center(category_index, len(categories), plot_left, plot_width)
        total_width = Fraction(count * bar_width + (count - 1) * bar_gap)
        start = slot_center - total_width / 2
        for position, (record, value) in enumerate(entries):
            bar_center = start + Fraction(position * (bar_width + bar_gap)) + Fraction(bar_width, 2)
            centers[(record.get("series"), category)] = bar_center
            value_y = _y_position(value, low, high, plot_top, plot_height)
            base_y = _y_position(baseline, low, high, plot_top, plot_height)
            top = min(value_y, base_y)
            height = abs(value_y - base_y)
            color = _series_color(series_index.get(record.get("series"), 0), geometry)
            parts.append(
                _el(
                    "rect",
                    [
                        ("x", _px(bar_center - Fraction(bar_width, 2))),
                        ("y", _px(top)),
                        ("width", str(bar_width)),
                        ("height", _px(height)),
                        ("fill", color),
                        ("data-rid", record.get("rendered_value_id")),
                        ("tabindex", "0"),
                    ],
                )
            )
            if value >= 0:
                label_y = top - geometry["label_offset"]
            else:
                label_y = top + height + geometry["label_offset"] + geometry["font_size_label"]
            parts.append(
                _text(
                    _px(bar_center),
                    _px(label_y),
                    record.get("rendered_label", ""),
                    [
                        ("text-anchor", "middle"),
                        ("font-size", str(geometry["font_size_label"])),
                        ("fill", geometry["color_text"]),
                    ],
                )
            )
    return centers


def _draw_line(parts, records, categories, series, domain, geometry):
    plot_left = geometry["margin_left"]
    plot_top = geometry["margin_top"]
    plot_width = geometry["canvas_width"] - geometry["margin_left"] - geometry["margin_right"]
    plot_height = geometry["canvas_height"] - geometry["margin_top"] - geometry["margin_bottom"]
    low, high = domain
    category_index = {value: index for index, value in enumerate(categories)}
    for series_index, series_value in enumerate(series):
        points = [
            (category_index[record.get("category")], value)
            for record, value in records
            if record.get("series") == series_value
        ]
        points.sort(key=lambda item: item[0])
        if not points:
            continue
        color = _series_color(series_index, geometry)
        commands = []
        for point_index, (index, value) in enumerate(points):
            x = _slot_center(index, len(categories), plot_left, plot_width)
            y = _y_position(value, low, high, plot_top, plot_height)
            commands.append("%s %s %s" % ("M" if point_index == 0 else "L", _px(x), _px(y)))
        parts.append(
            _el(
                "path",
                [
                    ("d", " ".join(commands)),
                    ("fill", "none"),
                    ("stroke", color),
                    ("stroke-width", str(geometry["stroke_width_mark"])),
                ],
            )
        )
    for record, value in records:
        index = category_index[record.get("category")]
        x = _slot_center(index, len(categories), plot_left, plot_width)
        y = _y_position(value, low, high, plot_top, plot_height)
        color = _series_color(series.index(record.get("series")), geometry)
        parts.append(
            _el(
                "circle",
                [
                    ("cx", _px(x)),
                    ("cy", _px(y)),
                    ("r", str(geometry["line_radius"])),
                    ("fill", color),
                    ("data-rid", record.get("rendered_value_id")),
                    ("tabindex", "0"),
                ],
            )
        )


def _draw_scatter(parts, records, categories, series, domain, geometry):
    plot_left = geometry["margin_left"]
    plot_top = geometry["margin_top"]
    plot_width = geometry["canvas_width"] - geometry["margin_left"] - geometry["margin_right"]
    plot_height = geometry["canvas_height"] - geometry["margin_top"] - geometry["margin_bottom"]
    low, high = domain
    category_index = {value: index for index, value in enumerate(categories)}
    totals = {}
    for record, _ in records:
        key = (record.get("series"), record.get("category"))
        totals[key] = totals.get(key, 0) + 1
    seen = {}
    for record, value in records:
        key = (record.get("series"), record.get("category"))
        position = seen.get(key, 0)
        seen[key] = position + 1
        offset = Fraction(2 * position - (totals[key] - 1), 2) * geometry["scatter_stack_step"]
        x = _slot_center(category_index[record.get("category")], len(categories), plot_left, plot_width) + offset
        y = _y_position(value, low, high, plot_top, plot_height)
        color = _series_color(series.index(record.get("series")), geometry)
        parts.append(
            _el(
                "circle",
                [
                    ("cx", _px(x)),
                    ("cy", _px(y)),
                    ("r", str(geometry["scatter_radius"])),
                    ("fill", color),
                    ("data-rid", record.get("rendered_value_id")),
                    ("tabindex", "0"),
                ],
            )
        )


def _draw_box(parts, records, categories, series, domain, geometry, box_map):
    plot_left = geometry["margin_left"]
    plot_top = geometry["margin_top"]
    plot_width = geometry["canvas_width"] - geometry["margin_left"] - geometry["margin_right"]
    plot_height = geometry["canvas_height"] - geometry["margin_top"] - geometry["margin_bottom"]
    low, high = domain
    category_index = {value: index for index, value in enumerate(categories)}
    groups = []
    group_index = {}
    for record, value in records:
        key = (record.get("series"), record.get("category"))
        if key not in group_index:
            group_index[key] = len(groups)
            groups.append({"key": key, "records": [], "values": []})
        groups[group_index[key]]["records"].append(record)
        groups[group_index[key]]["values"].append(value)
    series_index = {value: index for index, value in enumerate(series)}
    box_width = geometry["box_width"]
    for group_number, group in enumerate(groups):
        group_series, category = group["key"]
        values = sorted(group["values"])
        minimum = values[0]
        maximum = values[-1]
        q1 = _quantile(values, 1, 4)
        median = _quantile(values, 1, 2)
        q3 = _quantile(values, 3, 4)
        base_x = _slot_center(category_index[category], len(categories), plot_left, plot_width)
        if len(series) > 1:
            offset = Fraction(2 * series_index[group_series] - (len(series) - 1), 2) * (
                box_width + geometry["bar_gap"]
            )
            base_x = base_x + offset
        color = _series_color(series_index.get(group_series, 0), geometry)
        top = _y_position(q3, low, high, plot_top, plot_height)
        bottom = _y_position(q1, low, high, plot_top, plot_height)
        min_y = _y_position(minimum, low, high, plot_top, plot_height)
        max_y = _y_position(maximum, low, high, plot_top, plot_height)
        cap = Fraction(geometry["box_whisker_cap"], 2)
        parts.append(
            _el(
                "line",
                [
                    ("x1", _px(base_x)),
                    ("y1", _px(max_y)),
                    ("x2", _px(base_x)),
                    ("y2", _px(min_y)),
                    ("stroke", color),
                    ("stroke-width", str(geometry["stroke_width_mark"])),
                ],
            )
        )
        for edge in (max_y, min_y):
            parts.append(
                _el(
                    "line",
                    [
                        ("x1", _px(base_x - cap)),
                        ("y1", _px(edge)),
                        ("x2", _px(base_x + cap)),
                        ("y2", _px(edge)),
                        ("stroke", color),
                        ("stroke-width", str(geometry["stroke_width_mark"])),
                    ],
                )
            )
        box_key = "box-%d" % group_number
        parts.append(
            _el(
                "rect",
                [
                    ("x", _px(base_x - Fraction(box_width, 2))),
                    ("y", _px(top)),
                    ("width", str(box_width)),
                    ("height", _px(bottom - top)),
                    ("fill", geometry["color_background"]),
                    ("stroke", color),
                    ("stroke-width", str(geometry["stroke_width_mark"])),
                    ("data-box", box_key),
                    ("tabindex", "0"),
                ],
            )
        )
        median_y = _y_position(median, low, high, plot_top, plot_height)
        parts.append(
            _el(
                "line",
                [
                    ("x1", _px(base_x - Fraction(box_width, 2))),
                    ("y1", _px(median_y)),
                    ("x2", _px(base_x + Fraction(box_width, 2))),
                    ("y2", _px(median_y)),
                    ("stroke", color),
                    ("stroke-width", str(geometry["box_median_stroke"])),
                ],
            )
        )
        box_map[box_key] = {
            "series": group_series,
            "category": category,
            "n": len(values),
            "min": _px(minimum),
            "q1": _px(q1),
            "median": _px(median),
            "q3": _px(q3),
            "max": _px(maximum),
            "record_ids": [record.get("rendered_value_id") for record in group["records"]],
        }
        totals = len(group["records"])
        for position, (record, value) in enumerate(zip(group["records"], group["values"])):
            offset = Fraction(2 * position - (totals - 1), 2) * geometry["scatter_stack_step"]
            x = base_x + offset
            y = _y_position(value, low, high, plot_top, plot_height)
            parts.append(
                _el(
                    "circle",
                    [
                        ("cx", _px(x)),
                        ("cy", _px(y)),
                        ("r", str(geometry["scatter_radius"])),
                        ("fill", color),
                        ("data-rid", record.get("rendered_value_id")),
                        ("tabindex", "0"),
                    ],
                )
            )


def _polar(cx, cy, radius, angle, geometry):
    radians = float(angle) * math.pi / geometry["pie_half_turn"]
    return cx + radius * math.cos(radians), cy + radius * math.sin(radians)


def _draw_pie(parts, records, categories, geometry):
    plot_left = geometry["margin_left"]
    plot_top = geometry["margin_top"]
    plot_width = geometry["canvas_width"] - geometry["margin_left"] - geometry["margin_right"]
    plot_height = geometry["canvas_height"] - geometry["margin_top"] - geometry["margin_bottom"]
    center_x = Fraction(plot_left) + Fraction(plot_width, 2)
    center_y = Fraction(plot_top) + Fraction(plot_height, 2)
    radius = geometry["pie_radius"]
    start = Fraction(geometry["pie_start_angle"])
    total = sum((value for _, value in records), Fraction(0))
    if total == 0:
        return
    full = Fraction(geometry["pie_full_angle"])
    for index, (record, value) in enumerate(records):
        angle = value * full / total
        if angle == 0:
            continue
        end = start + angle
        color = _series_color(index, geometry)
        if angle == full:
            parts.append(
                _el(
                    "circle",
                    [
                        ("cx", _px(center_x)),
                        ("cy", _px(center_y)),
                        ("r", str(radius)),
                        ("fill", color),
                        ("data-rid", record.get("rendered_value_id")),
                        ("tabindex", "0"),
                    ],
                )
            )
        else:
            x1, y1 = _polar(center_x, center_y, radius, start, geometry)
            x2, y2 = _polar(center_x, center_y, radius, end, geometry)
            large_arc = 1 if angle > geometry["pie_half_turn"] else 0
            path = "M %s %s L %s %s A %s %s 0 %d 1 %s %s Z" % (
                _px(center_x),
                _px(center_y),
                _coord(x1, geometry),
                _coord(y1, geometry),
                radius,
                radius,
                large_arc,
                _coord(x2, geometry),
                _coord(y2, geometry),
            )
            parts.append(
                _el(
                    "path",
                    [
                        ("d", path),
                        ("fill", color),
                        ("data-rid", record.get("rendered_value_id")),
                        ("tabindex", "0"),
                    ],
                )
            )
        mid = start + angle / 2
        label_x, label_y = _polar(center_x, center_y, geometry["pie_label_radius"], mid, geometry)
        parts.append(
            _text(
                _coord(label_x, geometry),
                _coord(label_y, geometry),
                record.get("rendered_label", ""),
                [
                    ("text-anchor", "middle"),
                    ("dominant-baseline", "central"),
                    ("font-size", str(geometry["font_size_label"])),
                    ("fill", geometry["color_text"]),
                ],
            )
        )
        start = end


def _draw_overlay_with_domain(parts, dots, anchors, domain, geometry, y_position, plot_top, plot_height):
    """overlay_scatter：散点位置由 provenance sources[] 提供，不重算（K29）。"""
    low, high = domain
    totals = {}
    for record, index, source, value in dots:
        key = (record.get("series"), record.get("category"))
        totals[key] = totals.get(key, 0) + 1
    seen = {}
    for record, index, source, value in dots:
        key = (record.get("series"), record.get("category"))
        position = seen.get(key, 0)
        seen[key] = position + 1
        offset = Fraction(2 * position - (totals[key] - 1), 2) * geometry["scatter_stack_step"]
        x = anchors.get(key, 0) + offset
        y = y_position(value, low, high, plot_top, plot_height)
        parts.append(
            _el(
                "circle",
                [
                    ("cx", _px(x)),
                    ("cy", _px(y)),
                    ("r", str(geometry["scatter_radius"])),
                    ("fill", geometry["color_text"]),
                    ("data-rid", record.get("rendered_value_id")),
                    ("data-source", str(index)),
                    ("tabindex", "0"),
                ],
            )
        )


def _render_svg(normalized_spec, provenance_obj, geometry):
    """返回 (svg 字符串, records 载荷映射, boxes 摘要映射)。"""
    mark = normalized_spec["mark"]
    records = _usable_records(provenance_obj)
    payload_map = {}
    for record, _ in records:
        payload_map[record.get("rendered_value_id")] = _payload(record)
    box_map = {}
    parts = []
    width = geometry["canvas_width"]
    height = geometry["canvas_height"]
    plot_left = geometry["margin_left"]
    plot_top = geometry["margin_top"]
    plot_width = width - geometry["margin_left"] - geometry["margin_right"]
    plot_height = height - geometry["margin_top"] - geometry["margin_bottom"]

    if not records:
        parts.append(
            _text(
                _px(Fraction(plot_left + plot_width, 2)),
                _px(Fraction(plot_top + plot_height, 2)),
                "无可用溯源记录（审计调试件仍输出审计区块）",
                [
                    ("text-anchor", "middle"),
                    ("dominant-baseline", "central"),
                    ("font-size", str(geometry["font_size_label"])),
                    ("fill", geometry["color_axis"]),
                ],
            )
        )
    else:
        categories = _category_order(records)
        series = _series_order(records)
        overlay = bool(normalized_spec.get("overlay_scatter")) and mark in (
            "bar",
            "line",
            "scatter",
        )
        dots = _overlay_dots(records) if overlay else []
        values = [value for _, value in records]
        values.extend(value for _, _, _, value in dots)
        y_zero = normalized_spec.get("y_zero", True) if mark == "bar" else False
        low, high = _y_domain(values, y_zero)
        if mark == "pie":
            _draw_pie(parts, records, categories, geometry)
            legend = [
                (
                    (record.get("category") if record.get("series") is None else "%s / %s" % (record.get("series"), record.get("category"))),
                    _series_color(index, geometry),
                )
                for index, (record, _) in enumerate(records)
            ]
            _draw_legend(parts, legend, geometry)
        else:
            ticks, low, high = _ticks(low, high, geometry["y_tick_count"])
            _draw_axes(parts, categories, ticks, (low, high), geometry)
            if mark == "bar":
                anchors = _draw_bar(parts, records, categories, series, (low, high), geometry)
                if overlay:
                    _draw_overlay_with_domain(
                        parts, dots, anchors, (low, high), geometry, _y_position, plot_top, plot_height
                    )
            elif mark == "line":
                _draw_line(parts, records, categories, series, (low, high), geometry)
            elif mark == "scatter":
                _draw_scatter(parts, records, categories, series, (low, high), geometry)
            elif mark == "box":
                _draw_box(
                    parts, records, categories, series, (low, high), geometry, box_map
                )
            legend_entries = []
            if mark != "box" and len(series) > 1:
                legend_entries = [
                    (name, _series_color(index, geometry))
                    for index, name in enumerate(series)
                    if name is not None
                ]
            _draw_legend(parts, legend_entries, geometry)

    svg = _el(
        "svg",
        [
            ("viewBox", "0 0 " + _px(width) + " " + _px(height)),
            ("width", str(width)),
            ("height", str(height)),
            ("role", "img"),
            ("aria-label", normalized_spec.get("title", "")),
        ],
        parts,
    )
    return svg, payload_map, box_map


def _draw_overlay_with_domain(parts, dots, anchors, domain, geometry, y_position, plot_top, plot_height):
    """overlay_scatter：散点位置由 provenance sources[] 提供，不重算（K29）。"""
    low, high = domain
    totals = {}
    for record, index, source, value in dots:
        key = (record.get("series"), record.get("category"))
        totals[key] = totals.get(key, 0) + 1
    seen = {}
    for record, index, source, value in dots:
        key = (record.get("series"), record.get("category"))
        position = seen.get(key, 0)
        seen[key] = position + 1
        offset = Fraction(2 * position - (totals[key] - 1), 2) * geometry["scatter_stack_step"]
        x = anchors.get(key, 0) + offset
        y = y_position(value, low, high, plot_top, plot_height)
        parts.append(
            _el(
                "circle",
                [
                    ("cx", _px(x)),
                    ("cy", _px(y)),
                    ("r", str(geometry["scatter_radius"])),
                    ("fill", geometry["color_text"]),
                    ("data-rid", record.get("rendered_value_id")),
                    ("data-source", str(index)),
                    ("tabindex", "0"),
                ],
            )
        )


# ---------------------------------------------------------------------------
# 审计区块
# ---------------------------------------------------------------------------


def _audit_items(provenance_report, audit_obj, gates_obj):
    order = list(audit_obj.get("severity_order") or gates_obj.get("severity_order") or ())
    items = []
    for finding in audit_obj.get("findings", []):
        items.append(
            {
                "severity": finding["severity"],
                "id": finding["rule_id"],
                "evidence_path": finding["evidence_path"],
                "message": finding["message"],
                "layer": "规则",
            }
        )
    for finding in gates_obj.get("findings", []):
        items.append(
            {
                "severity": finding["severity"],
                "id": finding["gate_id"],
                "evidence_path": finding["evidence_path"],
                "message": finding["message"],
                "layer": "门禁",
            }
        )
    for error in provenance_report.get("errors", []):
        items.append(
            {
                "severity": error.get("severity", order[0]),
                "id": error.get("gate_id", ""),
                "evidence_path": error.get("evidence_path", ""),
                "message": error.get("detail", ""),
                "layer": "溯源",
            }
        )
    order_index = {level: index for index, level in enumerate(order)}
    items.sort(
        key=lambda item: (
            order_index.get(item["severity"], len(order)),
            item["id"],
            item["evidence_path"],
            item["message"],
        )
    )
    return order, items


def _audit_section(provenance_report, audit_obj, gates_obj, geometry):
    order, items = _audit_items(provenance_report, audit_obj, gates_obj)
    counts = {level: 0 for level in order}
    for item in items:
        counts[item["severity"]] = counts.get(item["severity"], 0) + 1
    count_text = " ｜ ".join(
        "%s <b>%d</b>" % (level, counts[level]) for level in order
    )
    rows = []
    for item in items:
        rows.append(
            '<li class="severity-%s"><span class="sev">%s</span>'
            '<code>%s</code> <span class="path">%s</span>'
            '<span class="msg">%s</span></li>'
            % (
                _esc(item["severity"].lower()),
                _esc(item["severity"]),
                _esc(item["id"]),
                _esc(item["evidence_path"]),
                _esc(item["message"]),
            )
        )
    if not rows:
        rows.append('<li class="clean">未发现任何审计命中。</li>')
    return (
        '<section class="audit" id="chartaudit-audit" data-section="audit">'
        "<h2>审计结果</h2>"
        '<p class="counts">%s</p>'
        '<ul class="findings">%s</ul>'
        "</section>" % (count_text, "".join(rows))
    )


# ---------------------------------------------------------------------------
# HTML 组装
# ---------------------------------------------------------------------------


_CSS_TEMPLATE = """
:root { color-scheme: light; }
body { margin: 0; padding: %(spacing_medium)spx; background: %(color_background)s; color: %(color_text)s; font-family: "Segoe UI", "Microsoft YaHei", "PingFang SC", system-ui, sans-serif; }
.chartaudit { max-width: %(canvas_width)spx; margin: 0 auto; }
h1 { font-size: %(font_size_title)spx; margin: 0 0 %(spacing_small)spx 0; }
.meta { font-size: %(font_size_axis)spx; color: %(color_axis)s; margin: 0 0 %(spacing_medium)spx 0; word-break: break-all; }
.banner { background: %(color_banner)s; color: %(color_background)s; padding: %(spacing_small)spx %(spacing_medium)spx; margin: 0 0 %(spacing_medium)spx 0; border-radius: %(spacing_small)spx; font-size: %(font_size_label)spx; }
.chart { position: relative; margin: 0; }
.audit { margin-top: %(spacing_large)spx; border-top: %(stroke_width_axis)spx solid %(color_grid)s; padding-top: %(spacing_medium)spx; font-size: %(font_size_label)spx; }
.audit h2 { font-size: %(font_size_label)spx; margin: 0 0 %(spacing_small)spx 0; }
.counts { margin: 0 0 %(spacing_small)spx 0; color: %(color_axis)s; }
.findings { margin: 0; padding-left: %(spacing_medium)spx; }
.findings li { margin: 0 0 %(spacing_small)spx 0; }
.sev { font-weight: %(font_weight_bold)s; margin-right: %(spacing_small)spx; }
.severity-error .sev { color: %(color_banner)s; }
.path { color: %(color_axis)s; margin-right: %(spacing_small)spx; }
.tip { position: fixed; display: none; z-index: %(z_index_tip)s; width: %(hover_panel_width)spx; padding: %(spacing_small)spx; border-radius: %(spacing_small)spx; background: %(color_hover_panel)s; color: %(color_background)s; font-size: %(font_size_hover)spx; line-height: %(line_height_tip)s; pointer-events: none; }
.tip div { margin: 0; }
"""

_JS_TEMPLATE = """
(function () {
  var payloadNode = document.getElementById('chartaudit-provenance');
  var tip = document.getElementById('chartaudit-tip');
  if (!payloadNode || !tip) { return; }
  var payload = JSON.parse(payloadNode.textContent);
  var config = %(config)s;

  function makeLine(text) {
    var node = document.createElement('div');
    node.textContent = text;
    return node;
  }

  function clearTip() {
    while (tip.firstChild) { tip.removeChild(tip.firstChild); }
  }

  function positionTip(node, event) {
    var x = null;
    var y = null;
    if (event && typeof event.clientX === 'number') {
      x = event.clientX;
      y = event.clientY;
    } else {
      var rect = node.getBoundingClientRect();
      x = rect.left;
      y = rect.bottom;
    }
    tip.style.left = (x + config.cursor_offset) + 'px';
    tip.style.top = (y + config.cursor_offset) + 'px';
  }

  function showTip(node, event) {
    var record = payload.records[node.getAttribute('data-rid')];
    if (!record) { return; }
    clearTip();
    var sourceIndex = node.getAttribute('data-source');
    var csvLine = record.csv_line;
    var column = record.column;
    var rawCell = record.raw_cell;
    var extra = '';
    if (sourceIndex !== null) {
      var source = record.sources[parseInt(sourceIndex, 10)];
      if (source) {
        csvLine = source.csv_line;
        column = source.column;
        rawCell = source.raw_cell;
        extra = '（聚合记录 ' + record.rendered_value_id + ' 的第 ' + (parseInt(sourceIndex, 10) + 1) + ' 个源单元格）';
      }
    }
    tip.appendChild(makeLine('此值 ' + record.rendered_label + ' 来自第 ' + csvLine + ' 行「' + column + '」列' + extra));
    tip.appendChild(makeLine('原始单元格：' + rawCell));
    if (record.sources_count > 1) {
      var lines = [];
      for (var i = 0; i < record.sources.length; i += 1) {
        lines.push(record.sources[i].csv_line);
      }
      tip.appendChild(makeLine('聚合源：' + record.sources_count + ' 个单元格（第 ' + lines.join('、') + ' 行）'));
    }
    tip.appendChild(makeLine('变换链：' + record.transform_summary));
    tip.appendChild(makeLine('rendered_value_id：' + record.rendered_value_id));
    tip.style.display = 'block';
    positionTip(node, event);
  }

  function showBox(node, event) {
    var box = payload.boxes[node.getAttribute('data-box')];
    if (!box) { return; }
    clearTip();
    tip.appendChild(makeLine('箱线：' + box.category + '（' + box.n + ' 条逐观测记录）'));
    tip.appendChild(makeLine('min=' + box.min + ' ｜ q1=' + box.q1 + ' ｜ median=' + box.median + ' ｜ q3=' + box.q3 + ' ｜ max=' + box.max));
    tip.appendChild(makeLine('记录：' + box.record_ids.join('、')));
    tip.style.display = 'block';
    positionTip(node, event);
  }

  function hideTip() {
    tip.style.display = 'none';
  }

  function bind(node, show) {
    node.addEventListener('mouseenter', function (event) { show(node, event); });
    node.addEventListener('mousemove', function (event) { positionTip(node, event); });
    node.addEventListener('mouseleave', hideTip);
    node.addEventListener('focus', function (event) { show(node, event); });
    node.addEventListener('blur', hideTip);
  }

  var nodes = document.querySelectorAll('[data-rid]');
  for (var index = 0; index < nodes.length; index += 1) {
    bind(nodes[index], showTip);
  }
  var boxes = document.querySelectorAll('[data-box]');
  for (var boxIndex = 0; boxIndex < boxes.length; boxIndex += 1) {
    bind(boxes[boxIndex], showBox);
  }
}());
"""


def _css(geometry):
    return _CSS_TEMPLATE % geometry


def _js(geometry):
    config = {"cursor_offset": geometry["hover_cursor_offset"]}
    return _JS_TEMPLATE % {"config": json.dumps(config, separators=(",", ":"), sort_keys=True)}


def render_html(
    dataset,
    normalized_spec,
    provenance_obj,
    provenance_report,
    audit_obj,
    gates_obj,
    geometry_cfg=None,
    blocked=False,
    audit_debug=False,
):
    """生成单文件 HTML 文本（确定性：同输入两次调用逐字节一致）。"""
    if geometry_cfg is None:
        geometry_cfg = load_geometry()
    geometry = geometry_cfg["values"]
    spec_title = normalized_spec.get("title", "")
    page_title = spec_title + ("（审计调试件）" if audit_debug else "")
    svg, payload_map, box_map = _render_svg(normalized_spec, provenance_obj, geometry)
    audit_html = _audit_section(provenance_report, audit_obj, gates_obj, geometry)
    payload_json = json.dumps(
        {"records": payload_map, "boxes": box_map},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=False,
    ).replace("<", "\\u003c")

    lines = []
    lines.append("<!DOCTYPE html>")
    lines.append('<html lang="zh-CN">')
    lines.append("<head>")
    lines.append('<meta charset="utf-8">')
    lines.append("<title>%s</title>" % _esc(page_title))
    lines.append("<style>")
    lines.append(_css(geometry).strip("\n"))
    lines.append("</style>")
    lines.append("</head>")
    lines.append("<body>")
    lines.append('<div class="chartaudit">')
    lines.append("<h1>%s</h1>" % _esc(spec_title))
    source = provenance_obj.get("source") or {}
    lines.append(
        '<p class="meta">spec_id：<code>%s</code> ｜ mark：%s ｜ 源文件：%s ｜ SHA-256：<code>%s</code></p>'
        % (
            _esc(provenance_obj.get("spec_id", "")),
            _esc(normalized_spec.get("mark", "")),
            _esc(source.get("name", "")),
            _esc(source.get("sha256", "")),
        )
    )
    if blocked:
        banner = (
            '<div class="banner" role="alert"><strong>审计阻断</strong>：存在 ERROR 级命中，'
            "默认不产出可发布 HTML。"
        )
        if audit_debug:
            banner += "本文件由 --emit-audit-html 生成，是审计调试件，不可作为发布产物。"
        banner += "</div>"
        lines.append(banner)
    lines.append('<div class="chart" data-section="chart">')
    lines.append(svg)
    lines.append('<div class="tip" id="chartaudit-tip" role="tooltip"></div>')
    lines.append("</div>")
    lines.append(audit_html)
    lines.append(
        '<script type="application/json" id="chartaudit-provenance" '
        'data-section="provenance-data">%s</script>' % payload_json
    )
    lines.append("<script>%s</script>" % _js(geometry).strip("\n"))
    lines.append("</div>")
    lines.append("</body>")
    lines.append("</html>")
    return "\n".join(lines) + "\n"
