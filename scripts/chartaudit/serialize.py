"""确定性写盘单点（D18）。

全部产物 JSON/HTML 写盘必须经本模块；参数为冻结契约（K 项）：
    json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=2) + LF + 结尾换行
原子写：临时文件 + os.replace。
"""

import json
import os
import tempfile


def dumps_json(obj):
    """序列化为冻结字节契约：UTF-8、LF、结尾换行。"""
    text = json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=2)
    return (text + "\n").encode("utf-8")


def write_atomic(path, data):
    """原子写：data 为 bytes 或 str（str 按 UTF-8 编码）。"""
    if isinstance(data, str):
        data = data.encode("utf-8")
    out_dir = os.path.dirname(os.path.abspath(path))
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=out_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
