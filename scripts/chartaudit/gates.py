"""M4 窄缝门禁：dataset + normalized spec + provenance → gates.json。

三条窄缝（本题差异化主线；唯一口径见 data/README.md 第四节）：
- G1 溯源完备性：直接复用 `provenance.validate` 的判定与 gate_id / verdict，
  本模块只调用并引用，不写第二份判定、不改判；
- G2 样本量门禁：组内 n < n_min 且偏斜或多峰 -> 阻断级；未判定 -> 警示级；
  合规替代（全量散点叠加 / 箱线图）-> 提示级；
- G3 误差棒来源真实性：sd / sem / ci / n 四类声明按口径 §11 判定；标题自由文本
  声明无来源 -> 阻断级；未声明但存在可疑 SD / SEM 列 -> 提示级。

配置纪律：
- 阈值只在 `references/gates.json` 的 thresholds 定义一次，代码零阈值字面量；
- 列名别名只在 `references/aliases.json` 定义一次，大小写规则亦只在该文件；
- gate_id / 级别 / 证据路径 / 文案全部来自 `references/gates.json`；本模块零
  gate_id 与级别字面量（扫描门见 tests/test_gates.py）；级别枚举复用规则包
  `references/rules.json` 的 severity_order / block_on，不另立第二份枚举。

确定性：无网络、无时钟、无随机；findings 按（级别序, gate_id, 证据路径, 分组）
排序；同一输入两次输出逐字节一致。
"""

import json
import math
import os
from fractions import Fraction

from . import provenance as provenance_layer
from . import rules as rules_layer
from .exitcodes import EXIT_AUDIT_ERRORS, EXIT_OK

CONTRACT_VERSION = 1

REQUIRED_THRESHOLD_KEYS = (
    "n_min",
    "skew_abs_threshold",
    "skew_min_n",
    "multimodal_bins",
    "multimodal_min_n",
    "multimodal_min_count_floor",
    "multimodal_min_count_divisor",
    "sem_tolerance_abs",
)

INT_THRESHOLD_KEYS = (
    "n_min",
    "skew_min_n",
    "multimodal_bins",
    "multimodal_min_n",
    "multimodal_min_count_floor",
    "multimodal_min_count_divisor",
)

NUMERIC_COLUMN_TYPES = ("integer", "decimal")


class GatesConfigError(Exception):
    """门禁配置 / 别名表缺失或校验失败，映射退出码 3。"""


# ---------------------------------------------------------------------------
# 配置加载（references/gates.json + references/aliases.json）
# ---------------------------------------------------------------------------


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def default_gates_path():
    return os.path.join(_repo_root(), "references", "gates.json")


def default_aliases_path():
    return os.path.join(_repo_root(), "references", "aliases.json")


def _load_json(path, label):
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as exc:
        raise GatesConfigError("无法读取%s %s：%s" % (label, path, exc))
    try:
        config = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise GatesConfigError("%s不是合法 UTF-8 JSON：%s" % (label, exc))
    if not isinstance(config, dict):
        raise GatesConfigError("%s必须是 JSON 对象" % label)
    if config.get("contract_version") != CONTRACT_VERSION:
        raise GatesConfigError(
            "%s contract_version=%r（期望 %d）"
            % (label, config.get("contract_version"), CONTRACT_VERSION)
        )
    return config


def _validate_thresholds(thresholds):
    if not isinstance(thresholds, dict):
        raise GatesConfigError("thresholds 必须是对象")
    for key in REQUIRED_THRESHOLD_KEYS:
        if key not in thresholds:
            raise GatesConfigError("thresholds 缺少键：%s" % key)
    for key in INT_THRESHOLD_KEYS:
        value = thresholds[key]
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise GatesConfigError("thresholds.%s 必须是正整数：%r" % (key, value))
    skew = thresholds["skew_abs_threshold"]
    if not isinstance(skew, (int, float)) or isinstance(skew, bool) or skew <= 0:
        raise GatesConfigError("thresholds.skew_abs_threshold 必须是正数：%r" % (skew,))
    try:
        tolerance = Fraction(str(thresholds["sem_tolerance_abs"]))
    except (ValueError, ZeroDivisionError):
        raise GatesConfigError(
            "thresholds.sem_tolerance_abs 不是数值：%r"
            % (thresholds["sem_tolerance_abs"],)
        )
    if tolerance < 0:
        raise GatesConfigError("thresholds.sem_tolerance_abs 不能为负")
    if thresholds["multimodal_min_n"] < 2:
        raise GatesConfigError("thresholds.multimodal_min_n 必须 >= 2")
    if thresholds["skew_min_n"] < 3:
        raise GatesConfigError("thresholds.skew_min_n 必须 >= 3")
    if thresholds["multimodal_bins"] < 2:
        raise GatesConfigError("thresholds.multimodal_bins 必须 >= 2")


def load_aliases(path=None):
    """读取并校验误差棒列名别名表（大小写规则的唯一出处）。"""
    if path is None:
        path = default_aliases_path()
    config = _load_json(path, "别名表")
    if not isinstance(config.get("case_sensitive"), bool):
        raise GatesConfigError("别名表 case_sensitive 必须是布尔值")
    if config.get("match_mode") != "suffix":
        raise GatesConfigError("别名表 match_mode 目前只允许 suffix")
    order = config.get("type_order")
    if (
        not isinstance(order, list)
        or not order
        or len(set(order)) != len(order)
        or any(not isinstance(item, str) for item in order)
    ):
        raise GatesConfigError("别名表 type_order 必须是非空、唯一的字符串列表")
    types = config.get("types")
    if not isinstance(types, dict):
        raise GatesConfigError("别名表 types 必须是对象")
    if set(types) != set(order):
        raise GatesConfigError("别名表 types 与 type_order 不一致")
    for type_name in order:
        entry = types[type_name]
        if not isinstance(entry, dict):
            raise GatesConfigError("别名类型 %s 必须是对象" % type_name)
        keys = ("lower", "upper") if type_name == "ci" else ("columns",)
        for key in keys:
            values = entry.get(key)
            if (
                not isinstance(values, list)
                or not values
                or any(not isinstance(value, str) or not value for value in values)
            ):
                raise GatesConfigError(
                    "别名类型 %s 的 %s 必须是非空字符串列表" % (type_name, key)
                )
        title_values = entry.get("title")
        if (
            not isinstance(title_values, list)
            or not title_values
            or any(not isinstance(value, str) or not value for value in title_values)
        ):
            raise GatesConfigError("别名类型 %s 的 title 必须是非空字符串列表" % type_name)
    return config


def _validate_gate_severity(entry, severity_order):
    severity = entry.get("severity")
    if isinstance(severity, str):
        if severity not in severity_order:
            raise GatesConfigError(
                "门禁 %s 的 severity=%r 不在规则包 severity_order 内"
                % (entry.get("gate_id"), severity)
            )
        return
    if isinstance(severity, dict):
        if not severity:
            raise GatesConfigError("门禁 %s 的 severity 映射为空" % entry.get("gate_id"))
        for key, value in severity.items():
            if not isinstance(key, str) or not key:
                raise GatesConfigError("门禁 %s 的 severity 键非法" % entry.get("gate_id"))
            if value not in severity_order:
                raise GatesConfigError(
                    "门禁 %s 的 severity[%s]=%r 不在规则包 severity_order 内"
                    % (entry.get("gate_id"), key, value)
                )
        return
    raise GatesConfigError("门禁 %s 的 severity 必须是字符串或映射" % entry.get("gate_id"))


def load_gates(path=None, rules_cfg=None):
    """读取并校验门禁包；缺失 / 非法 / 未覆盖检查器 -> GatesConfigError。"""
    if rules_cfg is None:
        try:
            rules_cfg = rules_layer.load_rules()
        except rules_layer.RulesConfigError as exc:
            raise GatesConfigError("规则包不可加载（级别枚举唯一出处）：%s" % exc)
    severity_order = rules_cfg["severity_order"]
    if path is None:
        path = default_gates_path()
    config = _load_json(path, "门禁包")
    _validate_thresholds(config.get("thresholds"))
    entries = config.get("gates")
    if not isinstance(entries, list) or not entries:
        raise GatesConfigError("gates 必须是非空列表")
    seen_ids = set()
    seen_checks = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise GatesConfigError("门禁项必须是对象：%r" % (entry,))
        for key in ("gate_id", "check", "evidence_path", "title", "message"):
            if not isinstance(entry.get(key), str) or not entry[key]:
                raise GatesConfigError(
                    "门禁项缺少有效字段 %s：%r" % (key, entry.get(key))
                )
        if entry["check"] not in GATE_CHECKS:
            raise GatesConfigError(
                "门禁 %s 引用未知检查器 %r（已实现：%s）"
                % (entry["gate_id"], entry["check"], ", ".join(sorted(GATE_CHECKS)))
            )
        if entry["gate_id"] in seen_ids:
            raise GatesConfigError("gate_id 重复：%s" % entry["gate_id"])
        if entry["check"] in seen_checks:
            raise GatesConfigError(
                "检查器 %s 被多条门禁重复登记（一检查一门禁）" % entry["check"]
            )
        _validate_gate_severity(entry, severity_order)
        seen_ids.add(entry["gate_id"])
        seen_checks.add(entry["check"])
    missing = set(GATE_CHECKS) - seen_checks
    if missing:
        raise GatesConfigError(
            "门禁包未覆盖全部已实现检查器，缺少：%s" % ", ".join(sorted(missing))
        )
    return config


# ---------------------------------------------------------------------------
# 统计口径（与生成器同口径的独立实现，口径 §7 / §8）
# ---------------------------------------------------------------------------


def skew_g1(values, thresholds):
    """样本偏度 g1 = m3 / m2^(3/2)；n 过小或全等值 -> None（未判定）。"""
    n = len(values)
    if n < thresholds["skew_min_n"]:
        return None
    mean = Fraction(sum(values), n)
    m2 = sum((Fraction(value) - mean) ** 2 for value in values) / n
    if m2 == 0:
        return None
    m3 = sum((Fraction(value) - mean) ** 3 for value in values) / n
    return float(m3 / (m2 ** Fraction(3, 2)))


def bin_counts(values, thresholds):
    """固定 bins 等宽直方图计数；n 过小或 max==min -> None（未判定）。"""
    bins = thresholds["multimodal_bins"]
    n = len(values)
    if n < thresholds["multimodal_min_n"]:
        return None
    lo, hi = min(values), max(values)
    if hi == lo:
        return None
    width = Fraction(hi - lo, bins)
    counts = [0] * bins
    for value in values:
        index = int((Fraction(value) - lo) / width)
        if index == bins:
            index = bins - 1
        counts[index] += 1
    return counts


def is_multimodal(counts, n, thresholds):
    """至少两个局部极大 bin（间隔 >= 1 个 bin）且计数达到下限 -> 多峰。"""
    if counts is None:
        return None
    divisor = thresholds["multimodal_min_count_divisor"]
    threshold = max(
        thresholds["multimodal_min_count_floor"],
        (n + divisor - 1) // divisor,
    )
    maxima = []
    for index, count in enumerate(counts):
        if count < threshold:
            continue
        left = counts[index - 1] if index > 0 else None
        right = counts[index + 1] if index < len(counts) - 1 else None
        if left is not None and count <= left:
            continue
        if right is not None and count <= right:
            continue
        maxima.append(index)
    for first in range(len(maxima)):
        for second in range(first + 1, len(maxima)):
            if maxima[second] - maxima[first] >= 2:
                return True
    return False


def group_stats(values, thresholds):
    """返回逐值统计（truth expected_stats 的对照基准由生成器独立给出）。"""
    g1 = skew_g1(values, thresholds)
    counts = bin_counts(values, thresholds)
    multimodal = is_multimodal(counts, len(values), thresholds) if counts else None
    skewed = None if g1 is None else abs(g1) > thresholds["skew_abs_threshold"]
    return {
        "n": len(values),
        "n_below_min": len(values) < thresholds["n_min"],
        "skewed": skewed,
        "multimodal": multimodal,
        "g1": None if g1 is None else round(g1, 6),
        "bin_counts": counts,
    }


# ---------------------------------------------------------------------------
# 数据分组与单元格工具
# ---------------------------------------------------------------------------


def _header_index(dataset):
    return {name: index for index, name in enumerate(dataset["header"])}


def _selected_rows(dataset, normalized_spec):
    conditions = []
    for channel_name in ("x", "y"):
        filter_obj = normalized_spec["encoding"].get(channel_name, {}).get("filter")
        if filter_obj:
            conditions.append((filter_obj["field"], filter_obj["equals"]))
    header_index = _header_index(dataset)
    rows = []
    for row_index, row in enumerate(dataset["rows"]):
        if all(
            row[header_index[field]] == expected for field, expected in conditions
        ):
            rows.append((row_index, row))
    return rows


def _groups(dataset, normalized_spec):
    header_index = _header_index(dataset)
    x_field = normalized_spec["encoding"]["x"]["field"]
    series_field = normalized_spec["encoding"].get("series", {}).get("field")
    groups = []
    index_by_key = {}
    for row_index, row in _selected_rows(dataset, normalized_spec):
        series = row[header_index[series_field]] if series_field else None
        category = row[header_index[x_field]]
        key = (series, category)
        if key not in index_by_key:
            index_by_key[key] = len(groups)
            groups.append(
                {
                    "series": series,
                    "category": category,
                    "row_indices": [],
                    "rows": [],
                }
            )
        group = groups[index_by_key[key]]
        group["row_indices"].append(row_index)
        group["rows"].append(row)
    return groups


def _numeric_cell(cell):
    if cell == "":
        return None
    try:
        return Fraction(cell)
    except (ValueError, ZeroDivisionError, TypeError):
        return None


def _column_numeric_values(group, column, header_index):
    values = []
    for row in group["rows"]:
        value = _numeric_cell(row[header_index[column]])
        if value is None:
            return None
        values.append(value)
    return values


def _normalize(name, aliases_cfg):
    return name if aliases_cfg["case_sensitive"] else name.casefold()


def _matches_alias(name, aliases, aliases_cfg):
    normalized = _normalize(name, aliases_cfg)
    for alias in aliases:
        candidate = _normalize(alias, aliases_cfg)
        if normalized == candidate or normalized.endswith(candidate):
            return True
    return False


def _matching_columns(header, aliases, aliases_cfg):
    return [column for column in header if _matches_alias(column, aliases, aliases_cfg)]


def _sem_consistent(pairs, n, thresholds):
    """sem 列与 sd/sqrt(n) 逐值对比；超出容差 -> False。"""
    tolerance = float(Fraction(str(thresholds["sem_tolerance_abs"])))
    for sem_value, sd_value in pairs:
        expected = float(sd_value) / math.sqrt(n)
        if abs(float(sem_value) - expected) > tolerance:
            return False
    return True


# ---------------------------------------------------------------------------
# G2：样本量门禁
# ---------------------------------------------------------------------------


def _g2_applicable(normalized_spec):
    aggregate = normalized_spec["encoding"]["y"].get("aggregate")
    if normalized_spec["mark"] == "box":
        return True
    return aggregate == "group_mean"


def _g2_alternative(normalized_spec):
    return bool(normalized_spec.get("overlay_scatter")) or normalized_spec["mark"] in (
        "box",
        "scatter",
    )


def _audit_g2(dataset, normalized_spec, gate_entry, thresholds):
    groups = []
    if not _g2_applicable(normalized_spec):
        return groups, []
    header_index = _header_index(dataset)
    y_field = normalized_spec["encoding"]["y"]["field"]
    alternative = _g2_alternative(normalized_spec)
    findings = []
    for group in _groups(dataset, normalized_spec):
        values = [_numeric_cell(row[header_index[y_field]]) for row in group["rows"]]
        if any(value is None for value in values):
            continue
        stats = group_stats(values, thresholds)
        status = "pass"
        if stats["n_below_min"]:
            if stats["skewed"] is True or stats["multimodal"] is True:
                status = "alternative" if alternative else "violation"
            elif stats["skewed"] is None or stats["multimodal"] is None:
                status = "undetermined"
        entry = {
            "series": group["series"],
            "category": group["category"],
            "n": stats["n"],
            "n_below_min": stats["n_below_min"],
            "skewed": stats["skewed"],
            "multimodal": stats["multimodal"],
            "g1": stats["g1"],
            "bin_counts": stats["bin_counts"],
            "status": status,
        }
        if status != "pass":
            entry["gate_id"] = gate_entry["gate_id"]
            entry["severity"] = gate_entry["severity"][status]
            findings.append(
                {
                    "gate_id": gate_entry["gate_id"],
                    "severity": gate_entry["severity"][status],
                    "evidence_path": gate_entry["evidence_path"],
                    "evidence": {
                        "series": group["series"],
                        "category": group["category"],
                        "status": status,
                        "n": stats["n"],
                        "n_min": thresholds["n_min"],
                        "skewed": stats["skewed"],
                        "multimodal": stats["multimodal"],
                        "g1": stats["g1"],
                        "bin_counts": stats["bin_counts"],
                    },
                    "message": gate_entry["message"],
                }
            )
        groups.append(entry)
    return groups, findings


# ---------------------------------------------------------------------------
# G3：误差棒来源真实性
# ---------------------------------------------------------------------------


def _title_declared_type(title, aliases_cfg):
    text = title if aliases_cfg["case_sensitive"] else title.casefold()
    for type_name in aliases_cfg["type_order"]:
        for alias in aliases_cfg["types"][type_name]["title"]:
            candidate = alias if aliases_cfg["case_sensitive"] else alias.casefold()
            if candidate in text:
                return type_name
    return None


def _suspicious_columns(dataset, normalized_spec, aliases_cfg):
    header = dataset["header"]
    header_index = _header_index(dataset)
    selected = _selected_rows(dataset, normalized_spec)
    suspicious = []
    for type_name in ("sd", "sem"):
        aliases = aliases_cfg["types"][type_name]["columns"]
        for column in _matching_columns(header, aliases, aliases_cfg):
            if column in suspicious:
                continue
            if any(
                _numeric_cell(row[header_index[column]]) is not None
                for _, row in selected
            ):
                suspicious.append(column)
    return suspicious


def _finding(gate_entry, evidence_path, evidence):
    return {
        "gate_id": gate_entry["gate_id"],
        "severity": gate_entry["severity"],
        "evidence_path": evidence_path or gate_entry["evidence_path"],
        "evidence": evidence,
        "message": gate_entry["message"],
    }


def _check_sd(group, declared_column, header, header_index, aliases_cfg):
    aliases = aliases_cfg["types"]["sd"]["columns"]
    candidates = []
    if declared_column:
        if not _matches_alias(declared_column, aliases, aliases_cfg):
            return None, {"declared_column": declared_column, "matched": []}
        candidates = [declared_column]
    else:
        candidates = _matching_columns(header, aliases, aliases_cfg)
    matched = []
    for column in candidates:
        values = _column_numeric_values(group, column, header_index)
        if values is not None:
            matched.append({"column": column, "values_count": len(values)})
    if matched:
        return {"column": matched[0]["column"], "matched": matched}, None
    return None, {"declared_column": declared_column, "matched": []}


def _check_sem(group, declared_column, header, header_index, aliases_cfg, thresholds):
    sem_aliases = aliases_cfg["types"]["sem"]["columns"]
    sd_aliases = aliases_cfg["types"]["sd"]["columns"]
    sd_columns = _matching_columns(header, sd_aliases, aliases_cfg)
    if declared_column:
        if not _matches_alias(declared_column, sem_aliases, aliases_cfg):
            return None, {"declared_column": declared_column, "reason": "列名不在 SEM 别名表"}
        sem_values = _column_numeric_values(group, declared_column, header_index)
        if sem_values is None:
            return None, {"declared_column": declared_column, "reason": "组内无有效 SEM 数值"}
        sd_column = sd_columns[0] if sd_columns else None
        sd_values = (
            _column_numeric_values(group, sd_column, header_index) if sd_column else None
        )
        if sd_values is not None:
            pairs = list(zip(sem_values, sd_values))
            if not _sem_consistent(pairs, len(group["rows"]), thresholds):
                return None, {
                    "declared_column": declared_column,
                    "sd_column": sd_column,
                    "reason": "SEM 与 sd/sqrt(n) 不符",
                }
        return {"column": declared_column, "source": "sem_column"}, None
    sem_columns = _matching_columns(header, sem_aliases, aliases_cfg)
    for column in sem_columns:
        values = _column_numeric_values(group, column, header_index)
        if values is not None:
            return {"column": column, "source": "sem_column"}, None
    for column in sd_columns:
        values = _column_numeric_values(group, column, header_index)
        if values is not None:
            return {"column": column, "source": "sd_recompute"}, None
    return None, {"declared_column": None, "reason": "无 SEM 列且无可重算的 SD 列"}


def _check_ci(group, declared_column, header, header_index, aliases_cfg):
    ci_cfg = aliases_cfg["types"]["ci"]
    lower_columns = _matching_columns(header, ci_cfg["lower"], aliases_cfg)
    upper_columns = _matching_columns(header, ci_cfg["upper"], aliases_cfg)
    if declared_column:
        # 单个 column 只能指向一侧，无法构成"上下限两列"的完整声明。
        return None, {
            "declared_column": declared_column,
            "reason": "CI 声明只给出单个列，缺少上下限成对来源",
        }
    lower_column = lower_columns[0] if lower_columns else None
    upper_column = upper_columns[0] if upper_columns else None
    if not lower_column or not upper_column:
        return None, {
            "declared_column": declared_column,
            "lower_column": lower_column,
            "upper_column": upper_column,
            "reason": "缺少 CI 下限或上限列",
        }
    for column in (lower_column, upper_column):
        values = _column_numeric_values(group, column, header_index)
        if values is None:
            return None, {
                "declared_column": declared_column,
                "lower_column": lower_column,
                "upper_column": upper_column,
                "reason": "组内 CI 列存在缺失或非数值",
            }
    return {"lower_column": lower_column, "upper_column": upper_column}, None


def _check_n(group, declared_column, header, header_index, aliases_cfg):
    aliases = aliases_cfg["types"]["n"]["columns"]
    candidates = []
    if declared_column:
        if not _matches_alias(declared_column, aliases, aliases_cfg):
            return None, {"declared_column": declared_column, "reason": "列名不在样本数别名表"}
        candidates = [declared_column]
    else:
        candidates = _matching_columns(header, aliases, aliases_cfg)
    if not candidates:
        return None, {"declared_column": declared_column, "reason": "未提供样本数列"}
    column = candidates[0]
    values = _column_numeric_values(group, column, header_index)
    if values is None:
        return None, {"declared_column": declared_column, "reason": "组内样本数存在缺失或非数值"}
    actual = len(group["rows"])
    mismatched = sorted({str(value) for value in values if value != actual})
    if mismatched:
        return None, {
            "declared_column": column,
            "declared_values": mismatched,
            "actual_n": actual,
        }
    return {"column": column, "declared_n": actual}, None


def _audit_g3(dataset, normalized_spec, gates_cfg, aliases_cfg):
    header = dataset["header"]
    header_index = _header_index(dataset)
    entries = {entry["check"]: entry for entry in gates_cfg["gates"]}
    findings = []
    declarations = []
    error_bar = normalized_spec["encoding"].get("error_bar")
    selected_rows = _selected_rows(dataset, normalized_spec)
    title_declared = None
    suspicious = []
    if error_bar is None:
        title_declared = _title_declared_type(normalized_spec["title"], aliases_cfg)
        if title_declared is not None:
            entry = entries["error_bar_%s_title" % title_declared]
            findings.append(
                _finding(
                    entry,
                    entry["evidence_path"],
                    {"title": normalized_spec["title"], "declared_type": title_declared},
                )
            )
        else:
            suspicious = _suspicious_columns(dataset, normalized_spec, aliases_cfg)
            if suspicious and selected_rows:
                entry = entries["error_bar_undeclared"]
                findings.append(
                    _finding(
                        entry,
                        entry["evidence_path"],
                        {"columns": suspicious},
                    )
                )
        return findings, declarations, title_declared, suspicious

    type_name = error_bar["type"]
    declared_column = error_bar.get("column")
    checks = {
        "sd": (_check_sd, "error_bar_sd"),
        "sem": (_check_sem, "error_bar_sem"),
        "ci": (_check_ci, "error_bar_ci"),
        "n": (_check_n, "error_bar_n"),
    }
    checker, check_name = checks[type_name]
    for group in _groups(dataset, normalized_spec):
        if type_name == "sem":
            source, problem = checker(
                group,
                declared_column,
                header,
                header_index,
                aliases_cfg,
                gates_cfg["thresholds"],
            )
        else:
            source, problem = checker(
                group, declared_column, header, header_index, aliases_cfg
            )
        declaration = {
            "type": type_name,
            "series": group["series"],
            "category": group["category"],
            "n": len(group["rows"]),
            "declared_column": declared_column,
            "status": "ok" if source is not None else "error",
        }
        if source is not None:
            declaration["source"] = source
        else:
            declaration["problem"] = problem
        declarations.append(declaration)
        if source is None:
            if type_name == "sem" and isinstance(problem, dict) and problem.get(
                "reason"
            ) == "SEM 与 sd/sqrt(n) 不符":
                entry = entries["error_bar_sem_value"]
            elif type_name == "n" and isinstance(problem, dict) and "actual_n" in problem:
                entry = entries["error_bar_n"]
            elif type_name == "n":
                entry = entries["error_bar_n_source"]
            else:
                entry = entries[check_name]
            findings.append(
                _finding(
                    entry,
                    entry["evidence_path"],
                    {
                        "type": type_name,
                        "series": group["series"],
                        "category": group["category"],
                        "declared_column": declared_column,
                        "problem": problem,
                    },
                )
            )
    return findings, declarations, title_declared, suspicious


# ---------------------------------------------------------------------------
# 门禁入口
# ---------------------------------------------------------------------------


GATE_CHECKS = (
    "sample_size_mean_bar",
    "error_bar_sd",
    "error_bar_sem",
    "error_bar_sem_value",
    "error_bar_ci",
    "error_bar_n",
    "error_bar_n_source",
    "error_bar_sd_title",
    "error_bar_sem_title",
    "error_bar_ci_title",
    "error_bar_n_title",
    "error_bar_undeclared",
)


def audit(dataset, normalized_spec, provenance_obj, gates_cfg=None, aliases_cfg=None,
          provenance_report=None, rules_cfg=None):
    """执行 G1 + G2 + G3，返回 gates.json 对象。"""
    if gates_cfg is None:
        gates_cfg = load_gates(rules_cfg=rules_cfg)
    if aliases_cfg is None:
        aliases_cfg = load_aliases()
    if provenance_report is None:
        provenance_report = provenance_layer.validate(
            provenance_obj, dataset, normalized_spec
        )
    if rules_cfg is None:
        rules_cfg = rules_layer.load_rules()
    order = {level: index for index, level in enumerate(rules_cfg["severity_order"])}
    block_on = rules_cfg["block_on"]

    g1_gate_ids = sorted(
        {issue["gate_id"] for issue in provenance_report.get("errors", [])}
    )
    g1_blocked = provenance_report.get("verdict") == "blocked"
    g1 = {
        "verdict": provenance_report.get("verdict"),
        "gate_ids": g1_gate_ids,
        "checked_count": provenance_report.get("checked_count", 0),
        "error_count": provenance_report.get("error_count", 0),
        "exit_code": provenance_report.get(
            "exit_code", EXIT_AUDIT_ERRORS if g1_blocked else EXIT_OK
        ),
    }

    entries = {entry["check"]: entry for entry in gates_cfg["gates"]}
    g2_groups, g2_findings = _audit_g2(
        dataset, normalized_spec, entries["sample_size_mean_bar"], gates_cfg["thresholds"]
    )
    g3_findings, declarations, title_declared, suspicious = _audit_g3(
        dataset, normalized_spec, gates_cfg, aliases_cfg
    )

    findings = g2_findings + g3_findings
    findings.sort(
        key=lambda finding: (
            order[finding["severity"]],
            finding["gate_id"],
            finding["evidence_path"],
            str(finding["evidence"].get("category", "")),
        )
    )

    counts = {level: 0 for level in rules_cfg["severity_order"]}
    for finding in findings:
        counts[finding["severity"]] += 1
    counts[block_on] += g1["error_count"]
    counts["total"] = len(findings) + g1["error_count"]

    blocked = g1_blocked or any(
        finding["severity"] == block_on for finding in findings
    )
    return {
        "contract_version": CONTRACT_VERSION,
        "spec_id": normalized_spec["spec_id"],
        "mark": normalized_spec["mark"],
        "source": {
            "name": provenance_obj["source"]["name"],
            "sha256": provenance_obj["source"]["sha256"],
        },
        "severity_order": list(rules_cfg["severity_order"]),
        "block_on": block_on,
        "g1": g1,
        "g2": {"groups": g2_groups},
        "g3": {
            "declarations": declarations,
            "title_declared_type": title_declared,
            "suspicious_columns": suspicious,
        },
        "counts": counts,
        "findings": findings,
        "verdict": "blocked" if blocked else "pass",
        "render_allowed": not blocked,
        "exit_code": EXIT_AUDIT_ERRORS if blocked else EXIT_OK,
    }
