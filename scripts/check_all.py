#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次跑完三组只读检查：文档与链接、稿件字数与章节一致性、文献索引。

默认只打印，不改任何文件；要落报告必须显式给 --write-reports。
用法:
    python scripts/check_all.py
    python scripts/check_all.py --write-reports
    python scripts/check_all.py --write-reports --date 2026-10-29
退出码 0 = 全部通过；1 = 有需要处理的问题。
"""

import argparse
import datetime
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _common as C  # noqa: E402


def run(args):
    """跑一个子脚本；返回 (退出码, 输出文本)。"""
    full = [sys.executable] + args
    proc = subprocess.run(full, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def main():
    ap = argparse.ArgumentParser(description="跑完全部只读检查")
    ap.add_argument("--root", default=None)
    ap.add_argument("--config", default=None)
    ap.add_argument("--write-reports", action="store_true", help="把三份报告写到 docs/reports/")
    ap.add_argument("--date", default=None, help="报告日期前缀，默认今天")
    args = ap.parse_args()
    root = os.path.abspath(args.root) if args.root else C.find_root()
    date = args.date or datetime.date.today().strftime("%Y-%m-%d")
    reports = os.path.join(root, "docs", "reports")
    base = ["--root", root]
    if args.config:
        base += ["--config", args.config]

    results = []

    if args.write_reports:
        path = os.path.join(reports, date + "-文档与链接检查.md")
        code, out = run([os.path.join(HERE, "check_docs.py")] + base + ["--out", path])
        results.append(("文档与链接检查", code, path))
    else:
        code, out = run([os.path.join(HERE, "check_docs.py")] + base)
        results.append(("文档与链接检查", code, None))
    print(out.rstrip())

    if args.write_reports:
        out_md = os.path.join(reports, date + "-字数报告.md")
        out_js = os.path.join(reports, date + "-字数报告.json")
        code, out = run([os.path.join(HERE, "paper_stats.py")] + base +
                        ["--check-sections", "--out", out_md, "--json", out_js])
        results.append(("稿件字数与章节一致性", code, out_md))
    else:
        code, out = run([os.path.join(HERE, "paper_stats.py")] + base + ["--check-sections"])
        results.append(("稿件字数与章节一致性", code, None))
    print(out.rstrip())

    if args.write_reports:
        path = os.path.join(reports, date + "-文献索引检查.md")
        code, out = run([os.path.join(HERE, "lit_index.py")] + base +
                        ["--check-index", "--out-report", path])
        results.append(("文献索引", code, path))
    else:
        code, out = run([os.path.join(HERE, "lit_index.py")] + base + ["--check-index"])
        results.append(("文献索引", code, None))
    print(out.rstrip())

    print("=== 汇总 ===")
    failed = 0
    for name, code, path in results:
        state = "通过" if code == 0 else "有问题"
        if code != 0:
            failed += 1
        line = "%-14s %s" % (name, state)
        if path:
            line += "  报告: " + os.path.relpath(path, root).replace("\\", "/")
        print(line)
    if not args.write_reports:
        print("（未写报告；要落盘加 --write-reports）")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
