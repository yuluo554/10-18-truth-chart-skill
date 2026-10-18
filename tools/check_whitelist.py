#!/usr/bin/env python3
"""假业务主题白名单校验（data/README §3.1）。

规则（唯一出处 data/README §3.1）：
- 维度名 / 指标名 / 标识名必须来自白名单；
- 规格标题必须以白名单主题前缀开头；
- 合成数据文件名必须以 `synthetic_` 开头；
- 文本中不得出现邮箱 / URL 等可识别真实主体痕迹。

用法：
    py -X utf8 tools/check_whitelist.py [--data-dir data/synthetic] [--specs-dir <dir>]
退出码：0 通过 / 1 违规 / 2 用法或读取错误。
"""

import argparse
import csv
import glob
import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "data", "synthetic")

THEME_PREFIXES = ("示例", "合成", "教学用")
ALLOWED_COLUMNS = {
    "组别",
    "批次",
    "站点",
    "渠道",
    "产量",
    "耗时",
    "得分",
    "单价",
    "转化数",
    "记录编号",
    "样本编号",
    "样本数",
}
METRIC_NAMES = ("产量", "耗时", "得分", "单价", "转化数")
METRIC_SUFFIXES = ("SD", "SEM", "CI下限", "CI上限")


def is_allowed_column(name):
    if name in ALLOWED_COLUMNS:
        return True
    return any(
        name == metric + suffix for metric in METRIC_NAMES for suffix in METRIC_SUFFIXES
    )
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
URL_RE = re.compile(r"https?://|www\.")


def read_header(path):
    with open(path, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8-sig")
    first_line = text.splitlines()[0] if text.splitlines() else ""
    delimiter = "\t" if "\t" in first_line and "," not in first_line else ","
    return next(csv.reader([first_line], delimiter=delimiter), [])


def check(data_dir, specs_dir=None):
    errors = []
    if not os.path.isdir(data_dir):
        return ["数据目录不存在：%s" % data_dir]

    for path in sorted(glob.glob(os.path.join(data_dir, "*"))):
        name = os.path.basename(path)
        if name == "manifest.json":
            continue
        if name.endswith((".csv", ".tsv")):
            if not name.startswith("synthetic_"):
                errors.append("文件名未使用 synthetic_ 前缀：%s" % name)
            try:
                header = read_header(path)
            except (UnicodeDecodeError, csv.Error) as exc:
                errors.append("无法读取表头 %s：%s" % (name, exc))
                continue
            for column in header:
                if not is_allowed_column(column):
                    errors.append("非白名单列名：%s → %s" % (name, column))
            with open(path, "rb") as f:
                text = f.read().decode("utf-8-sig")
            if EMAIL_RE.search(text):
                errors.append("发现邮箱痕迹：%s" % name)
            if URL_RE.search(text):
                errors.append("发现 URL 痕迹：%s" % name)
        elif name.endswith(".json"):
            if name.startswith("spec_"):
                with open(path, "rb") as f:
                    obj = json.loads(f.read().decode("utf-8"))
                title = obj.get("title", "")
                if not title.startswith(THEME_PREFIXES):
                    errors.append("标题未使用白名单主题前缀：%s → %s" % (name, title))

    if specs_dir:
        for path in sorted(glob.glob(os.path.join(specs_dir, "*.json"))):
            with open(path, "rb") as f:
                obj = json.loads(f.read().decode("utf-8"))
            title = obj.get("title", "")
            if not title.startswith(THEME_PREFIXES):
                errors.append(
                    "标题未使用白名单主题前缀：%s → %s" % (os.path.basename(path), title)
                )
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description="假业务主题白名单校验")
    parser.add_argument("--data-dir", default=DATA_DIR)
    parser.add_argument("--specs-dir", default=None)
    args = parser.parse_args(argv)
    try:
        errors = check(args.data_dir, args.specs_dir)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print("白名单校验无法执行：%s" % exc, file=sys.stderr)
        return 2
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("白名单校验通过：列名 / 标题前缀 / 文件名 / 隐私痕迹均合规")
    return 0


if __name__ == "__main__":
    sys.exit(main())
