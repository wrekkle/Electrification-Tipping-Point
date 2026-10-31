# N2 与 M07 去重判定（R4）

类型: 查重记录  
状态: 生效  
负责人: cost-data  
日期: 2026-10-31  
输入: research/round3_20261031/novelty_check.md（N2 登记）、literature/index.json / notes/M07、Crossref/OpenAlex 元数据

## 结论（确定）

**N2 与 M07 是同一篇论文**。理由（三条独立证据，均可在本机复算/复核）：

| 证据 | N2（novelty_check 登记） | M07（本机全文/索引/Crossref） |
|---|---|---|
| 题名 | Electric vehicles shared charging and parking: A reservation-based dynamic rolling allocation framework considering unpunctuality | 完全相同（标题逐字一致） |
| 出版社文章号/PII | ScienceDirect URL …/abs/pii/**S0968090X25002633** | DOI 10.1016/j.trc.2025.105259；Crossref link 字段 **PII:S0968090X25002633**，与 N2 URL 的 PII 完全一致 |
| 作者/年/卷 | 未取得（ScienceDirect 403） | Zhang Hongyang; Gong Jinrui; Tang Wei; Zhenyu Mei; Chi Feng；TR-C **179 (2025) 105259**，2025-10 出版 |
| 全文 | 未取得 | 本机 PDF：papers/electrification-math/M07_dynamic-rolling-parking-charging-unpunctuality_TRC2025.pdf（29 页，16,889,012 B），笔记 literature/notes/M07-混合停车充电滚动分配与不准时.md |

Crossref 复算命令（HTTP 200）：

    python -c "import json,urllib.request;d=json.load(urllib.request.urlopen('https://api.crossref.org/works/10.1016/j.trc.2025.105259'));m=d['message'];print(m['title'][0]);print(m['volume'],m['article-number'],m['DOI']);print([l['URL'] for l in m['link']])"

输出含 `S0968090X25002633` 与题名，和 N2 的 PII、题名一致。

## 处置建议

- 文献编号合并：保留 M07（已有全文、笔记、索引、PDF 哈希），把 N2 标记为 M07 的别名/重复登记；后续引用只用 M07。
- research/round3_20261031/novelty_check.md 与 docs/TODO.md 的 U20 中“N2 仅题录、摘要 403”可以改写为“N2=M07，已有全文；403 为出版社反爬，不代表缺文献”。本轮无双写权限，不改旧文件，只在此记录。
- N2 不是新的独立相关工作；第三轮报告中把它与 N1 并列可能重复计数（N1 与 M07 是不同文，见对照表）。

## 未验证

- N2 登记中的 ScienceDirect URL 未再访问（403 已在此前记录）；本判定不依赖再次访问，PII 与 DOI 映射由 Crossref 给出（确定）。
