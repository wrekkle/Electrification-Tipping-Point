#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查脚本共用函数：读配置、走目录、按 LF 口径数字符、排版。全部只读，不写任何文件。"""

import fnmatch
import json
import os
import sys
import unicodedata

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def find_root(start=None):
    """从 start 向上找含 repo-discipline.json 的目录。"""
    cur = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.isfile(os.path.join(cur, "repo-discipline.json")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(start or os.getcwd())
        cur = parent


def load_config(root, path=None):
    p = path or os.path.join(root, "repo-discipline.json")
    if not os.path.isfile(p):
        raise SystemExit("找不到配置文件: " + p)
    with open(p, "r", encoding="utf-8-sig") as fh:
        cfg = json.load(fh)
    cfg["_config_path"] = os.path.abspath(p)
    return cfg


def rel(root, path):
    return os.path.relpath(path, root).replace("\\", "/")


def read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def decode_text(data):
    """先按 UTF-8（容忍 BOM），失败再按 GB18030。项目里 download_manifest.csv 是 GBK 写的。"""
    for enc in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def read_text(path):
    try:
        return decode_text(read_bytes(path))
    except OSError:
        return ""


def is_binary(data):
    return b"\x00" in data[:8192]


def lf_text(data):
    return decode_text(data).replace("\r\n", "\n").replace("\r", "\n")


def lf_char_count(path):
    """LF 归一化后的 Unicode 字符数；二进制文件返回 None。"""
    try:
        data = read_bytes(path)
    except OSError:
        return None
    if is_binary(data):
        return None
    return len(lf_text(data))


def walk_files(root, cfg):
    """按 skip_dirs 走一遍，返回 [(绝对路径, 相对路径)]，按相对路径排序。"""
    skip = set(cfg.get("skip_dirs") or [])
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in skip)
        for name in filenames:
            p = os.path.join(dirpath, name)
            out.append((p, rel(root, p)))
    out.sort(key=lambda x: x[1])
    return out


def match_rule(relpath, cfg):
    """第一条命中的路径规则。规则顺序就是配置里 paths 的顺序。"""
    for rule in cfg.get("paths") or []:
        if fnmatch.fnmatchcase(relpath, rule["glob"]):
            return rule
    return None


def display_width(text):
    w = 0
    for ch in text:
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return w


def pad(text, width):
    return text + " " * max(0, width - display_width(text))


def table(headers, rows):
    """等宽表格：按显示宽度对齐（中文占 2 列）。"""
    widths = [display_width(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], display_width(str(cell)))
    lines = ["  ".join(pad(str(h), widths[i]) for i, h in enumerate(headers)).rstrip()]
    lines.append("  ".join("-" * widths[i] for i in range(len(headers))))
    for row in rows:
        lines.append("  ".join(pad(str(c), widths[i]) for i, c in enumerate(row)).rstrip())
    return "\n".join(lines)


def write_report(path, lines):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines).rstrip() + "\n")
    return path


def now_str():
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def report_header(title, cmd, status="已完成"):
    return [
        "# " + title,
        "",
        "生成命令: " + cmd,
        "生成时间: " + now_str(),
        "状态: " + status,
        "口径: 长度为 LF 归一化后的 Unicode 字符数，含空格与标点，每个换行计 1 个字符。",
        "",
    ]


def err(msg):
    return {"level": "错误", "msg": msg}


def warn(msg):
    return {"level": "警告", "msg": msg}
