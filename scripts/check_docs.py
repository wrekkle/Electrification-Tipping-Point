#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只读检查：管理文档长度档位、长行、链接、状态行、待办分散、生成物标记。

默认只打印，不写文件；要落报告必须显式给 --out。
用法:
    python scripts/check_docs.py
    python scripts/check_docs.py --out docs/reports/2026-10-30-文档检查.md
    python scripts/check_docs.py --selftest
退出码 0 = 没有必须处理的错误；1 = 有错误；2 = 配置或用法错误。
"""

import argparse
import fnmatch
import os
import re
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C  # noqa: E402

BT = chr(96)

LINK_RE = re.compile(r"\[[^\]]*\]\(\s*(<[^>\n]+>|[^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")
URL_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://")
ABS_WIN_RE = re.compile(r"^[a-zA-Z]:[\\/]")


def expand_status_patterns(patterns):
    out = []
    for p in patterns:
        out.append(p)
        if p.endswith("/**/*.md"):
            out.append(p[: -len("**/*.md")] + "*.md")
    return out


def classify_files(root, cfg):
    """把每个文本文件归到类别，算出实际长度和判定结果。"""
    doc_exts = tuple(e.lower() for e in cfg["doc_exts"])
    code_exts = tuple(e.lower() for e in cfg["code_exts"])
    tiers = list(cfg.get("text_tiers") or [])
    default = cfg.get("default_tier", 300)
    rows, unregistered = [], []
    for path, rp in C.walk_files(root, cfg):
        low = rp.lower()
        is_doc = low.endswith(doc_exts)
        is_code = low.endswith(code_exts)
        if not (is_doc or is_code):
            continue
        n = C.lf_char_count(path)
        if n is None:
            rows.append({"file": rp, "category": "二进制/编码不可读的文本后缀", "chars": None,
                         "limit": None, "result": "跳过（二进制）", "level": "警告"})
            continue
        rule = C.match_rule(rp, cfg)
        if is_code:
            limit = cfg.get("max_code_chars")
            rows.append({"file": rp, "category": rule["category"] if rule else "源码",
                         "chars": n, "limit": limit,
                         "result": "OK（软线）" if n <= limit else "超软线（警告）",
                         "level": "警告" if n > limit else None})
            continue
        if rule is None:
            limit = default
            category = "未登记文本（默认第一档）"
            unregistered.append(rp)
        else:
            limit = rule.get("limit")
            category = rule.get("category", "")
        if limit is None:
            result, level = "不按档位（已登记非管理类）", None
        elif limit not in tiers:
            result, level = "配置错误：上限 %s 不在档位表" % limit, "错误"
        elif n > limit:
            result, level = "超限 %d" % (n - limit), "错误"
        else:
            result, level = "OK 余 %d" % (limit - n), None
        rows.append({"file": rp, "category": category, "chars": n, "limit": limit,
                     "result": result, "level": level,
                     "generated": bool(rule and rule.get("generated"))})
    return rows, unregistered


def check_tiers(cfg):
    issues = []
    tiers = list(cfg.get("text_tiers") or [])
    default = cfg.get("default_tier")
    if default not in tiers:
        issues.append(C.err("default_tier=%s 不在档位表 %s 里" % (default, tiers)))
    for rule in cfg.get("paths") or []:
        lim = rule.get("limit")
        if lim is not None and lim not in tiers:
            issues.append(C.err("路径 %s 的上限 %s 不在档位表 %s 里" % (rule["glob"], lim, tiers)))
    return issues


def check_stale_config(root, cfg):
    issues = []
    for rule in cfg.get("paths") or []:
        g = rule["glob"]
        if any(ch in g for ch in "*?["):
            continue
        if not os.path.isfile(os.path.join(root, g.replace("/", os.sep))):
            issues.append(C.warn("配置登记了 %s，但文件不存在（改名或删除后没有同步配置）" % g))
    return issues


def check_required_reads(root, cfg):
    items, total = [], 0
    for name in cfg.get("required_reads") or []:
        p = os.path.join(root, name)
        size = os.path.getsize(p) if os.path.isfile(p) else 0
        total += size
        items.append({"file": name, "exists": os.path.isfile(p), "bytes": size})
    issues = []
    limit = cfg.get("max_required_bytes") or 0
    if total > limit:
        issues.append(C.err("必读文件合计 %d 字节，超过上限 %d 字节（接手成本过高）" % (total, limit)))
    for it in items:
        if not it["exists"]:
            issues.append(C.err("必读文件缺失: %s" % it["file"]))
    return items, total, limit, issues


def check_long_lines(root, cfg, rows):
    limit = cfg.get("max_long_line_chars") or 0
    hits = []
    for row in rows:
        if row["chars"] is None:
            continue
        if not row["file"].lower().endswith((".md", ".markdown")):
            continue
        text = C.read_text(os.path.join(root, row["file"].replace("/", os.sep)))
        for i, line in enumerate(text.splitlines(), 1):
            if len(line) > limit:
                hits.append({"file": row["file"], "line": i, "chars": len(line)})
    return hits, limit


def link_state(target, base_dir, root, by_name):
    t = target.strip()
    if t.startswith("<") and t.endswith(">"):
        t = t[1:-1].strip()
    if URL_RE.match(t):
        return "url", ""
    if t.startswith("#"):
        return "anchor", ""
    if t.startswith("mailto:"):
        return "url", ""
    if "{" in t:
        return "template", ""
    t = t.split("#", 1)[0].strip()
    if not t:
        return "anchor", ""
    try:
        from urllib.parse import unquote
        t = unquote(t)
    except Exception:
        pass
    if ABS_WIN_RE.match(t):
        resolved = os.path.normpath(t)
        return ("ok", "") if os.path.exists(resolved) else ("broken", "绝对路径不存在")
    resolved = os.path.normpath(os.path.join(base_dir, t.replace("/", os.sep)))
    rp = C.rel(root, resolved)
    if os.path.exists(resolved):
        return "ok", ""
    if rp.startswith(".."):
        return "broken", "指向项目目录之外"
    base = os.path.basename(t)
    if base in by_name:
        return "moved", "同名文件在 %s" % by_name[base]
    return "broken", "目标不存在"


def check_links(root, cfg, rows, all_files):
    by_name = {}
    for _, rp in all_files:
        by_name.setdefault(os.path.basename(rp), rp)
    stats = {"url": 0, "ok": 0, "broken": [], "moved": [], "md_files": 0}
    for row in rows:
        if not row["file"].lower().endswith((".md", ".markdown")):
            continue
        stats["md_files"] += 1
        path = os.path.join(root, row["file"].replace("/", os.sep))
        text = C.read_text(path)
        for lineno, line in enumerate(text.splitlines(), 1):
            for raw in LINK_RE.findall(line):
                state, why = link_state(raw, os.path.dirname(path), root, by_name)
                if state == "url":
                    stats["url"] += 1
                elif state == "ok":
                    stats["ok"] += 1
                else:
                    item = {"file": row["file"], "line": lineno, "target": raw, "why": why,
                            "managed": row["limit"] is not None}
                    if state == "moved":
                        stats["moved"].append(item)
                    else:
                        stats["broken"].append(item)
    return stats


def check_generated(root, cfg, rows):
    """脚本生成物第一屏必须有生成命令标记。名单在配置的 generated_globs 里。"""
    need = cfg.get("generated_header") or "生成命令:"
    globs = cfg.get("generated_globs") or []
    bad = []
    for row in rows:
        if not any(fnmatch.fnmatchcase(row["file"], g) for g in globs):
            continue
        path = os.path.join(root, row["file"].replace("/", os.sep))
        head = "\n".join(C.read_text(path).splitlines()[:12])
        needle = "生成命令" if row["file"].lower().endswith(".json") else need
        if needle not in head:
            bad.append(row["file"])
    return bad


def check_status_lines(root, cfg, rows):
    prefix = cfg.get("status_prefix") or "状态:"
    enum = list(cfg.get("status_enum") or [])
    window = int(cfg.get("status_header_lines") or 10)
    pats = expand_status_patterns(cfg.get("status_files") or [])
    bad, checked = [], 0
    for row in rows:
        if not any(fnmatch.fnmatchcase(row["file"], p) for p in pats):
            continue
        checked += 1
        path = os.path.join(root, row["file"].replace("/", os.sep))
        lines = C.read_text(path).splitlines()[:window]
        value = None
        for line in lines:
            s = line.strip().lstrip(">-* ").strip(BT)
            if s.startswith(prefix):
                value = s[len(prefix):].strip().strip("*" + BT + " ")
                break
        if value is None:
            bad.append({"file": row["file"], "why": "前 %d 行没有状态行（%s）" % (window, prefix)})
            continue
        token = value.split()[0] if value.split() else ""
        if token not in enum:
            bad.append({"file": row["file"], "why": "状态词 %r 不在 %s 里" % (token, enum)})
    return bad, checked


def check_pending(root, cfg, rows):
    words = cfg.get("pending_words") or []
    refs = cfg.get("registry_refs") or []
    limit = cfg.get("max_pending_files")
    per_file = {}
    ref_lines = 0
    for row in rows:
        if not row["category"].startswith(("管理文档",)):
            continue
        path = os.path.join(root, row["file"].replace("/", os.sep))
        n = 0
        for line in C.read_text(path).splitlines():
            stripped = line.strip()
            if not (stripped.startswith(("- ", "* ", "+ ")) or re.match(r"^\d+\.\s", stripped)
                    or stripped.startswith("#")):
                continue
            hits = sum(line.count(w) for w in words)
            if not hits:
                continue
            if any(r in line for r in refs):
                ref_lines += 1
                continue
            n += hits
        if n:
            per_file[row["file"]] = n
    over = limit is not None and len(per_file) > limit
    return per_file, ref_lines, over, limit


def check_claims(root, cfg, rows):
    words = cfg.get("claim_words") or []
    hits = []
    for row in rows:
        if not row["category"].startswith(("管理文档", "阅读笔记")):
            continue
        path = os.path.join(root, row["file"].replace("/", os.sep))
        for lineno, line in enumerate(C.read_text(path).splitlines(), 1):
            for w in words:
                if w not in line or BT in line or "/" in line:
                    continue
                pos = line.index(w)
                before = line[max(0, pos - 12):pos]
                if any(ch in before for ch in "不未没别勿禁非"):
                    continue
                hits.append({"file": row["file"], "line": lineno, "word": w,
                             "text": line.strip()[:70]})
    return hits


def check_formats(root, cfg):
    doc_exts = tuple(e.lower() for e in cfg["doc_exts"])
    code_exts = tuple(e.lower() for e in cfg["code_exts"])
    counts = {}
    for _, rp in C.walk_files(root, cfg):
        low = rp.lower()
        if low.endswith(doc_exts) or low.endswith(code_exts):
            continue
        ext = os.path.splitext(low)[1] or "(无后缀)"
        counts[ext] = counts.get(ext, 0) + 1
    return counts


def run_checks(root, cfg):
    rows, unregistered = classify_files(root, cfg)
    all_files = C.walk_files(root, cfg)
    issues = []
    issues += check_tiers(cfg)
    issues += check_stale_config(root, cfg)
    reads, read_total, read_limit, read_issues = check_required_reads(root, cfg)
    issues += read_issues

    for r in rows:
        if r.get("result", "").startswith("超软线"):
            issues.append(C.warn("%s 源码 %d 字符超过软线 %s（只提醒，不拦）" % (
                r["file"], r["chars"], r["limit"])))
    over = [r for r in rows if r["level"] == "错误"]
    for r in over:
        issues.append(C.err("%s 长度 %d 超过上限 %s（%s）" % (
            r["file"], r["chars"], r["limit"], r["result"])))

    long_hits, long_limit = check_long_lines(root, cfg, rows)
    if long_hits:
        issues.append(C.warn("%d 行超过 %d 字符（最长 %d，见 %s:%d）" % (
            len(long_hits), long_limit, max(h["chars"] for h in long_hits),
            long_hits[0]["file"], long_hits[0]["line"])))

    links = check_links(root, cfg, rows, all_files)
    for it in links["broken"]:
        f = C.err if it["managed"] else C.warn
        issues.append(f("失效链接 %s:%d -> %s（%s）" % (it["file"], it["line"], it["target"], it["why"])))
    for it in links["moved"]:
        issues.append(C.warn("疑似移动的链接 %s:%d -> %s（%s）" % (
            it["file"], it["line"], it["target"], it["why"])))

    gen_bad = check_generated(root, cfg, rows)
    for f in gen_bad:
        issues.append(C.err("生成物缺少生成命令标记: %s" % f))

    status_bad, status_checked = check_status_lines(root, cfg, rows)
    for it in status_bad:
        issues.append(C.err("状态行不合规 %s：%s" % (it["file"], it["why"])))

    pending, ref_lines, pending_over, pending_limit = check_pending(root, cfg, rows)
    if pending_over:
        issues.append(C.err("待办字样分散在 %d 个管理文档，超过配额 %d：%s" % (
            len(pending), pending_limit, ", ".join(sorted(pending)))))

    claims = check_claims(root, cfg, rows)
    for it in claims:
        issues.append(C.warn("声明性用语 %s:%d 的“%s”没有同行证据指针：%s" % (
            it["file"], it["line"], it["word"], it["text"])))

    formats = check_formats(root, cfg)
    return {
        "rows": rows, "unregistered": unregistered, "issues": issues,
        "reads": reads, "read_total": read_total, "read_limit": read_limit,
        "long": long_hits, "links": links, "gen_bad": gen_bad,
        "status_bad": status_bad, "status_checked": status_checked,
        "pending": pending, "pending_ref_lines": ref_lines, "pending_limit": pending_limit,
        "claims": claims, "formats": formats, "long_limit": long_limit,
    }


def summarize(res):
    rows = res["rows"]
    known = [r for r in rows if r["limit"] is not None]
    errs = [i for i in res["issues"] if i["level"] == "错误"]
    warns = [i for i in res["issues"] if i["level"] == "警告"]
    print("=== 文档检查 ===")
    print("文本文件 %d 个：按档位 %d、其余登记类 %d、未登记 %d；二进制跳过 %d" % (
        len(rows), len(known), len(rows) - len(known) - len(res["unregistered"]),
        len(res["unregistered"]), sum(1 for r in rows if r["chars"] is None)))
    print("长度：超限 %d，未登记文本 %d 个（从 300 档起）" % (
        sum(1 for r in rows if r["level"] == "错误"), len(res["unregistered"])))
    print("链接：Markdown %d 个，外链 %d，有效 %d，失效 %d，疑似移动 %d" % (
        res["links"]["md_files"], res["links"]["url"], res["links"]["ok"],
        len(res["links"]["broken"]), len(res["links"]["moved"])))
    print("状态行：应有 %d，不合规 %d；待办分散 %d 个文件（配额 %s）" % (
        res["status_checked"], len(res["status_bad"]), len(res["pending"]), res["pending_limit"]))
    print("错误 %d，警告 %d" % (len(errs), len(warns)))
    for item in errs[:30]:
        print("  [错误] " + item["msg"])
    if len(errs) > 30:
        print("  ... 另有 %d 条错误，见 --out 报告" % (len(errs) - 30))
    for item in warns[:12]:
        print("  [警告] " + item["msg"])
    if len(warns) > 12:
        print("  ... 另有 %d 条警告，见 --out 报告" % (len(warns) - 12))
    return len(errs)


def build_report(res, cmd):
    rows = res["rows"]
    lines = C.report_header("文档与链接检查报告", cmd)
    errs = [i for i in res["issues"] if i["level"] == "错误"]
    warns = [i for i in res["issues"] if i["level"] == "警告"]
    lines += [
        "## 结论",
        "",
        "错误 %d 条，警告 %d 条。" % (len(errs), len(warns)),
        "",
        "## 必读文件",
        "",
        C.table(["文件", "存在", "字节"],
                [[i["file"], "是" if i["exists"] else "否", i["bytes"]] for i in res["reads"]]),
        "",
        "合计 %d / 上限 %d 字节。" % (res["read_total"], res["read_limit"]),
        "",
        "## 长度（按类别）",
        "",
        C.table(["文件", "类别", "实际长度", "上限", "结果"],
                [[r["file"], r["category"], "—" if r["chars"] is None else r["chars"],
                  "—" if r["limit"] is None else r["limit"], r["result"]] for r in rows]),
        "",
        "## 问题明细",
        "",
    ]
    if not errs and not warns:
        lines.append("无。")
    for item in errs + warns:
        lines.append("- [%s] %s" % (item["level"], item["msg"]))
    lines += ["", "## 未检查的格式", "",
              "这些文件不按文本规则检查（PDF 由 scripts/lit_index.py 校验页数与 SHA-256）：", ""]
    lines += ["- %s: %d 个" % (ext, n) for ext, n in sorted(res["formats"].items())]
    lines += ["", "## 口径", "",
              "长度 = LF 归一化后的 Unicode 字符数，含空格与标点；CRLF 与 LF 结果相同。",
              "档位表 %s；未登记文本从 300 档起，登记后才升档。" % (res.get("tiers") or "见配置"),
              "历史记录、证据、机器生成物不按管理文档档位判定，但长度仍如实报告。"]
    return lines


def selftest():
    """用临时目录自测：CRLF/LF 同值、超限检出、中文路径与空格、登记类别、重复运行稳定。"""
    tmp = tempfile.mkdtemp(prefix="checkdocs_")
    ok = True

    def expect(cond, msg):
        nonlocal ok
        print(("  通过 " if cond else "  失败 ") + msg)
        ok = ok and bool(cond)

    try:
        root = os.path.join(tmp, "测试 项目")
        os.makedirs(os.path.join(root, "docs"), exist_ok=True)
        os.makedirs(os.path.join(root, "scripts"), exist_ok=True)
        cfg = {
            "text_tiers": [300, 1000, 3200],
            "default_tier": 300,
            "doc_exts": [".md", ".txt"],
            "code_exts": [".py"],
            "skip_dirs": [".git"],
            "paths": [
                {"glob": "README.md", "category": "管理文档", "limit": 1000},
                {"glob": "docs/gen.md", "category": "机器生成", "limit": None, "generated": True},
                {"glob": "docs/*.md", "category": "管理文档", "limit": 300},
                {"glob": "历史/*.md", "category": "历史记录", "limit": None},
                {"glob": "docs/gen.md", "category": "机器生成", "limit": None, "generated": True},
            ],
            "required_reads": ["README.md"],
            "max_required_bytes": 5000,
            "max_long_line_chars": 50,
            "generated_header": "生成命令:",
            "generated_globs": ["docs/gen.md", "docs/gen2.md"],
            "status_files": ["docs/*.md"],
            "status_prefix": "状态:",
            "status_enum": ["草案", "生效"],
            "status_header_lines": 12,
            "pending_words": ["待办"],
            "max_pending_files": 1,
            "registry_refs": ["docs/TODO.md"],
            "claim_words": ["已精读"],
            "max_code_chars": 2000,
        }
        import json
        with open(os.path.join(root, "repo-discipline.json"), "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, ensure_ascii=False)
        body = "# 标题\n\n" + "中文内容" * 10 + "\n"
        with open(os.path.join(root, "README.md"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
        with open(os.path.join(root, "README_crlf.md"), "w", encoding="utf-8", newline="\r\n") as fh:
            fh.write(body)
        n1 = C.lf_char_count(os.path.join(root, "README.md"))
        n2 = C.lf_char_count(os.path.join(root, "README_crlf.md"))
        expect(n1 == n2, "CRLF 与 LF 的字符数相同（%d == %d）" % (n1, n2))
        expect(n1 == len(body.replace("\r\n", "\n")), "字符数等于 LF 归一化后的 len()，含空格与标点")

        os.makedirs(os.path.join(root, "历史"), exist_ok=True)
        with open(os.path.join(root, "docs", "待 办.md"), "w", encoding="utf-8") as fh:
            fh.write("状态: 生效\n\n" + "字" * 400 + "\n")
        with open(os.path.join(root, "历史", "旧 记录.md"), "w", encoding="utf-8") as fh:
            fh.write("字" * 5000 + "\n")
        with open(os.path.join(root, "docs", "gen.md"), "w", encoding="utf-8") as fh:
            fh.write("生成命令: python x.py\n" + "字" * 5000 + "\n")
        root_abs = C.find_root(root)
        expect(os.path.normcase(root_abs) == os.path.normcase(os.path.abspath(root)),
               "find_root 在中文路径 + 空格下找到配置")
        res = run_checks(root_abs, C.load_config(root_abs))
        files = {r["file"]: r for r in res["rows"]}
        expect(files["docs/待 办.md"]["level"] == "错误", "中文文件名 + 空格的管理文档按 300 档检出超限")
        expect(files["历史/旧 记录.md"]["limit"] is None, "历史记录不按管理文档档位判定")
        expect(files["docs/gen.md"]["result"].startswith("不按档位"), "机器生成物不按档位判定")
        expect(res["gen_bad"] == [], "生成物带生成命令标记时不报错")
        with open(os.path.join(root, "docs", "gen2.md"), "w", encoding="utf-8") as fh:
            fh.write("没有标记\n")
        cfg["paths"].insert(2, {"glob": "docs/gen2.md", "category": "机器生成", "limit": None,
                                "generated": True})
        with open(os.path.join(root, "repo-discipline.json"), "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, ensure_ascii=False)
        res2 = run_checks(root_abs, C.load_config(root_abs))
        expect("docs/gen2.md" in res2["gen_bad"], "生成物缺少标记时被检出")
        with open(os.path.join(root, "docs", "链接.md"), "w", encoding="utf-8") as fh:
            fh.write("状态: 生效\n\n[好](<../历史/旧 记录.md>) [坏](../不存在.md)\n")
        res3 = run_checks(root_abs, C.load_config(root_abs))
        broken = [b["target"] for b in res3["links"]["broken"]]
        expect(any("不存在" in b for b in broken), "失效链接被检出")
        expect(not any("旧 记录" in b for b in broken), "含空格的中文相对链接能正确解析")
        a = run_checks(root_abs, C.load_config(root_abs))
        b = run_checks(root_abs, C.load_config(root_abs))
        expect(len(a["issues"]) == len(b["issues"]), "重复运行结果稳定（问题条数一致）")
        before = {r: os.path.getsize(os.path.join(root, r)) for r in ("README.md", "docs/待 办.md")}
        run_checks(root_abs, C.load_config(root_abs))
        after = {r: os.path.getsize(os.path.join(root, r)) for r in ("README.md", "docs/待 办.md")}
        expect(before == after, "检查过程不修改被检文件")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("自测结果: " + ("全部通过" if ok else "有失败"))
    return ok


def main():
    ap = argparse.ArgumentParser(description="只读检查文档长度档位、长行、链接、状态行、待办分散")
    ap.add_argument("--root", default=None, help="项目根目录，默认从当前目录向上找")
    ap.add_argument("--config", default=None, help="配置文件，默认 <root>/repo-discipline.json")
    ap.add_argument("--out", default=None, help="把完整报告写到这个路径（不写就只打印）")
    ap.add_argument("--selftest", action="store_true", help="用临时目录自测")
    args = ap.parse_args()
    if args.selftest:
        return 0 if selftest() else 1
    root = os.path.abspath(args.root) if args.root else C.find_root()
    cfg = C.load_config(root, args.config)
    res = run_checks(root, cfg)
    res["tiers"] = cfg.get("text_tiers")
    nerr = summarize(res)
    if args.out:
        cmd = "python scripts/check_docs.py --root . --out " + os.path.relpath(args.out, root).replace("\\", "/")
        lines = build_report(res, cmd)
        C.write_report(args.out, lines)
        print("报告: " + os.path.abspath(args.out))
    return 1 if nerr else 0


if __name__ == "__main__":
    sys.exit(main())
