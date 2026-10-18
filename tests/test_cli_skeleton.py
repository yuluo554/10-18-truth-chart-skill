"""骨架期冒烟测试：CLI 形态 + 退出码契约（0/1/2/3 + 骨架期 4）。"""

import pytest

from chartaudit import cli
from chartaudit.exitcodes import (
    EXIT_AUDIT_ERRORS,
    EXIT_CONFIG,
    EXIT_NOT_READY,
    EXIT_OK,
    EXIT_USAGE,
)


def test_no_args_is_usage_error():
    # 无子命令：不抛 SystemExit，统一返回用法错误码（契约统一入口，防 2/1 漂移）
    assert cli.main([]) == EXIT_USAGE


def test_build_is_not_ready_in_skeleton():
    assert cli.main(["build", "x.csv", "spec.json", "--out", "out"]) == EXIT_NOT_READY


def test_check_is_not_ready_in_skeleton():
    assert cli.main(["check", "x.csv", "spec.json", "--out", "out"]) == EXIT_NOT_READY


def test_selftest_is_not_ready_in_skeleton():
    assert cli.main(["selftest"]) == EXIT_NOT_READY


def test_exit_code_contract_constants():
    """口径 §15 四语义 + 骨架期临时码，常量值锁死。"""
    assert (EXIT_OK, EXIT_AUDIT_ERRORS, EXIT_USAGE, EXIT_CONFIG) == (0, 1, 2, 3)
    assert EXIT_NOT_READY == 4
