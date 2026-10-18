"""M2 基准脚本冒烟：tools/bench.py 全量达标。"""

import importlib.util
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BENCH_PATH = os.path.join(REPO_ROOT, "tools", "bench.py")


def load_bench():
    spec = importlib.util.spec_from_file_location("chartaudit_bench", BENCH_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_m2_benchmark_all_charts_pass(capsys):
    bench = load_bench()
    assert bench.main([]) == 0
    output = capsys.readouterr().out
    assert "汇总：29/29 达标；失败 0" in output


def test_bench_rejects_arguments(capsys):
    bench = load_bench()
    assert bench.main(["--unknown"]) == 2
    assert "用法" in capsys.readouterr().err
