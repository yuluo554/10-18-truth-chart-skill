"""M3 规则门禁：dataset + chart_spec.normalized + provenance → audit.json。

纪律（唯一口径见 data/README.md 第四节；对齐标注见题面 §七）：
- 本规则集与已有开源实现高度重叠，属**对齐已有工作，非创新**；标注唯一出处为规则包
  `alignment` 字段，audit.json 原样携带；
- rule_id / 严重级别 / 证据路径 / 阈值 / 文案全部来自 `references/rules.json`，
  本模块零规则字面量（扫描门见 tests/test_rules.py）；
- 规则层只读 M1 产物与 M2 provenance：不重算渲染值、不改 match、不读网络 / 时钟 / 随机；
- 规则包登记顺序即固定执行顺序；输出按（级别序, rule_id, evidence_path）排序；
- verdict=blocked 当且仅当存在级别等于 `block_on` 的命中；配置缺失 / 非法 → 退出码 3，
  绝不静默按"零规则"通过；
- 规格合法性（非法 mark / 未知字段等）由解析层以退出码 2 拦截，规则层不二次改判。
"""

import datetime
import json
import os
from fractions import Fraction

from .exitcodes import EXIT_AUDIT_ERRORS, EXIT_OK
from .provenance import format_value, round_half_up

CONTRACT_VERSION = 1

DATE_COLUMN_TYPE = "date"


class RulesConfigError(Exception):
    """规则包缺失 / 校验失败，映射退出码 3。"""


# ---------------------------------------------------------------------------
# 规则包加载（references/rules.json 是 rule_id / 级别 / 阈值 / 证据路径的唯一出处）
# ---------------------------------------------------------------------------


def default_rules_path():
    """仓库根下 references/rules.json（Skill 交付态布局，D20：不发布 PyPI）。"""
    repo_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    return os.path.join(repo_root, "references", "rules.json")


def load_rules(path=None):
    """读取并校验规则包；任何缺失 / 非法 → RulesConfigError（退出码 3）。"""
    if path is None:
        path = default_rules_path()
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as exc:
        raise RulesConfigError("无法读取规则包 %s：%s" % (path, exc))
    try:
        config = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise RulesConfigError("规则包不是合法 UTF-8 JSON：%s" % exc)
    if not isinstance(config, dict):
        raise RulesConfigError("规则包必须是 JSON 对象")
    if config.get("contract_version") != CONTRACT_VERSION:
        raise RulesConfigError(
            "contract_version=%r（期望 %d）"
            % (config.get("contract_version"), CONTRACT_VERSION)
        )

    order = config.get("severity_order")
    if (
        not isinstance(order, list)
        or not order
        or not all(isinstance(level, str) and level for level in order)
        or len(set(order)) != len(order)
    ):
        raise RulesConfigError("severity_order 必须是非空、唯一的字符串列表")
    if config.get("block_on") not in order:
        raise RulesConfigError("block_on 必须在 severity_order 内")
    if not isinstance(config.get("alignment"), str) or not config["alignment"]:
        raise RulesConfigError("alignment 缺失（K14：对齐已有工作标注是验收硬条件）")

    entries = config.get("rules")
    if not isinstance(entries, list) or not entries:
        raise RulesConfigError("rules 必须是非空列表")
    seen_ids = set()
    seen_checks = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise RulesConfigError("规则项必须是对象：%r" % (entry,))
        for key in ("rule_id", "check", "severity", "evidence_path", "title", "message"):
            if not isinstance(entry.get(key), str) or not entry[key]:
                raise RulesConfigError(
                    "规则项缺少有效字段 %s：%r" % (key, entry.get(key))
                )
        if entry["severity"] not in order:
            raise RulesConfigError(
                "规则 %s 的 severity=%r 不在 severity_order 内"
                % (entry["rule_id"], entry["severity"])
            )
        if entry["check"] not in CHECKERS:
            raise RulesConfigError(
                "规则 %s 引用未知检查器 %r（已实现：%s）"
                % (entry["rule_id"], entry["check"], ", ".join(sorted(CHECKERS)))
            )
        if entry["rule_id"] in seen_ids:
            raise RulesConfigError("rule_id 重复：%s" % entry["rule_id"])
        if entry["check"] in seen_checks:
            raise RulesConfigError(
                "检查器 %s 被多条规则重复登记（一检查一规则）" % entry["check"]
            )
        thresholds = entry.get("thresholds")
        if thresholds is not None and not isinstance(thresholds, dict):
            raise RulesConfigError("规则 %s 的 thresholds 必须是对象" % entry["rule_id"])
        seen_ids.add(entry["rule_id"])
        seen_checks.add(entry["check"])
    missing_checks = set(CHECKERS) - seen_checks
    if missing_checks:
        raise RulesConfigError(
            "规则包未覆盖全部已实现检查器，缺少：%s"
            % ", ".join(sorted(missing_checks))
        )
    return config


# ---------------------------------------------------------------------------
# 九条规则（纯函数：返回 evidence dict 表示命中，None 表示不适用 / 未命中）
# ---------------------------------------------------------------------------


def _check_bar_nonzero_baseline(dataset, normalized_spec, provenance_obj, rule):
    if normalized_spec["mark"] != "bar":
        return None
    if normalized_spec.get("y_zero") is not False:
        return None
    return {"mark": "bar", "y_zero": False}


def _check_dual_y_axis(dataset, normalized_spec, provenance_obj, rule):
    if normalized_spec.get("dual_y") is not True:
        return None
    return {"dual_y": True}


def _check_pie_sectors_sum(dataset, normalized_spec, provenance_obj, rule):
    if normalized_spec["mark"] != "pie":
        return None
    thresholds = rule.get("thresholds") or {}
    max_sectors = thresholds.get("max_sectors")
    if not isinstance(max_sectors, int) or max_sectors <= 0:
        raise RulesConfigError(
            "规则 %s 缺少有效 thresholds.max_sectors" % rule.get("rule_id")
        )
    records = provenance_obj.get("rendered_values") or []
    evidence = {"sector_count": len(records), "max_sectors": max_sectors}
    hit = len(records) > max_sectors

    values = []
    for record in records:
        try:
            values.append(Fraction(record["exact_value"]))
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            values = []
            break
    if values:
        total = sum(values, Fraction(0))
        if total != 0:
            decimals = normalized_spec["encoding"]["y"].get("decimals")
            total_percent = Fraction(0)
            for value in values:
                percent = value * 100 / total
                if decimals is not None:
                    percent = round_half_up(percent, decimals)
                total_percent += percent
            evidence["percent_sum"] = format_value(total_percent, decimals)
            evidence["decimals"] = decimals
            if total_percent != 100:
                hit = True
    return evidence if hit else None


def _check_pseudo_3d(dataset, normalized_spec, provenance_obj, rule):
    if normalized_spec.get("pseudo_3d") is not True:
        return None
    return {"pseudo_3d": True}


def _check_radius_encoding(dataset, normalized_spec, provenance_obj, rule):
    if normalized_spec.get("size_channel") != "radius":
        return None
    return {"mark": normalized_spec["mark"], "size_channel": "radius"}


def _check_smooth_overshoot(dataset, normalized_spec, provenance_obj, rule):
    if normalized_spec.get("smooth") is not True:
        return None
    return {"mark": normalized_spec["mark"], "smooth": True}


def _check_time_axis_uneven(dataset, normalized_spec, provenance_obj, rule):
    if normalized_spec["mark"] == "pie":
        return None
    x_field = normalized_spec["encoding"]["x"]["field"]
    column_types = {column["name"]: column["type"] for column in dataset["columns"]}
    if column_types.get(x_field) != DATE_COLUMN_TYPE:
        return None

    categories = []
    seen = set()
    for record in provenance_obj.get("rendered_values") or []:
        category = record.get("category")
        if category is None or category in seen:
            continue
        seen.add(category)
        categories.append(category)
    dates = []
    for category in categories:
        try:
            year, month, day = (int(part) for part in category.split("-"))
            dates.append(datetime.date(year, month, day))
        except (AttributeError, TypeError, ValueError):
            return None  # 非法日期串：不可判定，不命中
    if len(dates) < 2:
        return None
    ordered = sorted(dates)
    gaps = [(later - earlier).days for earlier, later in zip(ordered, ordered[1:])]
    if all(gap == gaps[0] for gap in gaps):
        return None
    return {"field": x_field, "value_count": len(dates), "gaps": gaps}


def _check_low_contrast(dataset, normalized_spec, provenance_obj, rule):
    if normalized_spec.get("low_contrast") is not True:
        return None
    return {"low_contrast": True}


def _check_spec_invalid(dataset, normalized_spec, provenance_obj, rule):
    # K15：规格合法性由解析层以退出码 2 拦截；规则层不得二次报错或改判退出码。
    return None


CHECKERS = {
    "bar_nonzero_baseline": _check_bar_nonzero_baseline,
    "dual_y_axis": _check_dual_y_axis,
    "pie_sectors_sum": _check_pie_sectors_sum,
    "pseudo_3d": _check_pseudo_3d,
    "radius_encoding": _check_radius_encoding,
    "smooth_overshoot": _check_smooth_overshoot,
    "time_axis_uneven": _check_time_axis_uneven,
    "low_contrast": _check_low_contrast,
    "spec_invalid": _check_spec_invalid,
}


# ---------------------------------------------------------------------------
# 审计入口
# ---------------------------------------------------------------------------


def audit(dataset, normalized_spec, provenance_obj, rules_cfg=None):
    """执行九条规则，返回 audit.json 对象（含排序、级别计数与 verdict）。"""
    if rules_cfg is None:
        rules_cfg = load_rules()
    order = {
        level: index for index, level in enumerate(rules_cfg["severity_order"])
    }
    block_on = rules_cfg["block_on"]

    findings = []
    for entry in rules_cfg["rules"]:  # 规则包登记顺序 = 固定执行顺序
        checker = CHECKERS[entry["check"]]
        evidence = checker(dataset, normalized_spec, provenance_obj, entry)
        if evidence is None:
            continue
        findings.append(
            {
                "rule_id": entry["rule_id"],
                "severity": entry["severity"],
                "evidence_path": entry["evidence_path"],
                "evidence": evidence,
                "message": entry["message"],
            }
        )

    findings.sort(
        key=lambda finding: (
            order[finding["severity"]],
            finding["rule_id"],
            finding["evidence_path"],
        )
    )

    counts = {level: 0 for level in rules_cfg["severity_order"]}
    for finding in findings:
        counts[finding["severity"]] += 1
    counts["total"] = len(findings)

    blocked = any(finding["severity"] == block_on for finding in findings)
    return {
        "contract_version": CONTRACT_VERSION,
        "spec_id": normalized_spec["spec_id"],
        "mark": normalized_spec["mark"],
        "source": {
            "name": provenance_obj["source"]["name"],
            "sha256": provenance_obj["source"]["sha256"],
        },
        "alignment": rules_cfg["alignment"],
        "severity_order": list(rules_cfg["severity_order"]),
        "block_on": block_on,
        "counts": counts,
        "findings": findings,
        "verdict": "blocked" if blocked else "pass",
        "render_allowed": not blocked,
        "exit_code": EXIT_AUDIT_ERRORS if blocked else EXIT_OK,
    }
