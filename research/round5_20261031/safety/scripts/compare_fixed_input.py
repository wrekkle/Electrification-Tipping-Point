# -*- coding: utf-8 -*-
"""固定输入研究数值前后一致性：忽略 provenance（时间戳/源码哈希），比较其余全部内容。"""
from __future__ import annotations

import json
import sys


def strip(payload):
    data = json.loads(json.dumps(payload))
    data.pop("provenance", None)
    return data


def main(argv):
    left, right = (json.loads(open(p, encoding="utf-8").read()) for p in argv[1:3])
    a, b = strip(left), strip(right)
    same = a == b
    detail = []
    if not same:
        for key in sorted(set(a) | set(b)):
            if a.get(key) != b.get(key):
                detail.append(key)
    print(json.dumps({"equal": same, "differing_keys": detail,
                      "seeds": a.get("seeds"), "rows": len(a.get("rows") or [])}, ensure_ascii=False, indent=2))
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
