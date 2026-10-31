#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一文献索引：合并配置所指的 P/M 分组清单，核对 PDF 与校验值。

数据来源（只读）:
    research/ev_parking_math_20261029/sources.json         书目与核验深度
    research/ev_parking_math_20261029/download_manifest.csv 下载状态与 SHA-256（GBK 兼容）
    research/ev_parking_math_20261029/download_status.json  下载过程记录
    papers/electrification-math/download_manifest.json      M 组下载记录
    literature/reading-log.json                             人工登记的阅读状态
默认只打印；写索引必须显式给 --write（或 --out-index/--out-md）。
用法:
    python scripts/lit_index.py
    python scripts/lit_index.py --write
    python scripts/lit_index.py --check-index
退出码 0 = 没有错误；1 = 有错误；2 = 用法错误。
"""

import argparse
import fnmatch
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C  # noqa: E402

PAGE_RE = re.compile(rb"/Type\s*/Pages\b[^>]{0,300}?/Count\s+(\d+)")
PAGE_OBJ_RE = re.compile(rb"/Type\s*/Page[^s]")
CLAIM_RES = [
    re.compile(r"已取得\s*\**\s*(\d+)\s*/\s*(\d+)"),
    re.compile(r"共\s*(\d+)\s*篇独立\s*PDF"),
    re.compile(r"(\d+)\s*篇独立\s*PDF"),
    re.compile(r"仍有\s*(\d+)\s*篇待补"),
    re.compile(r"剩余\s*(\d+)\s*篇待补"),
]
PENDING_ROW_RE = re.compile(r"^\|\s*([PM]\d{2})\s*\|")


def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def load_csv(path):
    import csv
    import io
    text = C.decode_text(C.read_bytes(path))
    return list(csv.DictReader(io.StringIO(text)))


def norm_key(text):
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def pdf_facts(path):
    """只核对文件头、字节数与 SHA-256。PDF 页数不做独立解析：没有可靠解析库时按正则数页会在压缩对象上误判，宁可不报。"""
    data = C.read_bytes(path)
    return {
        "header_ok": data[:5] == b"%PDF-",
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "pages": None,
    }


def pick_pdf(root, candidates):
    for cand in candidates:
        if not cand:
            continue
        p = os.path.join(root, cand.replace("/", os.sep))
        if os.path.isfile(p):
            return cand.replace("\\", "/"), p
    return None, None


def build(root, cfg):
    lit = cfg["literature"]
    notes_dir = lit["notes_dir"]
    issues = []

    def add_issue(level, code, iid, msg):
        issues.append({"level": level, "code": code, "id": iid, "msg": msg})

    # ---------- P 组 ----------
    sources = load_json(os.path.join(root, lit["p_sources"].replace("/", os.sep)))
    status = load_json(os.path.join(root, lit["p_status"].replace("/", os.sep)))
    csv_rows = load_csv(os.path.join(root, lit["p_csv"].replace("/", os.sep)))
    csv_map = {row.get("编号", "").strip(): row for row in csv_rows}
    items = []
    for src in sources:
        iid = src["id"]
        st = status.get(iid) or {}
        row = csv_map.get(iid) or {}
        manifest_downloaded = (st.get("status") == "downloaded") or (row.get("状态") == "已下载")
        filename = st.get("filename") or os.path.basename((row.get("PDF文件") or "").strip())
        cands = []
        if row.get("PDF文件"):
            cands.append(lit["p_pdf_root"] + "/" + row["PDF文件"].strip().replace("\\", "/"))
        if filename:
            cands.append(lit["p_pdf_root"] + "/" + lit.get("p_pdf_subdir", "PDFs") + "/" + filename)
        rel_pdf, abs_pdf = pick_pdf(root, cands)
        facts = pdf_facts(abs_pdf) if abs_pdf else None
        sha_manifest = (st.get("sha256") or row.get("SHA256") or "").strip().lower()
        pages_manifest = st.get("pages") or (int(row["页数"]) if (row.get("页数") or "").strip().isdigit() else None)
        version = (row.get("版本或缺失原因") or st.get("version_note") or "").strip()
        items.append({
            "id": iid, "kind": "P", "group": src.get("group", ""), "priority": src.get("priority", ""),
            "year": src.get("year", ""), "authors": src.get("authors", ""), "title": src.get("title", ""),
            "venue": src.get("venue", ""), "doi": src.get("doi", ""), "url": src.get("url", ""),
            "verification_level": src.get("level", ""),
            "version": version, "local_pdf": rel_pdf,
            "pdf_pages_manifest": pages_manifest,
            "pdf_pages_measured": (facts or {}).get("pages"),
            "pdf_bytes": (facts or {}).get("bytes"),
            "pdf_header_ok": (facts or {}).get("header_ok"),
            "sha256": (facts or {}).get("sha256"),
            "sha256_manifest": sha_manifest,
            "_manifest_downloaded": manifest_downloaded,
            "_pdf_exists": bool(abs_pdf),
        })

    # ---------- M 组 ----------
    m_entries = {e["id"]: dict(e) for e in load_json(os.path.join(root, lit["m_manifest"].replace("/", os.sep)))}
    # Apply append-only imports without rewriting historical download records.
    for update_file in lit.get("m_download_updates", []):
        updates = load_json(os.path.join(root, update_file.replace("/", os.sep)))
        for update in updates.get("items", []):
            m_entries.setdefault(update["id"], {}).update(update)
    m_manifest = list(m_entries.values())
    for entry in m_manifest:
        iid = entry["id"]
        filename = entry.get("filename") or os.path.basename((entry.get("path") or "").replace("\\", "/"))
        cands = [lit["m_pdf_root"] + "/" + filename]
        rel_pdf, abs_pdf = pick_pdf(root, cands)
        facts = pdf_facts(abs_pdf) if abs_pdf else None
        items.append({
            "id": iid, "kind": "M", "group": "电气化拐点相关数学方法（M 组）",
            "priority": "", "year": entry.get("year", ""), "authors": entry.get("authors", ""),
            "title": entry.get("title", ""), "venue": entry.get("venue", ""),
            "doi": entry.get("doi", ""), "url": entry.get("source_url", ""),
            "verification_level": "下载清单记录；题名与首页预览核对",
            "version": entry.get("version", ""), "local_pdf": rel_pdf,
            "pdf_pages_manifest": entry.get("pages"),
            "pdf_pages_measured": (facts or {}).get("pages"),
            "pdf_bytes": (facts or {}).get("bytes"),
            "pdf_header_ok": (facts or {}).get("header_ok"),
            "sha256": (facts or {}).get("sha256"),
            "sha256_manifest": (entry.get("sha256") or "").strip().lower(),
            "_manifest_downloaded": entry.get("status") == "downloaded",
            "_pdf_exists": bool(abs_pdf),
        })

    # ---------- 校验 ----------
    for item in items:
        iid = item["id"]
        exists = item["_pdf_exists"]
        if item["_manifest_downloaded"] and not exists:
            add_issue("错误", "DOWN_MISSING", iid,
                      "清单记已下载，磁盘上没有对应 PDF（清单: %s）" % (item["version"] or "无版本说明"))
        if exists and not item["_manifest_downloaded"]:
            add_issue("错误", "FILE_UNLISTED", iid, "磁盘有 PDF，但下载清单记为未取得")
        if exists:
            if not item["pdf_header_ok"]:
                add_issue("错误", "PDF_HEADER", iid, "文件头不是 %PDF-")
            if item["sha256_manifest"] and item["sha256"] != item["sha256_manifest"]:
                add_issue("错误", "SHA_MISMATCH", iid, "SHA-256 与清单不一致（实际 %s…，清单 %s…）" % (
                    item["sha256"][:16], item["sha256_manifest"][:16]))
        if not item["sha256"] and not item["_manifest_downloaded"]:
            pass

    # 重复检测
    seen_sha, seen_doi, seen_title = {}, {}, {}
    for item in items:
        for key, store in (("sha256", seen_sha), ("doi", seen_doi), ("title", seen_title)):
            val = item.get(key)
            if key == "sha256" and not val:
                continue
            if key == "doi":
                val = (val or "").strip().lower()
                if not val or val == "-":
                    continue
            if key == "title":
                val = norm_key(val)
                if not val:
                    continue
            if val in store:
                add_issue("警告", "DUP_" + key.upper(), item["id"],
                          "与 %s 的 %s 重复（%s）" % (store[val], key, (item.get(key) or "")[:60]))
            else:
                store[val] = item["id"]

    # 编号完整性
    for kind in ("P", "M"):
        ids = [i["id"] for i in items if i["kind"] == kind]
        nums = sorted(int(x[1:]) for x in ids if x[1:].isdigit())
        if nums and nums != list(range(1, len(nums) + 1)):
            add_issue("警告", "ID_GAP", kind, "%s 组编号不连续: %s" % (kind, nums))

    # ---------- 阅读状态 ----------
    log_path = os.path.join(root, lit["reading_log"].replace("/", os.sep))
    reading = {"defaults": {"P": {"read_status": "未开始", "evidence": []},
                            "M": {"read_status": "未开始", "evidence": []}},
               "items": {}}
    if os.path.isfile(log_path):
        reading = load_json(log_path)
    states = lit.get("read_states") or []
    require_note = lit.get("read_state_requires_note") or []
    for item in items:
        entry = (reading.get("items") or {}).get(item["id"]) or (reading.get("defaults") or {}).get(
            item["kind"]) or {"read_status": "未开始", "evidence": []}
        state = entry.get("read_status", "未开始")
        if states and state not in states:
            add_issue("错误", "READ_STATE", item["id"], "阅读状态 %r 不在允许值 %s 里" % (state, states))
        evidence = []
        for ev in entry.get("evidence") or []:
            p = os.path.join(root, ev.replace("/", os.sep))
            evidence.append({"path": ev, "exists": os.path.isfile(p)})
            if not os.path.isfile(p):
                add_issue("错误", "READ_EVIDENCE", item["id"], "阅读状态依据不存在: " + ev)
        note_files = []
        nd = os.path.join(root, notes_dir.replace("/", os.sep))
        if os.path.isdir(nd):
            for name in sorted(os.listdir(nd)):
                if name.startswith(item["id"]) and name.lower().endswith(".md"):
                    note_files.append(notes_dir + "/" + name)
        if state in require_note and not note_files:
            add_issue("错误", "NO_NOTE", item["id"],
                      "阅读状态为 %s，但 %s 下没有 %s 开头的笔记文件" % (state, notes_dir, item["id"]))
        item["read_status"] = state
        item["read_evidence"] = evidence
        item["read_note"] = note_files
        notes = []
        for p in (lit.get("note_sources") or {}).get(item["kind"], []):
            if os.path.isfile(os.path.join(root, p.replace("/", os.sep))):
                notes.append({"path": p, "what": "研究笔记与融合建议（不是精读笔记）"})
        for p in note_files:
            notes.append({"path": p, "what": "精读笔记"})
        item["notes"] = notes
        item.pop("_manifest_downloaded")
        item.pop("_pdf_exists")
        if item["local_pdf"]:
            item["download_status"] = ("已下载（文件存在，SHA-256 与清单一致）"
                                       if item["sha256"] and item["sha256"] == item["sha256_manifest"]
                                       else "已下载（文件存在，但清单无校验值或校验不一致）")
        elif item["pdf_pages_manifest"] or item["sha256_manifest"]:
            item["download_status"] = "清单记已下载，磁盘缺失"
        else:
            item["download_status"] = "未下载"

    # ---------- 与历史清单的数量差异 ----------
    p_total = len([i for i in items if i["kind"] == "P"])
    m_total = len([i for i in items if i["kind"] == "M"])
    p_down = len([i for i in items if i["kind"] == "P" and i["local_pdf"]])
    m_down = len([i for i in items if i["kind"] == "M" and i["local_pdf"]])
    total, down = len(items), p_down + m_down
    skip_dirs = set(cfg.get("skip_dirs") or [])
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for name in filenames:
            if not name.lower().endswith((".md", ".markdown")):
                continue
            p = os.path.join(dirpath, name)
            relp = C.rel(root, p)
            lines = C.read_text(p).splitlines()
            for lineno, line in enumerate(lines, 1):
                for rx in CLAIM_RES[:1]:
                    for m in rx.finditer(line):
                        n, d = int(m.group(1)), int(m.group(2))
                        if d == p_total:
                            actual = p_down
                        elif d == m_total:
                            actual = m_down
                        elif d == total:
                            actual = down
                        else:
                            continue
                        if n != actual:
                            add_issue("警告", "STALE_COUNT", relp,
                                      "第 %d 行声称 %d/%d，实测 %d/%d（历史记录，未改写）" % (
                                          lineno, n, d, actual, d))
                for rx in CLAIM_RES[1:3]:
                    for m in rx.finditer(line):
                        n = int(m.group(1))
                        if 0 < n < 200 and n != down:
                            add_issue("警告", "STALE_TOTAL", relp,
                                      "第 %d 行声称 %d 篇 PDF，实测 %d 篇（历史记录，未改写）" % (
                                          lineno, n, down))
                for rx in CLAIM_RES[3:]:
                    for m in rx.finditer(line):
                        n = int(m.group(1))
                        missing = total - down
                        if n != missing:
                            add_issue("警告", "STALE_PENDING", relp,
                                      "第 %d 行声称 %d 篇待补，实测 %d 篇（历史记录，未改写）" % (
                                          lineno, n, missing))
    # 过时待下载清单
    for pat in lit.get("pending_lists") or []:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            for name in filenames:
                if not fnmatch.fnmatchcase(name, pat):
                    continue
                p = os.path.join(dirpath, name)
                relp = C.rel(root, p)
                for lineno, line in enumerate(C.read_text(p).splitlines(), 1):
                    m = PENDING_ROW_RE.match(line.strip())
                    if not m:
                        continue
                    iid = m.group(1)
                    hit = [i for i in items if i["id"] == iid]
                    if hit and hit[0]["local_pdf"]:
                        add_issue("警告", "STALE_PENDING_LIST", relp,
                                  "第 %d 行仍把 %s 列为待下载，但索引里已有 PDF" % (lineno, iid))

    return items, issues, {"total": total, "down": down, "missing": total - down,
                           "p_total": p_total, "p_down": p_down,
                           "m_total": m_total, "m_down": m_down}


def digest(items):
    payload = json.dumps(items, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def index_payload(items, issues, counts, cmd):
    return {
        "生成命令": cmd,
        "生成时间": C.now_str(),
        "口径": "LF 归一化字符与文件系统实测；阅读状态以 literature/reading-log.json 为准，未登记时按分组默认值。",
        "counts": counts,
        "items": items,
        "issues": issues,
    }


def summarize(items, issues, counts, existing_digest=None):
    print("=== 文献索引 ===")
    print("条目 %d（P %d、M %d），已下载 %d，缺全文 %d" % (
        counts["total"], counts["p_total"], counts["m_total"], counts["down"], counts["missing"]))
    states = {}
    for item in items:
        states[item["read_status"]] = states.get(item["read_status"], 0) + 1
    print("阅读状态: " + "，".join("%s %d" % (k, v) for k, v in sorted(states.items())))
    errs = [i for i in issues if i["level"] == "错误"]
    warns = [i for i in issues if i["level"] == "警告"]
    print("错误 %d，警告 %d" % (len(errs), len(warns)))
    for item in errs:
        print("  [错误] %s %s: %s" % (item["id"], item["code"], item["msg"]))
    for item in warns[:10]:
        print("  [警告] %s %s: %s" % (item["id"], item["code"], item["msg"]))
    if len(warns) > 10:
        print("  ... 另有 %d 条警告" % (len(warns) - 10))
    if existing_digest is not None:
        print("索引摘要: " + existing_digest[:16] + "…")
    return len(errs)


def build_index_md(items, issues, counts, cmd):
    lines = C.report_header("文献索引", cmd)
    lines += [
        "## 计数",
        "",
        C.table(["范围", "条目", "已下载", "缺全文"],
                [["P01-P%02d" % counts["p_total"], counts["p_total"], counts["p_down"],
                  counts["p_total"] - counts["p_down"]],
                 ["M01-M%02d" % counts["m_total"], counts["m_total"], counts["m_down"],
                  counts["m_total"] - counts["m_down"]],
                 ["合计", counts["total"], counts["down"], counts["missing"]]]),
        "",
        "阅读状态默认取分组值：P 组依据 sources.json 的 level 字段（摘要与元数据层面的核验），",
        "M 组依据 plan/notes.md；两者都不是精读记录。要标成“精读并记笔记”必须先有 literature/notes/ 下的笔记文件。",
        "",
        "## 条目",
        "",
    ]
    groups = {}
    for item in items:
        groups.setdefault((item["kind"], item["group"]), []).append(item)
    for (kind, group) in sorted(groups, key=lambda k: (k[0], k[1])):
        lines.append("### %s 组 · %s" % (kind, group))
        lines.append("")
        for item in sorted(groups[(kind, group)], key=lambda i: i["id"]):
            title = item["title"] or "(题名缺失)"
            lines.append("#### %s %s" % (item["id"], title))
            meta = []
            if item.get("year"):
                meta.append("年份 " + str(item["year"]))
            if item.get("authors"):
                meta.append(item["authors"])
            if item.get("priority"):
                meta.append("用途 " + item["priority"])
            if meta:
                lines.append("- " + "；".join(meta))
            if item.get("doi"):
                lines.append("- DOI: %s" % item["doi"])
            if item.get("venue"):
                lines.append("- 出处: %s" % item["venue"])
            if item.get("url"):
                lines.append("- 入口: " + item["url"])
            if item.get("version"):
                lines.append("- 版本: %s" % item["version"])
            if item.get("verification_level"):
                lines.append("- 查证深度: %s" % item["verification_level"])
            if item.get("local_pdf"):
                pdf = item["local_pdf"]
                pages = item.get("pdf_pages_measured") or item.get("pdf_pages_manifest")
                size = item.get("pdf_bytes")
                sha = (item.get("sha256") or "")[:16]
                lines.append("- PDF: [%s](<%s>)（%s 页，%s 字节，SHA-256 %s…）" % (
                    os.path.basename(pdf), "../" + pdf, pages if pages else "?",
                    size if size else "?", sha or "无"))
            else:
                lines.append("- PDF: 未取得")
            lines.append("- 下载: " + item["download_status"])
            evidence = "、".join(e["path"] for e in item.get("read_evidence") or []) or "无"
            lines.append("- 阅读: %s（依据 %s）" % (item["read_status"], evidence))
            if item.get("notes"):
                lines.append("- 笔记: " + "；".join(
                    "%s（%s）" % (n["path"], n["what"]) for n in item["notes"]))
            lines.append("")
    lines += ["## 校验发现", ""]
    if not issues:
        lines.append("无。")
    for item in issues:
        lines.append("- [%s] %s %s: %s" % (item["level"], item["id"], item["code"], item["msg"]))
    return lines


def build_issues_md(items, issues, counts, cmd):
    lines = C.report_header("文献索引检查报告", cmd)
    errs = [i for i in issues if i["level"] == "错误"]
    warns = [i for i in issues if i["level"] == "警告"]
    lines += [
        "## 结论",
        "",
        "条目 %d（P %d、M %d），已下载 %d，缺全文 %d；错误 %d 条，警告 %d 条。" % (
            counts["total"], counts["p_total"], counts["m_total"], counts["down"],
            counts["missing"], len(errs), len(warns)),
        "",
        "## 分组计数",
        "",
        C.table(["范围", "条目", "已下载", "缺全文"],
                [["P01-P%02d" % counts["p_total"], counts["p_total"], counts["p_down"],
                  counts["p_total"] - counts["p_down"]],
                 ["M01-M%02d" % counts["m_total"], counts["m_total"], counts["m_down"],
                  counts["m_total"] - counts["m_down"]],
                 ["合计", counts["total"], counts["down"], counts["missing"]]]),
        "",
        "## 问题明细",
        "",
    ]
    if not issues:
        lines.append("无。")
    for item in errs + warns:
        lines.append("- [%s] %s %s: %s" % (item["level"], item["id"], item["code"], item["msg"]))
    lines += [
        "",
        "## 校验范围与限制",
        "",
        "- 已校验：PDF 文件头、字节数、SHA-256 与清单一致；编号连续；重复 SHA/DOI/题名；阅读状态与笔记存在性。",
        "- 未独立校验：PDF 页数只取清单记录。没有可靠解析库时按正则数页会在压缩对象上误判，宁可不报。",
        "- 历史记录只读：数量差异以警告形式列出，不改写 plan/、research/、papers/ 里的原文。",
        "- 阅读状态以 literature/reading-log.json 为准；未登记条目按分组默认值。",
    ]
    return lines


def main():
    ap = argparse.ArgumentParser(description="生成并校验统一文献索引")
    ap.add_argument("--root", default=None)
    ap.add_argument("--config", default=None)
    ap.add_argument("--write", action="store_true", help="把 index.json 与 INDEX.md 写回配置路径")
    ap.add_argument("--out-index", default=None, help="自定义 index.json 输出路径")
    ap.add_argument("--out-md", default=None, help="自定义 INDEX.md 输出路径")
    ap.add_argument("--check-index", action="store_true", help="只比对现有索引是否过期")
    ap.add_argument("--out-report", default=None, help="把索引检查报告写到这个路径")
    args = ap.parse_args()
    root = os.path.abspath(args.root) if args.root else C.find_root()
    cfg = C.load_config(root, args.config)
    lit = cfg["literature"]
    items, issues, counts = build(root, cfg)
    index_path = args.out_index or os.path.join(root, lit["index_json"].replace("/", os.sep))
    md_path = args.out_md or os.path.join(root, lit["index_md"].replace("/", os.sep))
    existing = None
    if os.path.isfile(index_path):
        try:
            with open(index_path, "r", encoding="utf-8-sig") as fh:
                existing = json.load(fh)
        except Exception:
            existing = None
    stale = existing is not None and digest(existing.get("items")) != digest(items)
    if args.out_report:
        rel_report = os.path.relpath(args.out_report, root).replace("\\", "/")
        lines = build_issues_md(items, issues, counts,
                                "python scripts/lit_index.py --check-index --out-report " + rel_report)
        C.write_report(args.out_report, lines)
        print("问题报告: " + os.path.abspath(args.out_report))
    if args.check_index:
        if existing is None:
            print("索引不存在或无法读取: " + os.path.abspath(index_path))
            return 1
        if stale:
            print("索引已过期：数据变了但索引没重写。请运行 python scripts/lit_index.py --write")
            return 1
        print("索引与数据一致（摘要 %s…，%d 条）" % (digest(items)[:16], len(items)))
        nerr = summarize(items, issues, counts)
        return 1 if nerr else 0
    nerr = summarize(items, issues, counts)
    if args.write or args.out_index or args.out_md:
        if args.write or args.out_index:
            cmd = "python scripts/lit_index.py --write"
            payload = index_payload(items, issues, counts, cmd)
            os.makedirs(os.path.dirname(os.path.abspath(index_path)), exist_ok=True)
            with open(index_path, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            print("索引 JSON: " + os.path.abspath(index_path))
        if args.write or args.out_md:
            cmd = "python scripts/lit_index.py --write"
            lines = build_index_md(items, issues, counts, cmd)
            C.write_report(md_path, lines)
            print("索引 Markdown: " + os.path.abspath(md_path))
    else:
        print("（未写入：只读模式。要写索引用 --write 或 --out-index/--out-md）")
    return 1 if nerr else 0


if __name__ == "__main__":
    sys.exit(main())
