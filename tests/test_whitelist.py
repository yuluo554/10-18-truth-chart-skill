"""白名单校验脚本测试：真实冻结目录通过；违规样例必须报红。"""

import importlib.util
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO_ROOT, "data", "synthetic")
CHECKER_PATH = os.path.join(REPO_ROOT, "tools", "check_whitelist.py")


def load_checker():
    spec = importlib.util.spec_from_file_location("check_whitelist", CHECKER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = load_checker()


def test_frozen_data_passes():
    assert checker.check(DATA) == []


def test_unknown_column_is_rejected(tmp_path):
    (tmp_path / "synthetic_bad.csv").write_text(
        "组别,公司营收\n甲组,10\n", encoding="utf-8"
    )
    errors = checker.check(str(tmp_path))
    assert any("非白名单列名" in error for error in errors)


def test_bad_filename_is_rejected(tmp_path):
    (tmp_path / "real_company.csv").write_text("组别,产量\n甲组,10\n", encoding="utf-8")
    errors = checker.check(str(tmp_path))
    assert any("synthetic_ 前缀" in error for error in errors)


def test_title_without_whitelisted_prefix_is_rejected(tmp_path):
    (tmp_path / "synthetic_ok.csv").write_text("组别,产量\n甲组,10\n", encoding="utf-8")
    (tmp_path / "spec_bad.json").write_text(
        '{"title": "某公司季度营收"}\n', encoding="utf-8"
    )
    errors = checker.check(str(tmp_path))
    assert any("主题前缀" in error for error in errors)


def test_email_trace_is_rejected(tmp_path):
    (tmp_path / "synthetic_bad.csv").write_text(
        "组别,产量\nsomeone@example.com,10\n", encoding="utf-8"
    )
    errors = checker.check(str(tmp_path))
    assert any("邮箱" in error for error in errors)


def test_derived_errorbar_columns_are_allowed(tmp_path):
    (tmp_path / "synthetic_ok.tsv").write_text(
        "组别,耗时,耗时SD,耗时SEM,耗时CI下限,耗时CI上限,样本数\n甲组,10,1.5,0.75,8,12,4\n",
        encoding="utf-8",
    )
    assert checker.check(str(tmp_path)) == []
