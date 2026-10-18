"""确定性写盘单点测试（D18）：冻结字节契约 + 原子写 + 双跑一致。"""

import json
import os

from chartaudit import serialize


def test_json_bytes_contract(tmp_path):
    data = {"b": 1, "a": "中文"}
    raw = serialize.dumps_json(data)
    assert raw.endswith(b"\n")
    assert b"\r" not in raw
    # ensure_ascii=False：中文直出
    assert "中文".encode("utf-8") in raw
    # sort_keys
    text = raw.decode("utf-8")
    assert text.index('"a"') < text.index('"b"')
    # 可回读
    assert json.loads(text) == data


def test_double_run_identical(tmp_path):
    obj = {"k": [3, 1, 2], "nested": {"z": None, "a": True}}
    p1 = tmp_path / "one.json"
    p2 = tmp_path / "two.json"
    serialize.write_atomic(str(p1), serialize.dumps_json(obj))
    serialize.write_atomic(str(p2), serialize.dumps_json(obj).decode("utf-8"))  # str 直写也走同一契约
    with open(p1, "rb") as f1, open(p2, "rb") as f2:
        assert f1.read() == f2.read()


def test_atomic_no_tmp_leftover(tmp_path):
    target = str(tmp_path / "out.json")
    serialize.write_atomic(target, "{}\n")
    assert os.path.exists(target)
    leftovers = [n for n in os.listdir(str(tmp_path)) if n.endswith(".tmp")]
    assert leftovers == []
