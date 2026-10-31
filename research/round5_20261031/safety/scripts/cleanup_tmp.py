# -*- coding: utf-8 -*-
"""清理 safety/tmp/** 故障注入目录；删除前断言绝对路径在 safety/tmp 下。"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
TMP = ROOT / "research" / "round5_20261031" / "safety" / "tmp"


def main() -> int:
    root = TMP.resolve()
    removed, files = [], []
    if not TMP.exists():
        print(json.dumps({"tmp_root": str(root), "removed": [], "note": "tmp 不存在"}, ensure_ascii=False))
        return 0
    for child in sorted(TMP.iterdir()):
        resolved = child.resolve()
        if resolved.parent != root:
            raise AssertionError(f"拒绝清理 {resolved}：不在 {root} 下")
        if resolved.is_dir():
            shutil.rmtree(resolved)
            removed.append(str(resolved))
        else:
            resolved.unlink()
            files.append(str(resolved))
    print(json.dumps({"tmp_root": str(root), "removed_dirs": removed, "removed_files": files,
                      "remaining": sorted(p.name for p in TMP.iterdir())}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
