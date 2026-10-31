#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统计论文稿件字数：分别给出汉字数、英文词数与字符数，并核对章节清单里的字数。

统计对象是 docx 的段落文字，不采用 Word 写在 docProps/app.xml 里的缓存字数。
默认只打印；写文件必须显式给 --out / --json / --write-sections。
用法:
    python scripts/paper_stats.py
    python scripts/paper_stats.py --out docs/reports/2026-10-30-字数报告.md --json docs/reports/2026-10-30-字数报告.json
    python scripts/paper_stats.py --check-sections
    python scripts/paper_stats.py --write-sections
退出码 0 = 正常；1 = 章节清单字数与实际不符；2 = 用法或稿件读取错误。
"""

import argparse
import json
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C  # noqa: E402

CJK_RE = re.compile(
    "[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002a6df\U0002f800-\U0002fa1f]")
WORD_RE = re.compile("[A-Za-z][A-Za-z'\u2019\\-]*")
MATH_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
SEC_RE = re.compile(r"<!-- stats:(S\d) -->\n(.*?)\n<!-- /stats:\1 -->", re.S)

SECTION_NAMES = {
    "S0": "题名、摘要与关键词",
    "S1": "Introduction",
    "S2": "Results",
    "S3": "Discussion",
    "S4": "Methods",
    "S5": "References",
    "S6": "Data availability and code availability",
    "S7": "Ethics declarations",
}


def measure(text):
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    han = len(CJK_RE.findall(text))
    words = len(WORD_RE.findall(text))
    return {"han": han, "words": words, "chars": len(text)}


def math_count(paragraph):
    try:
        return len(paragraph._element.findall(".//" + MATH_NS + "oMath"))
    except Exception:
        return 0


def classify(doc, cfg):
    pcfg = cfg.get("paper") or {}
    paras = doc.paragraphs
    texts = [(p.text or "").strip() for p in paras]
    styles = [p.style.name for p in paras]

    def find_heading(name, start=0, level="Heading 1"):
        for i in range(start, len(paras)):
            if styles[i] == level and texts[i] == name:
                return i
        return -1

    abstract_i = -1
    for i, t in enumerate(texts):
        if t == pcfg.get("title_to_abstract") and not styles[i].startswith("Heading"):
            abstract_i = i
            break
    kw_prefix = pcfg.get("keywords_prefix") or "Keywords:"
    keywords_i = -1
    for i in range(max(abstract_i, 0), len(paras)):
        if texts[i].startswith(kw_prefix):
            keywords_i = i
            break
    body_start_i = find_heading(pcfg.get("body_start") or "Introduction")
    body_end_i = find_heading(pcfg.get("body_end") or "References", body_start_i if body_start_i >= 0 else 0)
    back_i = find_heading(pcfg.get("back_matter_start") or "Data availability and code availability",
                          body_end_i if body_end_i >= 0 else 0)

    sections = {}

    def add(key, idxs, include_label=True):
        rows = [i for i in idxs if 0 <= i < len(paras)]
        sec = {"key": key, "name": SECTION_NAMES.get(key, key), "paras": [], "captions": [],
               "labels": [], "formulas": 0}
        for i in rows:
            p = paras[i]
            t = texts[i]
            sec["formulas"] += math_count(p)
            if styles[i] == "Caption":
                sec["captions"].append({"index": i, "text": t})
                continue
            if not t:
                continue
            if styles[i] in ("Heading 1", "Heading 2"):
                sec["paras"].append({"index": i, "text": t, "style": styles[i]})
                continue
            if key == "S5" and styles[i] == "Bibliography":
                sec["paras"].append({"index": i, "text": t, "style": styles[i]})
            elif i in getattr(add, "labels", {}):
                sec["labels"].append(t)
            else:
                sec["paras"].append({"index": i, "text": t, "style": styles[i]})
            sec["formulas"] += math_count(p)
        sections[key] = sec
        return sec

    add.labels = {}
    # S0: 题名 + 摘要正文 + 关键词
    if abstract_i < 0:
        raise SystemExit("找不到摘要标记（配置 paper.title_to_abstract），无法切分稿件范围")
    s0_idx = list(range(0, max(keywords_i, abstract_i) + 1))
    add.labels = {abstract_i, keywords_i}
    add("S0", s0_idx)

    # 正文：按 Heading 1 / Heading 2 切
    if body_start_i >= 0 and body_end_i > body_start_i:
        bounds = [i for i in range(body_start_i, body_end_i)
                  if styles[i] in ("Heading 1", "Heading 2")]
        h1 = [i for i in bounds if styles[i] == "Heading 1"]
        for n, i in enumerate(h1):
            key = "S%d" % (n + 1)
            sections.setdefault(key, {"key": key, "name": texts[i], "paras": [], "captions": [],
                                      "labels": [], "formulas": 0})
            sec = sections[key]
            sec["name"] = texts[i]
            end = h1[n + 1] if n + 1 < len(h1) else body_end_i
            for j in range(i, end):
                p = paras[j]
                t = texts[j]
                sec["formulas"] += math_count(p)
                if styles[j] == "Caption":
                    sec["captions"].append({"index": j, "text": t})
                    continue
                if not t:
                    continue
                sec["paras"].append({"index": j, "text": t, "style": styles[j]})
    # S5 参考文献
    if body_end_i >= 0:
        end = back_i if back_i > body_end_i else len(paras)
        s5 = add("S5", list(range(body_end_i, end)))
        s5["entries"] = len([1 for i in range(body_end_i, end)
                            if styles[i] == "Bibliography" and texts[i]])
    # 后置声明 S6 S7
    if back_i >= 0:
        h1 = [i for i in range(back_i, len(paras)) if styles[i] == "Heading 1"]
        for n, i in enumerate(h1):
            key = "S%d" % (6 + n)
            end = h1[n + 1] if n + 1 < len(h1) else len(paras)
            sec = add(key, list(range(i, end)))
            sec["name"] = texts[i]

    # 汇总
    totals, assigned = {"han": 0, "words": 0, "chars": 0, "paras": 0, "formulas": 0}, {}
    for key, sec in sections.items():
        agg = {"han": 0, "words": 0, "chars": 0, "paras": 0, "formulas": 0}
        for item in sec["paras"]:
            m = measure(item["text"])
            agg["han"] += m["han"]
            agg["words"] += m["words"]
            agg["chars"] += m["chars"]
            agg["paras"] += 1
            assigned[item["index"]] = key
        # 题注单独汇总（见下方 cap），不计入章节 agg 与全稿 totals。
        agg["formulas"] = sec["formulas"]
        sec["agg"] = agg
        for k in ("han", "words", "chars", "paras", "formulas"):
            totals[k] += agg[k]

    cap = {"han": 0, "words": 0, "chars": 0, "paras": 0}
    for key, sec in sections.items():
        for item in sec["captions"]:
            m = measure(item["text"])
            cap["han"] += m["han"]
            cap["words"] += m["words"]
            cap["chars"] += m["chars"]
            cap["paras"] += 1

    tables = []
    for ti, table in enumerate(doc.tables):
        text = "\n".join(cell.text for row in table.rows for cell in row.cells)
        m = measure(text)
        m["rows"] = len(table.rows)
        m["cells"] = len(table.rows) * len(table.columns)
        tables.append(m)

    uncovered = [{"index": i, "style": styles[i], "text": texts[i][:60]}
                 for i in range(len(paras))
                 if texts[i] and i not in assigned and styles[i] != "Caption"
                 and i not in add.labels]
    try:
        formula_global = len(doc.element.body.findall(".//" + MATH_NS + "oMath"))
    except Exception:
        formula_global = totals["formulas"]
    table_formulas = 0
    for table in doc.tables:
        try:
            table_formulas += len(table._element.findall(".//" + MATH_NS + "oMath"))
        except Exception:
            pass
    return {"sections": sections, "totals": totals, "captions": cap, "tables": tables,
            "formula_global": formula_global, "formula_in_tables": table_formulas,
            "uncovered": uncovered, "styles": sorted(set(styles)),
            "abstract_index": abstract_i, "body_start_index": body_start_i,
            "body_end_index": body_end_i, "back_matter_index": back_i,
            "inline_shapes": len(doc.inline_shapes)}


def cached_props(path):
    out = {}
    try:
        with zipfile.ZipFile(path) as z:
            if "docProps/app.xml" in z.namelist():
                raw = z.read("docProps/app.xml").decode("utf-8", errors="replace")
                for key in ("Words", "Characters", "Pages", "Paragraphs", "Lines"):
                    m = re.search(r"<%s>([0-9]+)</%s>" % (key, key), raw)
                    if m:
                        out[key] = int(m.group(1))
            if "docProps/core.xml" in z.namelist():
                raw = z.read("docProps/core.xml").decode("utf-8", errors="replace")
                m = re.search(r"<dcterms:modified[^>]*>([^<]+)<", raw)
                if m:
                    out["modified"] = m.group(1)
    except Exception as exc:
        out["error"] = str(exc)
    return out


def fmt(value):
    return "—" if value is None else str(value)


def build_rows(res):
    rows = []
    for key in sorted(res["sections"], key=lambda k: (int(k[1:]), k)):
        sec = res["sections"][key]
        agg = sec["agg"]
        rows.append([key, sec["name"][:28], agg["han"], agg["words"], agg["chars"],
                     agg["paras"], agg["formulas"]])
    t = res["totals"]
    rows.append(["合计", "全部范围之和", t["han"], t["words"], t["chars"], t["paras"], t["formulas"]])
    return rows


def print_summary(root, rel_manuscript, res, doc):
    t = res["totals"]
    print("=== 论文稿件字数统计（不采用 Word 缓存字数）===")
    print("稿件: " + rel_manuscript)
    print("段落 %d，样式: %s" % (len(doc.paragraphs), ", ".join(res["styles"])))
    print("图 %d 张，表 %d 张，题注 %d 条" % (res["inline_shapes"], len(res["tables"]), res["captions"]["paras"]))
    print()
    print(C.table(["范围", "名称", "汉字", "英文词", "字符", "段落", "公式"], build_rows(res)))
    print()
    tb = {"han": 0, "words": 0, "chars": 0}
    for item in res["tables"]:
        for k in tb:
            tb[k] += item[k]
    print("公式：分范围之和 %d，文档整体 %d（差 %d 位于表格/文本框内）" % (
        t["formulas"], res["formula_global"], res["formula_global"] - t["formulas"]))
    print("表格内文字（不计入正文）: 汉字 %d、英文词 %d、字符 %d" % (tb["han"], tb["words"], tb["chars"]))
    print("题注（不计入正文）: 汉字 %d、英文词 %d、字符 %d" % (
        res["captions"]["han"], res["captions"]["words"], res["captions"]["chars"]))
    if res["uncovered"]:
        print("未归类段落 %d 条（见 --out 报告）" % len(res["uncovered"]))
    else:
        print("未归类段落 0 条：所有非空段落都落在声明的范围内。")


def build_report(root, rel_manuscript, res, doc, cfg, cmd, cached, mtime):
    pcfg = cfg.get("paper") or {}
    lines = C.report_header("论文稿件字数报告", cmd)
    t = res["totals"]
    lines += [
        "## 结论",
        "",
        "全稿 %d 段：汉字 %d，英文词 %d，字符 %d，公式 %d（文档整体 %d）；图 %d 张，表 %d 张，参考文献 %d 条。" % (
            t["paras"], t["han"], t["words"], t["chars"], t["formulas"], res["formula_global"],
            res["inline_shapes"], len(res["tables"]),
            res["sections"].get("S5", {}).get("entries", 0)),
        "",
        "稿件: " + rel_manuscript,
        "文件修改时间(文件系统): " + mtime,
        "",
        "## 统计口径",
        "",
        "- 汉字: " + pcfg.get("count_rules", {}).get("chinese_char", ""),
        "- 英文词: " + pcfg.get("count_rules", {}).get("english_word", ""),
        "- 字符: " + pcfg.get("count_rules", {}).get("chars", ""),
        "- 公式: " + pcfg.get("count_rules", {}).get("formula", ""),
        "- 表格: " + pcfg.get("count_rules", {}).get("tables", ""),
        "- 题注: " + pcfg.get("count_rules", {}).get("captions", ""),
        "- 参考文献: " + pcfg.get("count_rules", {}).get("references", ""),
        "",
        "## 分范围字数",
        "",
        C.table(["范围", "名称", "汉字", "英文词", "字符", "段落", "公式"], build_rows(res)),
        "",
        "## 图、表与题注",
        "",
        "图 %d 张（inline shape），表 %d 张，题注 %d 条。" % (
            res["inline_shapes"], len(res["tables"]), res["captions"]["paras"]),
        "",
    ]
    trows = []
    for i, item in enumerate(res["tables"], 1):
        trows.append(["表 %d" % i, item["rows"], item["cells"], item["han"], item["words"], item["chars"]])
    if trows:
        lines.append(C.table(["表", "行", "单元格", "汉字", "英文词", "字符"], trows))
        lines.append("")
    lines += ["## 未归类段落", ""]
    if res["uncovered"]:
        for item in res["uncovered"]:
            lines.append("- 第 %d 段（%s）：%s" % (item["index"], item["style"], item["text"]))
    else:
        lines.append("无。所有非空段落都落在声明的范围内。")
    lines += [
        "",
        "## Word 缓存字数的处理",
        "",
        "docProps/app.xml 记录 Words=%s、Characters=%s、Pages=%s，这些是 Word 上次保存时的缓存值，" % (
            fmt(cached.get("Words")), fmt(cached.get("Characters")), fmt(cached.get("Pages"))),
        "本报告不使用它，只把解析出的段落文字作为统计对象；缓存值与实测值不一致属正常现象。",
        "",
        "## 目标字数",
        "",
        "目标期刊: %s；目标字数: %s。" % (
            fmt(pcfg.get("target_journal")), fmt(pcfg.get("target_words"))),
        pcfg.get("target_note", ""),
        "",
        "## 本次无法准确识别的部分",
        "",
        "- 公式只计数不折字：Word 公式（OMML）里的符号数不到文字里，因此单列公式个数。",
        "- 表内文字与题注单列，不计入正文；若期刊要求把表计入字数，需要用本报告的两个数相加再人工取舍。",
        "- 补充材料不在本文件中，未计入。",
        "- 中文汉字与英文词分开统计，中英混排的句子按字符类别归属，不做语言判定。",
    ]
    return lines


def sections_blocks(res):
    blocks = {}
    for key, sec in res["sections"].items():
        agg = sec["agg"]
        blocks[key] = "- 汉字: %d；英文词: %d；字符: %d；段落: %d；公式: %d" % (
            agg["han"], agg["words"], agg["chars"], agg["paras"], agg["formulas"])
    return blocks


def check_or_write(root, cfg, res, write=False):
    rel = (cfg.get("paper") or {}).get("sections_file")
    path = os.path.join(root, rel.replace("/", os.sep))
    if not os.path.isfile(path):
        print("找不到章节清单: " + rel)
        return 2
    text = C.read_text(path)
    blocks = sections_blocks(res)
    keys = [m.group(1) for m in SEC_RE.finditer(text)]
    found = {m.group(1): m.group(2).strip() for m in SEC_RE.finditer(text)}
    problems = []
    for key in sorted({k for k in keys if keys.count(k) > 1}):
        problems.append("%s 在章节清单里重复出现 %d 次" % (key, keys.count(key)))
    for key in sorted(blocks):
        if key not in found:
            problems.append("%s 在章节清单里没有统计块" % key)
            continue
        expect = blocks[key]
        if write:
            continue
        if found[key] != expect:
            problems.append("%s 字数块与实际不符\n  清单: %s\n  实际: %s" % (key, found[key], expect))
    if problems:
        for p in problems:
            print("  " + p)
        return 1
    if write:
        planned = []
        for key, body in blocks.items():
            pat = re.compile(r"(<!-- stats:%s -->\n).*?(\n<!-- /stats:%s -->)" % (key, key), re.S)
            _, n = pat.subn(lambda m: m.group(1) + body + m.group(2), text)
            if n != 1:
                problems.append("%s 可写入统计块数量为 %d（必须为 1）" % (key, n))
            else:
                planned.append((pat, body))
        if problems:
            for p in problems:
                print("  " + p)
            print("章节清单未写入：存在缺块或重复块。")
            return 1
        for pat, body in planned:
            text, n = pat.subn(lambda m: m.group(1) + body + m.group(2), text)
            if n != 1:  # 防御：预检后不应发生
                print("  统计块写入时数量异常，未完成写入")
                return 1
        C.write_report(path, text.splitlines())
        print("已写入章节清单: " + rel)
    print("章节清单字数与实际一致（%d 个统计块）" % len(blocks))
    return 0


def _replay_path(value):
    """把影响统计对象的参数写成可重放的相对路径（越出当前目录则用绝对路径）。"""
    absolute = os.path.abspath(value)
    rel = os.path.relpath(absolute, os.getcwd())
    if rel == ".." or rel.startswith(".." + os.sep):
        rel = absolute
    return rel.replace("\\", "/")


def _quote_arg(value):
    """命令行含空格/引号时加双引号，保证记录的命令可直接重放。"""
    if any(ch in value for ch in ' \t"'):
        return '"' + value.replace('"', '\\"') + '"'
    return value


def main():
    ap = argparse.ArgumentParser(description="统计论文稿件字数并与章节清单核对")
    ap.add_argument("--root", default=None)
    ap.add_argument("--config", default=None)
    ap.add_argument("--manuscript", default=None, help="默认取配置 paper.manuscript")
    ap.add_argument("--out", default=None, help="Markdown 报告路径")
    ap.add_argument("--json", default=None, help="机器可读结果路径")
    ap.add_argument("--write-sections", action="store_true", help="把统计块写回章节清单")
    ap.add_argument("--check-sections", action="store_true", help="核对章节清单里的字数")
    args = ap.parse_args()
    root = os.path.abspath(args.root) if args.root else C.find_root()
    cfg = C.load_config(root, args.config)
    rel_manuscript = args.manuscript or (cfg.get("paper") or {}).get("manuscript")
    path = rel_manuscript if os.path.isabs(rel_manuscript) else os.path.join(root, rel_manuscript.replace("/", os.sep))
    if not os.path.isfile(path):
        print("找不到稿件: " + rel_manuscript)
        return 2
    if (args.write_sections or args.check_sections) and args.manuscript:
        cfg_rel = (cfg.get("paper") or {}).get("manuscript") or ""
        cfg_abs = os.path.join(root, cfg_rel.replace("/", os.sep))
        if os.path.normcase(os.path.realpath(cfg_abs)) != os.path.normcase(os.path.realpath(path)):
            print("拒绝：--manuscript 与配置统计对象不一致。")
            print("  --write-sections/--check-sections 只允许配置稿件: " + cfg_rel)
            print("  本次请求: " + rel_manuscript)
            return 2
    import datetime
    try:
        import docx
    except ImportError:
        print("缺少 python-docx，无法解析 docx。请用 DSH 自带 Python 运行本脚本。")
        return 2
    doc = docx.Document(path)
    res = classify(doc, cfg)
    cached = cached_props(path)
    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")
    print_summary(root, rel_manuscript, res, doc)
    code = 0
    if args.write_sections or args.check_sections:
        code = check_or_write(root, cfg, res, write=args.write_sections)
    if args.out or args.json:
        cmd = "python scripts/paper_stats.py"
        if args.root:
            cmd += " --root " + _quote_arg(_replay_path(args.root))
        if args.config:
            cmd += " --config " + _quote_arg(_replay_path(args.config))
        if args.manuscript:
            cmd += " --manuscript " + _quote_arg(_replay_path(args.manuscript))
        if args.write_sections:
            cmd += " --write-sections"
        if args.check_sections:
            cmd += " --check-sections"
        if args.out:
            cmd += " --out " + _quote_arg(_replay_path(args.out))
        if args.json:
            cmd += " --json " + _quote_arg(_replay_path(args.json))
        payload = {
            "生成命令": cmd,
            "生成时间": C.now_str(),
            "manuscript": rel_manuscript,
            "file_mtime": mtime,
            "cached_word_props": cached,
            "sections": {k: {"name": v["name"], "agg": v["agg"],
                             "entries": v.get("entries", 0),
                             "captions": len(v["captions"])} for k, v in res["sections"].items()},
            "totals": res["totals"],
            "captions": res["captions"],
            "tables": res["tables"],
            "uncovered": res["uncovered"],
            "styles": res["styles"],
            "inline_shapes": res["inline_shapes"],
            "target_journal": (cfg.get("paper") or {}).get("target_journal"),
            "target_words": (cfg.get("paper") or {}).get("target_words"),
        }
        if args.out:
            C.write_report(args.out, build_report(root, rel_manuscript, res, doc, cfg, cmd, cached, mtime))
            print("报告: " + os.path.abspath(args.out))
        if args.json:
            os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
            with open(args.json, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            print("JSON: " + os.path.abspath(args.json))
    return code


if __name__ == "__main__":
    sys.exit(main())
