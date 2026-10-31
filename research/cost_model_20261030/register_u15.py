# -*- coding: utf-8 -*-
"""Register Shoup (ACCESS No.30, 2007 reprint) and Biswas et al. (arXiv v2, 2016) as P36/P37.

U15 of docs/TODO.md: the two cost-framework sources were read but never entered the
numbered literature index.  This script performs the registration described in
literature/README.md: move the PDF into the established directory, append the entries
to the index config data (P sources / download status / download CSV), record the real
reading scope in reading-log.json, then the caller rebuilds the index with
python scripts/lit_index.py --write.

Appends only: existing 35 entries are kept byte for byte; new records are inserted
before the closing bracket.  Re-running is a no-op.
"""
import csv
import hashlib
import io
import json
import os
import shutil

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PDF_DIR = os.path.join(ROOT, "research", "ev_parking_math_20261029", "PDFs")
DL_DIR = os.path.join(ROOT, "research", "cost_model_20261030", "downloads")

SHOUP_SRC = os.path.join(DL_DIR, "shoup2006_cruising-for-parking_fbfl-reprint.pdf")
SHOUP_DST = os.path.join(PDF_DIR, "P36_Shoup_Cruising_for_Parking_ACCESS30_2007_reprint.pdf")
BISWAS_SRC = os.path.join(DL_DIR, "biswas2016_overstaying-ev-park-and-charge_arxiv1604.05471v2.pdf")
BISWAS_DST = os.path.join(PDF_DIR, "P37_Biswas_Managing_Overstaying_EVs_in_Park_and_Charge_Facilities_arXiv_1604.05471v2.pdf")

SHOUP_ENTRY = {
    "id": "P36",
    "group": "交通与充电应用",
    "priority": "关键前作",
    "year": "2007（ACCESS 重印）；原期刊版 2006",
    "authors": "Donald Shoup",
    "title": "Cruising for Parking",
    "venue": "ACCESS Magazine No.30 (Spring 2007):16-22；Transport Policy 13(6):479-486 (2006) 的重印版",
    "doi": "",
    "url": "http://www.fbfl.us/DocumentCenter/View/16322/Cruising-for-Parking",
    "level": "选读 ACCESS 2007 重印版第 17 页（12 页扫描件无文字层，逐页渲染目视核读）；2006 Transport Policy 版全文未取得",
    "use": "巡游找车位的时间与车流占比机制，支撑成本框架中油车停车失败的搜索时间项与敏感性场景。",
    "limit": "全部为路边停车样本（1927-2001、11 城市 CBD），非台北路外停车场；数值不得当作台北参数，两版数值一致性未核。",
}
BISWAS_ENTRY = {
    "id": "P37",
    "group": "排队与动态准入",
    "priority": "关键前作",
    "year": "2016",
    "authors": "Arpita Biswas; Ragavendran Gopalakrishnan; Partha Dutta",
    "title": "Managing Overstaying Electric Vehicles in Park-and-Charge Facilities",
    "venue": "arXiv:1604.05471v2（会议版 IJCAI-16）",
    "doi": "",
    "url": "https://arxiv.org/abs/1604.05471",
    "level": "选读 arXiv v2 第 1 页摘要、第 3 页风险与收费定义、第 7 页数值示例、第 11 页仿真参数",
    "use": "充完电不挪车（overstay）作为独立资源阻塞机制的建模依据；罚金属转移支付而非社会成本。",
    "limit": "印度情境的仿真假设值（USD），αo 是机制参数不是损失单价；不得作为台北占桩罚金或挪车代价参数。",
}


def sha_and_bytes(path):
    data = open(path, "rb").read()
    return len(data), hashlib.sha256(data).hexdigest()


def insert_items(path, entries, indent_step=2):
    """Append JSON objects to a top-level JSON array without reformatting history."""
    text = open(path, "r", encoding="utf-8-sig").read()
    ids = {e["id"] for e in json.loads(text)}
    todo = [e for e in entries if e["id"] not in ids]
    if not todo:
        return 0
    idx = text.rstrip().rfind("]")
    head, tail = text[:idx].rstrip(), text[idx:]
    blocks = []
    for e in todo:
        body = json.dumps(e, ensure_ascii=False, indent=indent_step)
        body = "\n".join((" " * indent_step) + line if i else (" " * indent_step) + line
                          for i, line in enumerate(body.splitlines()))
        blocks.append(body)
    new = head + ",\n" + ",\n".join(blocks) + "\n" + tail
    json.loads(new)  # validate before writing
    open(path, "w", encoding="utf-8", newline="\n").write(new)
    return len(todo)


def insert_dict_items(path, entries):
    """Append key -> object to a top-level JSON object, keeping history byte-stable."""
    text = open(path, "r", encoding="utf-8-sig").read()
    current = json.loads(text)
    todo = [e for e in entries if e["id"] not in current]
    if not todo:
        return 0
    idx = text.rstrip().rfind("}")
    head, tail = text[:idx].rstrip(), text[idx:]
    blocks = []
    for e in todo:
        body = json.dumps(e, ensure_ascii=False, indent=2).splitlines()
        block = '  "%s": %s' % (e["id"], body[0])
        block += "\n" + "\n".join(("  " + line) for line in body[1:])
        blocks.append(block)
    new = head + ",\n" + ",\n".join(blocks) + "\n" + tail
    json.loads(new)
    open(path, "w", encoding="utf-8", newline="\n").write(new)
    return len(todo)


def append_csv(path, rows, header):
    text = open(path, "r", encoding="utf-8-sig", newline="").read()
    exist = {r["编号"] for r in csv.DictReader(io.StringIO(text))}
    todo = [r for r in rows if r["编号"] not in exist]
    if not todo:
        return 0
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=header, lineterminator="\n")
    for r in todo:
        w.writerow(r)
    if not text.endswith("\n"):
        text += "\n"
    open(path, "w", encoding="utf-8", newline="").write(text + buf.getvalue())
    return len(todo)


def main():
    report = []
    for src, dst in ((SHOUP_SRC, SHOUP_DST), (BISWAS_SRC, BISWAS_DST)):
        if os.path.isfile(src) and not os.path.isfile(dst):
            shutil.move(src, dst)
            report.append("moved %s -> %s" % (os.path.basename(src), os.path.basename(dst)))
        elif os.path.isfile(dst):
            report.append("already in place: %s" % os.path.basename(dst))
        else:
            raise SystemExit("missing PDF: %s" % src)

    shoup_bytes, shoup_sha = sha_and_bytes(SHOUP_DST)
    biswas_bytes, biswas_sha = sha_and_bytes(BISWAS_DST)

    status_entries = [
        {"id": "P36", "status": "downloaded",
         "filename": os.path.basename(SHOUP_DST),
         "source_url": SHOUP_ENTRY["url"],
         "resolved_url": SHOUP_ENTRY["url"],
         "bytes": shoup_bytes,
         "attempts": [],
         "pages": 12,
         "title_keyword_coverage": None,
         "text_verified": False,
         "note": "ACCESS No.30 (Spring 2007) 重印版扫描件，无文字层；p.17 逐页渲染目视核读，非 2006 Transport Policy 版",
         "sha256": shoup_sha,
         "version_note": "ACCESS Magazine No.30 (Spring 2007):16-22，fbfl.us 市政转载扫描件；不是 Transport Policy 13(6):479-486 (2006) 期刊版"},
        {"id": "P37", "status": "downloaded",
         "filename": os.path.basename(BISWAS_DST),
         "source_url": BISWAS_ENTRY["url"],
         "resolved_url": "https://arxiv.org/pdf/1604.05471v2",
         "bytes": biswas_bytes,
         "attempts": [],
         "pages": 15,
         "title_keyword_coverage": 1.0,
         "text_verified": False,
         "note": "arXiv v2 作者稿；只选读 p.1/p.3/p.7/p.11，未通读全文",
         "sha256": biswas_sha,
         "version_note": "arXiv:1604.05471v2（会议版 IJCAI-16）"},
    ]

    csv_rows = [
        {"编号": "P36", "方向": "交通与充电应用", "年份": "2007（ACCESS 重印）；原期刊版 2006",
         "作者": "Donald Shoup", "题名": "Cruising for Parking",
         "刊物": "ACCESS Magazine No.30 (Spring 2007):16-22；Transport Policy 13(6):479-486 (2006) 的重印版",
         "DOI": "", "状态": "已下载",
         "版本或缺失原因": "ACCESS No.30 (2007 春季号) 重印版扫描件（12 页、无文字层）；非 2006 Transport Policy 版",
         "PDF文件": "PDFs/" + os.path.basename(SHOUP_DST),
         "页数": "12", "字节数": str(shoup_bytes),
         "下载来源": SHOUP_ENTRY["url"], "论文入口": "",
         "SHA256": shoup_sha},
        {"编号": "P37", "方向": "排队与动态准入", "年份": "2016",
         "作者": "Arpita Biswas; Ragavendran Gopalakrishnan; Partha Dutta",
         "题名": "Managing Overstaying Electric Vehicles in Park-and-Charge Facilities",
         "刊物": "arXiv:1604.05471v2（会议版 IJCAI-16）", "DOI": "", "状态": "已下载",
         "版本或缺失原因": "arXiv:1604.05471v2 作者稿（15 页）；会议版 IJCAI-16",
         "PDF文件": "PDFs/" + os.path.basename(BISWAS_DST),
         "页数": "15", "字节数": str(biswas_bytes),
         "下载来源": BISWAS_ENTRY["url"], "论文入口": "https://arxiv.org/abs/1604.05471",
         "SHA256": biswas_sha},
    ]

    n1 = insert_items(os.path.join(ROOT, "research", "ev_parking_math_20261029", "sources.json"),
                      [SHOUP_ENTRY, BISWAS_ENTRY])
    report.append("sources.json appended: %d" % n1)
    n2 = insert_dict_items(os.path.join(ROOT, "research", "ev_parking_math_20261029", "download_status.json"),
                           status_entries)
    report.append("download_status.json appended: %d" % n2)
    header = ["编号", "方向", "年份", "作者", "题名", "刊物", "DOI", "状态", "版本或缺失原因",
              "PDF文件", "页数", "字节数", "下载来源", "论文入口", "SHA256"]
    n3 = append_csv(os.path.join(ROOT, "research", "ev_parking_math_20261029", "download_manifest.csv"),
                    csv_rows, header)
    report.append("download_manifest.csv appended: %d" % n3)

    log_path = os.path.join(ROOT, "literature", "reading-log.json")
    log = json.load(open(log_path, encoding="utf-8-sig"))
    items = log.setdefault("items", {})
    if "P36" not in items:
        items["P36"] = {
            "read_status": "摘要级",
            "evidence": [
                "research/cost_model_20261030/notes/shoup2007-cruising-for-parking.md",
                "research/ev_parking_math_20261029/PDFs/" + os.path.basename(SHOUP_DST),
            ],
            "date": "2026-10-30",
            "note": "只选读 ACCESS No.30 (2007) 重印版第 17 页（12 页扫描件，逐页渲染目视核读），其余页未读；2006 Transport Policy 版未取得，故不升全文略读，也不登记为已验证。",
        }
    if "P37" not in items:
        items["P37"] = {
            "read_status": "摘要级",
            "evidence": [
                "research/cost_model_20261030/notes/biswas2016-overstaying-park-and-charge.md",
                "research/ev_parking_math_20261029/PDFs/" + os.path.basename(BISWAS_DST),
            ],
            "date": "2026-10-30",
            "note": "只选读 arXiv v2 第 1 页摘要、第 3 页风险与收费定义、第 7 页数值示例、第 11 页仿真参数，未通读全文，不登记为全文略读/已验证。",
        }
    json.dump(log, open(log_path, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=2)
    open(log_path, "a", encoding="utf-8").write("\n")
    report.append("reading-log.json updated")
    print("\n".join(report))
    print(json.dumps({"P36": {"bytes": shoup_bytes, "sha256": shoup_sha},
                      "P37": {"bytes": biswas_bytes, "sha256": biswas_sha}}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
