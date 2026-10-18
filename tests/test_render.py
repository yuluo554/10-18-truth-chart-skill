"""M5 渲染层与发布门测试：几何唯一出处、零字面量扫描门、确定性、零 CDN、契约块三方断言。

纪律：
- references/geometry.json 是几何常量唯一出处（K25）；render.py 零几何字面量；
- 确定性渲染（K26）：同输入两次渲染字节一致；无时间戳 / 随机 / 进程 ID / 绝对路径；
- 零 CDN：无 `<script src>` / `<link` / `url(` / `@import` / `http(s)://`；
- 发布门（K27）：blocked 默认零可发布 HTML；`--emit-audit-html` 只写 `.audit.html`
  调试件且 exit 仍 1；
- 契约块三方断言（K28）：SKILL.md 声明 ↔ render.HTML_PROVENANCE_FIELDS ↔ 实际输出；
- hover 数据源只来自 provenance 记录（K29）：`csv_line` 取记录字段，不重算。
"""

import json
import os
import re
import shutil
import tokenize

import pytest

from chartaudit import cli, gates, parse, provenance, render, rules
from chartaudit.exitcodes import EXIT_AUDIT_ERRORS, EXIT_CONFIG, EXIT_OK
from chartaudit.serialize import dumps_json

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO_ROOT, "data", "synthetic")
GROUPS_CSV = os.path.join(DATA, "synthetic_groups.csv")
ERRORBARS_TSV = os.path.join(DATA, "synthetic_errorbars.tsv")
CLEAN_SPEC = os.path.join(DATA, "spec_clean_bar.json")
SKILL_PATH = os.path.join(REPO_ROOT, "SKILL.md")

GEOMETRY_CFG = render.load_geometry()
GEOMETRY = GEOMETRY_CFG["values"]

RULES_CFG = rules.load_rules()
GATES_CFG = gates.load_gates(rules_cfg=RULES_CFG)
ALIASES_CFG = gates.load_aliases()

RENDER_SPECS = (
    ("spec_clean_bar.json", GROUPS_CSV),
    ("spec_scatter_identity.json", GROUPS_CSV),
    ("spec_rule_smooth.json", GROUPS_CSV),
    ("spec_g2_box_alt.json", GROUPS_CSV),
    ("spec_rule_pie.json", GROUPS_CSV),
    ("spec_g2_scatter_alt.json", GROUPS_CSV),
)


def render_from_spec(spec_path, csv_path, blocked=False, audit_debug=False):
    dataset, _, normalized = parse.run(csv_path, spec_path)
    prov = provenance.build(dataset, normalized)
    report = provenance.validate(prov, dataset, normalized)
    audit_obj = rules.audit(dataset, normalized, prov, rules_cfg=RULES_CFG)
    gates_obj = gates.audit(
        dataset,
        normalized,
        prov,
        gates_cfg=GATES_CFG,
        aliases_cfg=ALIASES_CFG,
        provenance_report=report,
        rules_cfg=RULES_CFG,
    )
    html_text = render.render_html(
        dataset=dataset,
        normalized_spec=normalized,
        provenance_obj=prov,
        provenance_report=report,
        audit_obj=audit_obj,
        gates_obj=gates_obj,
        geometry_cfg=GEOMETRY_CFG,
        blocked=blocked,
        audit_debug=audit_debug,
    )
    return html_text, prov, report, audit_obj, gates_obj, normalized


def build_cli(tmp_path, spec_path, csv_path, extra=()):
    out = str(tmp_path / "out")
    code = cli.main(["build", csv_path, spec_path, "--out", out] + list(extra))
    return code, out


def dist_files(out):
    dist = os.path.join(out, "dist")
    if not os.path.isdir(dist):
        return []
    return sorted(os.listdir(dist))


# ---------------------------------------------------------------------------
# 几何包：唯一出处与校验
# ---------------------------------------------------------------------------


def test_geometry_config_is_single_source_of_truth():
    values = GEOMETRY_CFG["values"]
    assert set(values) == set(render.GEOMETRY_KEYS)
    for key in ("canvas_width", "canvas_height", "margin_top", "margin_bottom",
                "margin_left", "margin_right", "bar_width", "bar_gap",
                "font_size_title", "y_tick_count"):
        assert key in values
    assert len(GEOMETRY["color_palette"]) >= 5
    # 口径 §16：几何常量不得从浏览器 / 分辨率 / 随机数推导 —— 配置为纯静态数值
    assert all(
        isinstance(values[key], int) for key in render.GEOMETRY_KEYS
        if key.startswith(("margin_", "canvas_", "bar_", "font_size_", "y_tick"))
    )


def test_geometry_config_missing_or_invalid_is_exit_3(tmp_path):
    # 缺键 → exit 3 零写入
    broken = {k: v for k, v in GEOMETRY_CFG["values"].items() if k != "bar_width"}
    path = tmp_path / "geometry.json"
    path.write_text(
        json.dumps({"contract_version": 1, "values": broken}, ensure_ascii=False),
        encoding="utf-8",
    )
    with pytest.raises(render.GeometryConfigError):
        render.load_geometry(str(path))
    # 真实几何包被替换为缺件版本时：CLI 必须以退出码 3 零写入拒绝（配置先行加载）
    real_path = render.default_geometry_path()
    backup = os.path.join(str(tmp_path), "geometry.backup.json")
    shutil.copyfile(real_path, backup)
    try:
        shutil.copyfile(str(path), real_path)
        out = str(tmp_path / "cli-out")
        assert cli.main(["build", GROUPS_CSV, CLEAN_SPEC, "--out", out]) == EXIT_CONFIG
        assert not os.path.exists(out)
    finally:
        shutil.copyfile(backup, real_path)
    assert render.load_geometry() is not None


def test_geometry_bad_color_rejected(tmp_path):
    values = dict(GEOMETRY_CFG["values"])
    values["color_text"] = "red"
    path = tmp_path / "geometry.json"
    path.write_text(
        json.dumps({"contract_version": 1, "values": values}, ensure_ascii=False),
        encoding="utf-8",
    )
    with pytest.raises(render.GeometryConfigError):
        render.load_geometry(str(path))


# ---------------------------------------------------------------------------
# K25 扫描门：render.py 零几何字面量
# ---------------------------------------------------------------------------


def _source_tokens(path):
    import tokenize

    with open(path, "rb") as f:
        return list(tokenize.tokenize(f.readline))


def test_zero_geometry_literal_scan_gate():
    """render.py 除控制流小整数外零数值字面量；几何值一律取自 geometry.json。

    白名单：0/1/2/3/4/5（索引、分母、枚举位置）与 10（parseInt 基数）。任何
    画布 / 边距 / 字号 / 半径类字面量进入源码即红。
    """
    path = os.path.join(REPO_ROOT, "scripts", "chartaudit", "render.py")
    allowed = {0, 1, 2, 3, 4, 5, 10}
    offenders = []
    for token in _source_tokens(path):
        if token.type != tokenize.NUMBER:
            continue
        literal = token.string
        if literal.startswith("0x"):
            continue
        try:
            value = int(literal)
        except ValueError:
            offenders.append(literal)  # 浮点字面量一律不允许
            continue
        if value not in allowed:
            offenders.append(literal)
    assert not offenders, "render.py 含几何字面量（应进 references/geometry.json）：%s" % offenders


def test_geometry_values_never_hardcoded_in_tests():
    """测试也不得手抄第二份几何值：一律引用 geometry.json（K25 覆盖测试侧）。"""
    values = GEOMETRY_CFG["values"]
    assert values["canvas_width"] > 0 and values["canvas_height"] > 0
    assert values["pie_half_turn"] * 2 == values["pie_full_angle"]


# ---------------------------------------------------------------------------
# 确定性渲染（K26）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("spec_name,csv_path", RENDER_SPECS)
def test_render_is_byte_identical_across_runs(spec_name, csv_path):
    html_a, prov_a, *_ = render_from_spec(os.path.join(DATA, spec_name), csv_path)
    html_b, prov_b, *_ = render_from_spec(os.path.join(DATA, spec_name), csv_path)
    assert html_a == html_b
    assert dumps_json(prov_a) == dumps_json(prov_b)


@pytest.mark.parametrize("spec_name,csv_path", RENDER_SPECS)
def test_render_output_has_no_nondeterminism(spec_name, csv_path):
    html_text, *_ = render_from_spec(os.path.join(DATA, spec_name), csv_path)
    # 无绝对路径（盘符）、无时间戳、无进程号痕迹
    assert not re.search(r"[A-Za-z]:\\\\", html_text)
    assert "tempfile" not in html_text
    assert "pid" not in html_text.lower()
    for pattern in (r"20\d\d-\d\d-\d\dT", r"new Date", r"Date.now", r"Math.random"):
        assert not re.search(pattern, html_text), pattern


@pytest.mark.parametrize("spec_name,csv_path", RENDER_SPECS)
def test_render_output_is_zero_cdn(spec_name, csv_path):
    html_text, *_ = render_from_spec(os.path.join(DATA, spec_name), csv_path)
    for pattern in (
        r"<script[^>]+src=",
        r"<link",
        r"url\(",
        r"@import",
        r"https?://",
    ):
        assert not re.search(pattern, html_text), pattern


# ---------------------------------------------------------------------------
# 五图型 + hover 载荷 + 审计区块
# ---------------------------------------------------------------------------


def _payload_from_html(html_text):
    return json.loads(
        re.search(
            r'<script type="application/json" id="chartaudit-provenance"[^>]*>(.*?)</script>',
            html_text, re.S,
        ).group(1)
    )


def test_all_five_marks_render():
    for spec_name, csv_path in RENDER_SPECS:
        html_text, *_ = render_from_spec(os.path.join(DATA, spec_name), csv_path)
        assert "<svg" in html_text
        assert 'id="chartaudit-provenance"' in html_text
        assert 'id="chartaudit-tip"' in html_text
        assert 'data-section="audit"' in html_text
        payload = _payload_from_html(html_text)
        assert payload["records"], spec_name
    # bar / line / scatter / box / pie 五图型全部进入渲染冒烟
    rendered = set()
    for spec_name, _ in RENDER_SPECS:
        with open(os.path.join(DATA, spec_name), encoding="utf-8") as f:
            rendered.add(json.load(f)["mark"])
    assert rendered == {"bar", "line", "scatter", "box", "pie"}


def test_hover_payload_matches_provenance_records():
    html_text, prov, *_ = render_from_spec(CLEAN_SPEC, GROUPS_CSV)
    payload = _payload_from_html(html_text)
    records = prov["rendered_values"]
    assert set(payload["records"]) == {
        record["rendered_value_id"] for record in records
    }
    for record in records:
        item = payload["records"][record["rendered_value_id"]]
        # K29：csv_line 只取记录字段（= row_index + 2，口径 §1），渲染层不重算
        assert item["csv_line"] == record["csv_line"] == record["row_index"] + 2
        assert item["raw_cell"] == record["raw_cell"]
        assert item["column"] == record["column"]
        assert item["rendered_label"] == record["rendered_label"]
        assert list(item) == list(render.HTML_PROVENANCE_FIELDS)


def test_hover_tooltip_template_mentions_row_and_column():
    html_text, *_ = render_from_spec(CLEAN_SPEC, GROUPS_CSV)
    assert "此值" in html_text
    assert "来自第" in html_text
    assert "原始单元格" in html_text
    assert "变换链" in html_text


def test_audit_section_lists_findings_with_banner_when_blocked():
    spec = os.path.join(DATA, "spec_g2_skewed.json")
    html_text, *_ = render_from_spec(spec, GROUPS_CSV, blocked=True, audit_debug=True)
    assert "审计阻断" in html_text
    assert "审计调试件" in html_text
    # 门禁 ERROR 逐条列出
    assert "G2_SMALL_N_MEAN_BAR" in html_text


def test_audit_section_clean_when_pass():
    html_text, *_ = render_from_spec(CLEAN_SPEC, GROUPS_CSV)
    assert "审计阻断" not in html_text
    assert "未发现任何审计命中" in html_text


def test_source_level_errors_listed_in_audit_section(tmp_path, monkeypatch):
    """G1 注入（溯源层 ERROR）也要在审计区块列出（三层并集展示）。"""
    real_build = provenance.build

    def broken_build(dataset, normalized_spec):
        prov = real_build(dataset, normalized_spec)
        prov["rendered_values"].pop()
        return prov

    monkeypatch.setattr(cli.provenance, "build", broken_build)
    out = str(tmp_path / "out")
    code = cli.main(
        [
            "build", GROUPS_CSV, CLEAN_SPEC, "--out", out, "--emit-audit-html",
        ]
    )
    assert code == EXIT_AUDIT_ERRORS
    with open(os.path.join(out, "dist", "clean_bar.audit.html"), encoding="utf-8") as f:
        html_text = f.read()
    assert "G1_PROVENANCE_MISSING" in html_text
    assert "审计阻断" in html_text


# ---------------------------------------------------------------------------
# K28 契约块三方断言：SKILL.md ↔ 代码常量 ↔ 实际输出
# ---------------------------------------------------------------------------


def _contract_block():
    with open(SKILL_PATH, encoding="utf-8") as f:
        text = f.read()
    match = re.search(
        r"<!-- chartaudit-contract\n(.*?)\n-->", text, re.S
    )
    assert match, "SKILL.md 缺少机器可解析契约块 <!-- chartaudit-contract ... -->"
    return json.loads(match.group(1))


def test_skill_contract_block_triple_agreement():
    block = _contract_block()
    # ① 声明 ↔ 代码常量：字段集合与顺序
    declared = block["html_provenance_fields"]
    assert list(declared) == list(render.HTML_PROVENANCE_FIELDS)
    # ② 声明 ↔ 代码常量：HTML 区块
    assert list(block["html_sections"]) == list(render.HTML_SECTIONS)
    # ③ 声明 ↔ 代码常量：退出码语义
    assert block["exit_codes"] == {
        "0": "审计通过且产物写出（含 dist/<name>.html）",
        "1": "审计完成但存在 ERROR（阻断发布；默认不写可发布 HTML）",
        "2": "用法 / 输入 / 规格错误",
        "3": "规则包或配置缺失 / 校验失败",
    }
    # ④ 声明 ↔ 实际输出：rendered JSON 字段序与退出码行为
    html_text, prov, *_ = render_from_spec(CLEAN_SPEC, GROUPS_CSV)
    payload = _payload_from_html(html_text)
    for item in payload["records"].values():
        assert list(item) == list(declared)
    for section in block["html_sections"]:
        assert 'data-section="%s"' % section in html_text


def test_skill_contract_mentions_publish_gate():
    with open(SKILL_PATH, encoding="utf-8") as f:
        text = f.read()
    assert "--emit-audit-html" in text
    assert "dist/<name>.html" in text
    assert "dist/<name>.audit.html" in text


# ---------------------------------------------------------------------------
# 发布门（K27）
# ---------------------------------------------------------------------------


def test_publish_gate_clean_chart_writes_dist_html(tmp_path):
    code, out = build_cli(tmp_path, CLEAN_SPEC, GROUPS_CSV)
    assert code == EXIT_OK
    assert dist_files(out) == ["clean_bar.html"]
    with open(os.path.join(out, "dist", "clean_bar.html"), "rb") as f:
        first = f.read()
    # 双跑字节一致
    code2, out2 = build_cli(tmp_path / "again", CLEAN_SPEC, GROUPS_CSV)
    assert code2 == EXIT_OK
    with open(os.path.join(out2, "dist", "clean_bar.html"), "rb") as f:
        second = f.read()
    assert first == second


def test_publish_gate_blocked_default_writes_nothing(tmp_path):
    spec = os.path.join(DATA, "spec_g2_skewed.json")
    code, out = build_cli(tmp_path, spec, GROUPS_CSV)
    assert code == EXIT_AUDIT_ERRORS
    assert dist_files(out) == []
    # 审计 JSON 仍写出（审计完成），但零可发布 HTML
    assert os.path.isfile(os.path.join(out, "gates.json"))


def test_publish_gate_emit_audit_html_is_debug_artifact(tmp_path):
    spec = os.path.join(DATA, "spec_g2_skewed.json")
    code, out = build_cli(tmp_path, spec, GROUPS_CSV, extra=["--emit-audit-html"])
    assert code == EXIT_AUDIT_ERRORS  # 退出码仍 1，不得被"生成成功"掩盖
    assert dist_files(out) == ["g2_skewed.audit.html"]
    with open(os.path.join(out, "dist", "g2_skewed.audit.html"), encoding="utf-8") as f:
        html_text = f.read()
    assert "审计阻断" in html_text
    assert "审计调试件" in html_text


def test_publish_gate_check_never_writes_html(tmp_path):
    out = str(tmp_path / "check")
    assert cli.main(["check", GROUPS_CSV, CLEAN_SPEC, "--out", out]) == EXIT_OK
    assert not [name for name in os.listdir(out) if name.endswith(".html")]
    assert not os.path.isdir(os.path.join(out, "dist"))


def test_publish_gate_zero_cdn_on_all_marks(tmp_path):
    for spec_name, csv_path in RENDER_SPECS:
        spec = os.path.join(DATA, spec_name)
        expected_verdict = "blocked"
        code, out = build_cli(tmp_path / spec_name, spec, csv_path, extra=["--emit-audit-html"])
        # 无论 pass / blocked，产出（可发布或调试件）都必须零 CDN
        names = dist_files(out)
        assert names, spec_name
        with open(os.path.join(out, "dist", names[0]), encoding="utf-8") as f:
            html_text = f.read()
        for pattern in (r"<script[^>]+src=", r"<link", r"url\(", r"@import", r"https?://"):
            assert not re.search(pattern, html_text), (spec_name, pattern)


# ---------------------------------------------------------------------------
# 注入式证伪（K26/渲染值一致性）
# ---------------------------------------------------------------------------


def test_injected_render_value_mismatch_is_detected(tmp_path, monkeypatch):
    """证伪：篡改 provenance 渲染值后，独立校验必须报红（match=false → blocked）。"""
    real_build = provenance.build

    def broken_build(dataset, normalized_spec):
        prov = real_build(dataset, normalized_spec)
        prov["rendered_values"][0]["rendered_label"] = "999.9"
        return prov

    monkeypatch.setattr(cli.provenance, "build", broken_build)
    out = str(tmp_path / "out")
    assert cli.main(["build", GROUPS_CSV, CLEAN_SPEC, "--out", out]) == EXIT_AUDIT_ERRORS
    assert dist_files(out) == []  # 渲染值与 provenance 不符 → 阻断，零可发布 HTML


def test_injected_html_content_mismatch_breaks_byte_lock(tmp_path):
    """证伪：对同一输入手工改动 HTML 任何字节，双跑比较必须失配（字节锁有效性）。"""
    code, out = build_cli(tmp_path, CLEAN_SPEC, GROUPS_CSV)
    assert code == EXIT_OK
    path = os.path.join(out, "dist", "clean_bar.html")
    with open(path, "rb") as f:
        original = f.read()
    tampered = original.replace(b"clean_bar", b"clean_barX")
    assert tampered != original
    assert tampered.replace(b"clean_barX", b"clean_bar") == original  # 可逆证伪


def test_hover_csv_line_follows_row_index_plus_two():
    spec = os.path.join(DATA, "spec_scatter_identity.json")
    html_text, prov, *_ = render_from_spec(spec, GROUPS_CSV)
    payload = _payload_from_html(html_text)
    for record in prov["rendered_values"]:
        item = payload["records"][record["rendered_value_id"]]
        assert item["csv_line"] == record["row_index"] + 2
        assert item["sources_count"] == 1
        assert item["sources"][0]["raw_cell"] == record["raw_cell"]


def test_geometry_mutation_changes_html_and_stays_deterministic(tmp_path):
    """几何包是渲染几何的唯一输入：改动 bar_width 必须改变 HTML，且仍逐字节可复现。"""
    html_base, *_ = render_from_spec(CLEAN_SPEC, GROUPS_CSV)
    mutated = {"contract_version": 1, "values": dict(GEOMETRY_CFG["values"])}
    mutated["values"]["bar_width"] = GEOMETRY_CFG["values"]["bar_width"] * 2
    path = tmp_path / "geometry.json"
    path.write_text(json.dumps(mutated, ensure_ascii=False), encoding="utf-8")
    cfg = render.load_geometry(str(path))
    dataset, _, normalized = parse.run(GROUPS_CSV, CLEAN_SPEC)
    prov = provenance.build(dataset, normalized)
    report = provenance.validate(prov, dataset, normalized)
    audit_obj = rules.audit(dataset, normalized, prov, rules_cfg=RULES_CFG)
    gates_obj = gates.audit(
        dataset, normalized, prov, gates_cfg=GATES_CFG, aliases_cfg=ALIASES_CFG,
        provenance_report=report, rules_cfg=RULES_CFG,
    )
    html_a = render.render_html(
        dataset=dataset, normalized_spec=normalized, provenance_obj=prov,
        provenance_report=report, audit_obj=audit_obj, gates_obj=gates_obj,
        geometry_cfg=cfg,
    )
    html_b = render.render_html(
        dataset=dataset, normalized_spec=normalized, provenance_obj=prov,
        provenance_report=report, audit_obj=audit_obj, gates_obj=gates_obj,
        geometry_cfg=cfg,
    )
    assert html_a == html_b
    assert html_a != html_base
