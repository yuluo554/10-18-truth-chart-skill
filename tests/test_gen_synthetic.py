"""生成器守门测试：双跑一致、两层 --check、变异必红、无 stdlib 随机。"""

import importlib.util
import os
import shutil

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO_ROOT, "data", "synthetic")
GEN_PATH = os.path.join(REPO_ROOT, "tools", "gen_synthetic.py")


def load_generator():
    spec = importlib.util.spec_from_file_location("gen_synthetic", GEN_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gen = load_generator()


def test_generation_is_byte_identical_across_runs():
    first = gen.generate_artifacts()
    second = gen.generate_artifacts()
    assert first == second
    for name, data in first.items():
        assert data.endswith(b"\n"), name
        assert b"\r" not in data, name


def test_frozen_directory_passes_two_layer_check():
    ok, messages = gen.check(DATA)
    assert ok, messages


def test_manifest_covers_generator_and_caliber():
    ok, messages = gen.check(DATA)
    assert ok, messages
    import json

    with open(os.path.join(DATA, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["generator"]["path"] == "tools/gen_synthetic.py"
    assert manifest["caliber"]["path"] == "data/README.md"
    assert manifest["generator"]["sha256"] == gen.file_sha256(GEN_PATH)


def test_mutation_makes_check_fail(tmp_path):
    copy = str(tmp_path / "frozen")
    shutil.copytree(DATA, copy)
    target = os.path.join(copy, "synthetic_groups.csv")
    with open(target, "rb") as f:
        data = f.read()
    with open(target, "wb") as f:
        f.write(data.replace("甲组".encode("utf-8"), "乙组".encode("utf-8"), 1))
    ok, messages = gen.check(copy)
    assert not ok
    assert any("哈希不符" in message for message in messages)


def test_missing_frozen_file_makes_check_fail(tmp_path):
    copy = str(tmp_path / "frozen")
    shutil.copytree(DATA, copy)
    os.remove(os.path.join(copy, "spec_clean_bar.json"))
    ok, messages = gen.check(copy)
    assert not ok
    assert any("缺件" in message for message in messages)


def test_extra_file_makes_check_fail(tmp_path):
    copy = str(tmp_path / "frozen")
    shutil.copytree(DATA, copy)
    with open(os.path.join(copy, "stray.txt"), "w", encoding="utf-8") as f:
        f.write("stray\n")
    ok, messages = gen.check(copy)
    assert not ok
    assert any("多件" in message for message in messages)


def test_generator_has_no_stdlib_random_or_clock():
    import inspect

    with open(GEN_PATH, encoding="utf-8") as f:
        source = f.read()
    assert "import random" not in source
    assert "from random" not in source
    assert "time.time" not in source
    assert "datetime.now" not in source
    # 生成路径不得依赖 set 迭代序
    for func in (gen.build_tables, gen.build_specs, gen.build_truth):
        assert "set(" not in inspect.getsource(func), func.__name__
